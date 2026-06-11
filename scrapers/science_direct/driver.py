"""
Selenium WebDriver management for Science Direct scraper.

SeleniumBase UC mode kullanır (CDP modu YOK):
- uc=True → Chrome undetectable (Cloudflare bot tespiti geçilir)
- sb.solve_captcha() / sb.uc_gui_click_captcha() → CAPTCHA çözümü
- CDP modu yok → asyncio event loop deadlock yok
- sb.driver (raw WebDriver) → tüm DOM/JS operasyonları normal çalışır

Architecture: SeleniumDriver, WebDriver-compatible proxy olarak davranır;
scraper.py / rate_limiter.py / navigation.py hiçbir değişiklik gerektirmeden çalışır.
  self.driver = self.selenium_driver.start()  →  SeleniumDriver (proxy) döner
  self.driver.find_elements(...)               →  sb.driver.find_elements(...)
  self.driver.execute_script(...)              →  sb.driver.execute_script(...)
  WebDriverWait(self.driver, t).until(cond)   →  proxy interface ile çalışır
"""

import concurrent.futures
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from seleniumbase import SB

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
from utils.user_agents import USER_AGENTS
logger = get_logger('science_direct')

from .config import ProxyConfig
from backend.core.config import settings
from backend.core.circuit_breaker import get_circuit_breaker
from utils.network_probe import NetworkProbe, effective_page_load_timeout
from utils.resilient_fetch import FetchResult
from utils.chrome_tuning import maybe_emulate_slow_network


class SeleniumDriver:
    """
    SeleniumBase UC mode tabanlı WebDriver proxy.

    CDP modu KULLANILMAZ — asyncio deadlock riskini ortadan kaldırır.
    Tüm operasyonlar sb.driver (ham WebDriver, normal HTTP/WebDriver protokolü)
    üzerinden yapılır.

    Cloudflare bypass: UC mode (uc=True) Chrome'u undetectable yapar;
    CAPTCHA için sb.solve_captcha() / sb.uc_gui_click_captcha() kullanılır.
    """

    CF_TITLE_KEYWORDS = [
        "just a moment",
        "bir dakika lütfen",
        "lütfen bekleyin",
        "checking your browser",
        "please wait",
        "attention required",
        "bitte warten",
        "un moment",
    ]

    def __init__(self,
                 proxy_config: Optional[ProxyConfig] = None,
                 headless: bool = False,
                 use_undetected: bool = True,   # API uyumluluğu — yoksayılır
                 user_agent: str = None):        # API uyumluluğu — yoksayılır
        self.proxy_config = proxy_config
        self.headless = headless
        self.use_undetected = use_undetected

        self._sb = None
        self._sb_context = None
        self._raw_driver = None      # sb.driver — tüm Selenium operasyonları buraya

        self.network_class = "fast"
        self.last_fetch = None
        self._base_page_load_timeout = settings.sd_timeout

        # User-agent rotation (content error / restart sonrası farklı UA)
        self._current_ua: Optional[str] = None
        self._used_uas: list = []

    # ------------------------------------------------------------------ #
    #  WebDriver proxy interface
    # ------------------------------------------------------------------ #

    @property
    def driver(self):
        """Geriye dönük uyumluluk: self.driver her zaman proxy'i döndürür."""
        return self

    @property
    def page_source(self) -> str:
        try:
            if self._raw_driver:
                return self._raw_driver.page_source
        except Exception as e:
            logger.warning(f"page_source hatası: {e}")
        return ""

    @property
    def title(self) -> str:
        try:
            if self._raw_driver:
                return self._raw_driver.title or ""
        except Exception:
            pass
        return ""

    @property
    def current_url(self) -> str:
        try:
            if self._raw_driver:
                return self._raw_driver.current_url or ""
        except Exception:
            pass
        return ""

    def execute_script(self, script: str, *args):
        """JavaScript çalıştır — ham driver (HTTP/WebDriver protokolü, no CDP)."""
        try:
            if self._raw_driver:
                return self._raw_driver.execute_script(script, *args)
        except Exception as e:
            logger.warning(f"execute_script hatası: {e}")
        return None

    def find_element(self, by, value):
        if self._raw_driver:
            return self._raw_driver.find_element(by, value)
        raise RuntimeError("Driver aktif değil")

    def find_elements(self, by, value):
        if self._raw_driver:
            return self._raw_driver.find_elements(by, value)
        return []

    def set_page_load_timeout(self, timeout: float):
        if self._raw_driver:
            try:
                self._raw_driver.set_page_load_timeout(timeout)
            except Exception:
                pass

    def set_script_timeout(self, timeout: float):
        if self._raw_driver:
            try:
                self._raw_driver.set_script_timeout(timeout)
            except Exception:
                pass

    def implicitly_wait(self, timeout: float):
        if self._raw_driver:
            try:
                self._raw_driver.implicitly_wait(timeout)
            except Exception:
                pass

    def set_window_size(self, width: int, height: int):
        if self._raw_driver:
            try:
                self._raw_driver.set_window_size(width, height)
            except Exception:
                pass

    def save_screenshot(self, path: str) -> bool:
        if self._raw_driver:
            try:
                return self._raw_driver.save_screenshot(path)
            except Exception:
                pass
        return False

    def quit(self):
        self.close()

    # ------------------------------------------------------------------ #
    #  Stealth / Fingerprint patching
    # ------------------------------------------------------------------ #

    # CDP ile her yeni belge yüklenmeden önce çalışacak stealth JS.
    # UC mode zaten navigator.webdriver'ı patch eder; bu script geri kalanları kapatır.
    _STEALTH_SCRIPT = r"""
(() => {
    // 1. window.chrome runtime — yoksa otomasyona işaret eder
    if (!window.chrome) {
        window.chrome = {
            app: { isInstalled: false, InstallState: { DISABLED:'disabled', INSTALLED:'installed', NOT_INSTALLED:'not_installed' }, RunningState: { CANNOT_RUN:'cannot_run', READY_TO_RUN:'ready_to_run', RUNNING:'running' } },
            runtime: {
                OnInstalledReason: { CHROME_UPDATE:'chrome_update', INSTALL:'install', SHARED_MODULE_UPDATE:'shared_module_update', UPDATE:'update' },
                OnRestartRequiredReason: { APP_UPDATE:'app_update', OS_UPDATE:'os_update', PERIODIC:'periodic' },
                PlatformArch: { ARM:'arm', ARM64:'arm64', MIPS:'mips', MIPS64:'mips64', X86_32:'x86-32', X86_64:'x86-64' },
                PlatformOs: { ANDROID:'android', CROS:'cros', LINUX:'linux', MAC:'mac', OPENBSD:'openbsd', WIN:'win' },
                RequestUpdateCheckStatus: { NO_UPDATE:'no_update', THROTTLED:'throttled', UPDATE_AVAILABLE:'update_available' },
                connect: () => {}, sendMessage: () => {}, id: undefined,
            },
            loadTimes: function() { return { requestTime: Date.now()/1000, startLoadTime: Date.now()/1000, commitLoadTime: Date.now()/1000, finishDocumentLoadTime: Date.now()/1000, finishLoadTime: Date.now()/1000, firstPaintTime: Date.now()/1000, firstPaintAfterLoadTime: 0, navigationType:'Other', wasFetchedViaSpdy:false, wasNpnNegotiated:true, npnNegotiatedProtocol:'h2', wasAlternateProtocolAvailable:false, connectionInfo:'h2' }; },
            csi: function() { return { startE: Date.now(), onloadT: Date.now(), pageT: 1000 + Math.random()*4000, tran: 15 }; },
        };
    }

    // 2. navigator.languages — tutarlı locale
    try {
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
    } catch(e) {}

    // 3. navigator.hardwareConcurrency — gerçekçi
    try {
        if (!navigator.hardwareConcurrency || navigator.hardwareConcurrency < 2) {
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
        }
    } catch(e) {}

    // 4. navigator.deviceMemory — gerçekçi
    try {
        if (!navigator.deviceMemory) {
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true });
        }
    } catch(e) {}

    // 5. navigator.permissions — Notification.permission ile tutarlı
    try {
        const _origQuery = navigator.permissions.query.bind(navigator.permissions);
        Object.defineProperty(navigator.permissions, 'query', {
            value: (params) => {
                if (params && params.name === 'notifications') {
                    return Promise.resolve({ state: (typeof Notification !== 'undefined' ? Notification.permission : 'default'), onchange: null });
                }
                return _origQuery(params);
            },
            configurable: true,
        });
    } catch(e) {}
})();
"""

    def _inject_stealth_scripts(self) -> None:
        """
        CDP üzerinden stealth JS'i her yeni belge öncesinde çalışacak şekilde ekler.
        UC mode navigator.webdriver'ı patch eder; bu metot geri kalan sinyalleri kapatır.
        """
        if not self._raw_driver:
            return
        try:
            self._raw_driver.execute_cdp_cmd(
                'Page.addScriptToEvaluateOnNewDocument',
                {'source': self._STEALTH_SCRIPT}
            )
            logger.debug("Stealth scripts injected via CDP")
        except Exception as e:
            logger.debug(f"Stealth script injection başarısız (devam): {e}")

    # ------------------------------------------------------------------ #
    #  Cloudflare detection & solving
    # ------------------------------------------------------------------ #

    def _is_cloudflare(self) -> bool:
        try:
            title = (self._raw_driver.title or "").lower()
            return any(kw in title for kw in self.CF_TITLE_KEYWORDS)
        except Exception:
            return False

    def _human_pause(self, lo: float = 1.5, hi: float = 4.0) -> None:
        """Rastgele insan benzeri bekleme — CF davranış analizini geçmek için."""
        import random
        time.sleep(random.uniform(lo, hi))

    def _solve_cloudflare(self, max_click_attempts: int = 3) -> bool:
        """
        Cloudflare Turnstile / JS challenge çözümü.

        Sıra:
          1. 10s otomatik geçiş bekle (ucmode bunu bazen kendisi halleder)
          2. uc_gui_handle_captcha() — SB'nin kendi retry'lı CF handler'ı
          3. uc_gui_click_cf() — CF Turnstile'a özel tıklayıcı (generic değil)
             Her tıklamadan sonra sayfa yeniden yüklenebilir; max_click_attempts kez dene.
        """
        if not self._is_cloudflare():
            return True

        logger.warning("Cloudflare challenge algılandı, otomatik geçiş bekleniyor (10s)...")
        time.sleep(10)

        if not self._is_cloudflare():
            logger.success("Cloudflare otomatik geçildi")
            return True

        if not self._sb:
            logger.warning("SB instance yok, CF çözülemiyor")
            return False

        # Adım 2: uc_gui_handle_captcha — SB'nin kendi retry'lı handler'ı (CF + reCAPTCHA)
        if hasattr(self._sb, "uc_gui_handle_captcha"):
            try:
                logger.info("uc_gui_handle_captcha() deneniyor...")
                self._human_pause(1.0, 2.5)   # insan benzeri gecikme
                self._sb.uc_gui_handle_captcha()
                time.sleep(6)
                if not self._is_cloudflare():
                    logger.success("Cloudflare uc_gui_handle_captcha() ile çözüldü")
                    return True
                logger.warning("uc_gui_handle_captcha() sonrası CF hala mevcut")
            except Exception as e:
                logger.warning(f"uc_gui_handle_captcha() hatası: {e}")

        # Adım 3: uc_gui_click_cf — CF Turnstile'a özel (generic detect adımı yok)
        cf_click_fn = getattr(self._sb, "uc_gui_click_cf", None) or getattr(self._sb, "uc_gui_click_captcha", None)
        if cf_click_fn is None:
            logger.warning("CF tıklama metodu bulunamadı")
            return False

        method_name = "uc_gui_click_cf" if hasattr(self._sb, "uc_gui_click_cf") else "uc_gui_click_captcha"
        for click_attempt in range(1, max_click_attempts + 1):
            try:
                logger.info(f"{method_name}() deneniyor (tık {click_attempt}/{max_click_attempts})...")
                self._human_pause(0.8, 2.0)   # tıklamadan önce kısa insan gecikmesi
                cf_click_fn()
                # Sayfa yeniden yüklenebilir — yeterli süre bekle
                time.sleep(8)
                if not self._is_cloudflare():
                    logger.success(f"Cloudflare {method_name}() ile çözüldü (tık {click_attempt})")
                    return True
                logger.warning(f"Tık {click_attempt}/{max_click_attempts}: CF hala mevcut")
                if click_attempt < max_click_attempts:
                    backoff = 12 * click_attempt
                    logger.warning(f"{backoff}s bekleniyor...")
                    time.sleep(backoff)
            except Exception as e:
                logger.warning(f"{method_name}() hatası (tık {click_attempt}): {e}")
                if click_attempt < max_click_attempts:
                    time.sleep(5)

        logger.warning(f"Cloudflare {max_click_attempts} tıklamada geçilemedi "
                       f"(başlık: {(self._raw_driver.title or '')[:40]})")
        return False

    def _handle_cookie_consent(self) -> bool:
        """
        OneTrust / genel cookie consent banner'ını kapat.
        Her driver'ın get() çağrısında otomatik tetiklenir —
        main driver ve tüm worker driver'lar için geçerlidir.
        """
        try:
            from .utils import handle_cookie_consent
            return handle_cookie_consent(self)
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Proxy helper
    # ------------------------------------------------------------------ #

    def _get_proxy_string(self) -> str:
        """SeleniumBase proxy format: user:pass@host:port"""
        if self.proxy_config and self.proxy_config.is_configured():
            return (
                f"{self.proxy_config.proxy_user}:{self.proxy_config.proxy_pass}"
                f"@{self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}"
            )
        return ""

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> Optional['SeleniumDriver']:
        """
        SeleniumBase UC mode başlatır (CDP modu yok).
        Returns self (proxy) on success, None on failure.
        """
        try:
            logger.info("WebDriver başlatılıyor (SeleniumBase UC mode, CDP yok)...")
            logger.info(f"  - Headless: {self.headless}")

            use_proxy = (
                self.proxy_config is not None
                and self.proxy_config.use_proxy
                and self.proxy_config.is_configured()
            )

            sb_kwargs = {
                "uc": True,
                "test": True,
                "incognito": True,
                "locale_code": "en",
                "page_load_strategy": settings.page_load_strategy,
            }

            if settings.block_resources_for('sciencedirect'):
                sb_kwargs["block_images"] = True

            if self.headless:
                sb_kwargs["headless"] = True

            if use_proxy:
                sb_kwargs["proxy"] = self._get_proxy_string()
                logger.info(f"  - Proxy: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
            else:
                logger.info("  - Proxy: Devre dışı")

            if self._current_ua:
                sb_kwargs["agent"] = self._current_ua
                logger.info(f"  - User Agent: {self._current_ua[:70]}...")
            else:
                logger.info("  - User Agent: SeleniumBase otomatik (undetectable)")

            import os
            os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

            original_argv = sys.argv.copy()
            if "--quiet" not in sys.argv:
                sys.argv.append("--quiet")

            try:
                self._sb_context = SB(**sb_kwargs)
                self._sb = self._sb_context.__enter__()
                self._raw_driver = self._sb.driver
            finally:
                sys.argv = original_argv

            # Adaptif timeout
            try:
                self.network_class = NetworkProbe().measure_and_classify(self._raw_driver)
            except Exception:
                self.network_class = "fast"

            eff_timeout = effective_page_load_timeout(
                self._base_page_load_timeout, self.network_class
            )
            self._raw_driver.set_page_load_timeout(eff_timeout)
            self._raw_driver.set_script_timeout(20)
            self._raw_driver.implicitly_wait(settings.implicit_wait)
            logger.info(
                "page_load_timeout_set",
                effective_timeout=eff_timeout,
                network_class=self.network_class,
            )

            import random
            w = random.choice([1920, 1440, 1536, 1280])
            h = random.choice([1080, 900, 864, 800])
            self._raw_driver.set_window_size(w, h)
            maybe_emulate_slow_network(self._raw_driver, settings)

            # Her yeni belge yüklenmeden önce stealth JS çalışsın (CF fingerprint bypass)
            self._inject_stealth_scripts()

            logger.success(
                f"SeleniumBase WebDriver başlatıldı {'(proxy ile)' if use_proxy else '(proxy yok)'}"
            )
            return self

        except Exception as e:
            logger.error(f"WebDriver başlatma hatası: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close(self):
        """SB context'ini kapat."""
        if self._sb_context:
            try:
                logger.info("WebDriver kapatılıyor...")
                # SB context exit triggers asyncio cleanup; run in isolated thread
                # to avoid "event loop is already running" from FastAPI/CDP loops.
                ctx = self._sb_context
                def _exit():
                    import asyncio
                    asyncio.set_event_loop(asyncio.new_event_loop())
                    ctx.__exit__(None, None, None)
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    executor.submit(_exit).result(timeout=15)
                except Exception:
                    pass
                finally:
                    executor.shutdown(wait=False)
            except OSError:
                pass
            except Exception as e:
                logger.warning(f"WebDriver kapatma hatası: {e}")
            finally:
                self._sb = None
                self._sb_context = None
                self._raw_driver = None
                logger.success("WebDriver kapatıldı")
        elif self._raw_driver:
            try:
                self._raw_driver.quit()
            except Exception:
                pass
            self._raw_driver = None

    def restart(self) -> Optional['SeleniumDriver']:
        """Tarayıcıyı kapatıp yeniden başlat."""
        try:
            logger.warning("Tarayıcı yeniden başlatılıyor...")
            self.close()
            time.sleep(2)
            result = self.start()
            if result:
                logger.success("Tarayıcı başarıyla yeniden başlatıldı!")
            else:
                logger.error("Tarayıcı yeniden başlatılamadı!")
            return result
        except Exception as e:
            logger.error(f"Tarayıcı yeniden başlatma hatası: {e}")
            return None

    def _pick_next_user_agent(self) -> str:
        """
        USER_AGENTS listesinden daha önce kullanılmayan bir UA seçer.
        Tüm UA'lar tüketildiyse listeyi sıfırlar.
        """
        import random
        available = [ua for ua in USER_AGENTS if ua not in self._used_uas]
        if not available:
            self._used_uas.clear()
            available = [ua for ua in USER_AGENTS if ua != self._current_ua]
        if not available:
            available = USER_AGENTS
        ua = random.choice(available)
        self._used_uas.append(ua)
        self._current_ua = ua
        return ua

    def restart_with_new_user_agent(self) -> bool:
        """
        Yeni bir user-agent seçerek tarayıcıyı yeniden başlatır.
        Content error / captcha sonrası çağrılır.
        """
        self._pick_next_user_agent()
        logger.info(f"Yeni User Agent seçildi: {self._current_ua[:60]}...")
        return self.restart() is not None

    # ------------------------------------------------------------------ #
    #  Navigation
    # ------------------------------------------------------------------ #

    def get(self, url: str, wait_after: int = 3, max_retries: int = 2) -> bool:
        """
        URL'e git — UC mode (Cloudflare bypass) + otomatik CAPTCHA çözümü.
        CDP modu yok; ham driver.get() kullanılır (no asyncio deadlock riski).
        """
        breaker = get_circuit_breaker(
            'sciencedirect',
            failure_threshold=settings.cb_failure_threshold,
            recovery_timeout=settings.cb_recovery_timeout,
        )
        if not breaker.can_execute():
            logger.warning(
                "fetch_skipped_circuit_open",
                scraper='sciencedirect',
                url=url,
                retry_after=round(breaker.time_until_recovery, 1),
            )
            self.last_fetch = FetchResult(ok=False, error='circuit_open', error_kind='circuit_open')
            return False

        max_attempts = max(1, getattr(settings, 'retry_max', 2))
        backoff_base = getattr(settings, 'retry_backoff_base', 2)
        backoff_cap  = getattr(settings, 'retry_backoff_cap', 30)

        import time as _time
        _started = _time.perf_counter()

        for attempt in range(max_attempts):
            try:
                if self._raw_driver is None:
                    logger.warning("Driver aktif değil, başlatılıyor...")
                    if not self.start():
                        breaker.record_failure()
                        self.last_fetch = FetchResult(
                            ok=False, attempts=attempt + 1,
                            error='driver_start_failed', error_kind='fatal',
                        )
                        return False

                if attempt > 0:
                    logger.info(f"Yeniden deneniyor ({attempt}/{max_attempts - 1})...")

                logger.info(f"Açılıyor: {url}")

                try:
                    self._raw_driver.get(url)
                except Exception:
                    # page_load_strategy=eager/none → timeout normal, devam et
                    pass

                if wait_after > 0:
                    time.sleep(min(wait_after, 3))

                cf_solved = self._solve_cloudflare()
                if not cf_solved:
                    logger.warning(f"fetch_cf_unsolved scraper=sciencedirect url={url}")
                self._handle_cookie_consent()

                logger.success("Sayfa yüklendi")
                breaker.record_success()
                self.last_fetch = FetchResult(
                    ok=True,
                    attempts=attempt + 1,
                    duration_s=round(_time.perf_counter() - _started, 2),
                )
                logger.info(
                    "fetch_complete",
                    scraper='sciencedirect',
                    url=url,
                    duration_s=self.last_fetch.duration_s,
                    attempts=attempt + 1,
                )
                return True

            except Exception as e:
                error_str = str(e)
                is_conn_err = any(
                    err in error_str for err in [
                        'ERR_TUNNEL_CONNECTION_FAILED', 'ERR_PROXY_CONNECTION_FAILED',
                        'ERR_CONNECTION_REFUSED', 'ERR_CONNECTION_TIMED_OUT',
                        'net::ERR_', 'timeout', 'timed out',
                    ]
                )

                if is_conn_err and attempt < max_attempts - 1:
                    wait = min(backoff_base ** (attempt + 1), backoff_cap)
                    logger.warning(
                        "fetch_retry_backoff",
                        scraper='sciencedirect',
                        url=url,
                        attempt=attempt + 1,
                        backoff_s=round(wait, 1),
                    )
                    if not self.restart():
                        break
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"Sayfa yükleme hatası: {e}")
                    break

        breaker.record_failure()
        self.last_fetch = FetchResult(
            ok=False,
            attempts=max_attempts,
            duration_s=round(_time.perf_counter() - _started, 2),
            error_kind='fatal',
        )
        logger.error("fetch_failed", scraper='sciencedirect', url=url, attempts=max_attempts)
        return False

    # ------------------------------------------------------------------ #
    #  Screenshot
    # ------------------------------------------------------------------ #

    def take_screenshot(self, name: str = "screenshot") -> str:
        if not self._raw_driver:
            return ""
        try:
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = screenshots_dir / f"{name}_{timestamp}.png"
            self._raw_driver.save_screenshot(str(filepath))
            logger.info(f"Screenshot: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.warning(f"Screenshot hatası: {e}")
            return ""
