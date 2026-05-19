"""
Selenium WebDriver management for Springer Online Library scraper.

Uses SeleniumBase UC mode + CDP mode for:
1. Cloudflare bypass (undetected browsing)
2. Proxy authentication (CDP mode handles 407 auth internally)

Same architecture as ACM driver — CDP mode throughout for stealth.
"""

import time
import sys
import concurrent.futures
from datetime import datetime
from pathlib import Path

from seleniumbase import SB

# ── mycdp monkey-patch ────────────────────────────────────────────────────────
# mycdp 1.3.2 doesn't know about DOM.adoptedStyleSheetsModified (Chrome 115+).
# Without this patch every such CDP event causes a KeyError traceback.
try:
    import mycdp.util as _cdp_util
    _orig_parse = _cdp_util.parse_json_event

    def _safe_parse_json_event(json_dict):
        try:
            return _orig_parse(json_dict)
        except KeyError:
            return None  # Unknown CDP event — silently skip

    _cdp_util.parse_json_event = _safe_parse_json_event
except Exception:
    pass
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(__file__).rsplit('springer', 1)[0])
from utils.logger import get_logger
logger = get_logger('springer')

from .config import ProxyConfig

# Yavaş internet optimizasyonu — paylaşımlı yardımcılar (SB ailesi: CDP modu
# kullandığı için resilient_get DEĞİL; breaker + adaptif timeout + backoff).
from backend.core.config import settings
from backend.core.circuit_breaker import get_circuit_breaker
from utils.network_probe import NetworkProbe, effective_page_load_timeout
from utils.resilient_fetch import FetchResult
from utils.chrome_tuning import maybe_emulate_slow_network


class SeleniumDriver:
    """
    Selenium WebDriver yönetici sınıfı — Springer için.

    SeleniumBase SB (uc=True) + CDP mode kullanır.
    Her zaman CDP modu kullanılır (proxy olsun olmasın).
    Proxy, browser başlatılırken sb_kwargs["proxy"] ile Chrome'a verilir.
    """

    def __init__(self, proxy_config: ProxyConfig, headless: bool = False, page_load_timeout: int = 90):
        self.proxy_config = proxy_config
        self.headless = headless
        self.page_load_timeout = page_load_timeout
        self._base_page_load_timeout = page_load_timeout  # adaptif ölçekleme tabanı
        self.driver = None       # Underlying Selenium driver (sb.driver)
        self._sb = None          # SB instance
        self._sb_context = None  # SB context manager
        self._cdp_active = False
        # Yavaş internet adaptasyonu için durum
        self.network_class = "fast"
        self.last_fetch = None

    # ------------------------------------------------------------------ #
    #  Properties
    # ------------------------------------------------------------------ #

    @property
    def page_source(self) -> str:
        """Sayfa kaynağını döndür"""
        if self._cdp_active and self._sb:
            return self._sb.cdp.get_page_source()
        elif self.driver:
            return self.driver.page_source
        return ""

    @property
    def current_url(self) -> str:
        """Mevcut URL'i döndür"""
        if self._cdp_active and self._sb:
            return self._sb.cdp.get_current_url()
        elif self.driver:
            return self.driver.current_url
        return ""

    def execute_script(self, script: str):
        """JavaScript çalıştır"""
        try:
            if self._cdp_active and self._sb:
                expr = script.strip()
                if expr.startswith("return "):
                    expr = expr[len("return "):]
                return self._sb.cdp.evaluate(expr)
            elif self.driver:
                return self.driver.execute_script(script)
        except Exception as e:
            logger.warning(f"execute_script hatası: {e}")
        return None

    def _get_proxy_string(self) -> str:
        """SeleniumBase proxy format: user:pass@host:port"""
        return (
            f"{self.proxy_config.user}:{self.proxy_config.password}"
            f"@{self.proxy_config.host}:{self.proxy_config.port}"
        )

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        """WebDriver'ı başlat"""
        try:
            logger.info("WebDriver başlatılıyor (SeleniumBase UC + CDP mode)...")
            logger.info(f"  - Headless: {self.headless}")

            use_proxy = self.proxy_config.use_proxy and self.proxy_config.is_configured()

            sb_kwargs = {
                "uc": True,
                "test": True,
                "incognito": True,
                "locale_code": "en",
                # Yavaş internet: DOMContentLoaded'da devam (görseller beklenmez)
                "page_load_strategy": settings.page_load_strategy,
            }
            # SB-native görsel engelleme (yavaş hatta en büyük bant kazancı)
            if settings.block_resources_for('springer'):
                sb_kwargs["block_images"] = True

            if self.headless:
                sb_kwargs["headless"] = True

            if use_proxy:
                sb_kwargs["proxy"] = self._get_proxy_string()
                logger.info(f"  - Proxy: {self.proxy_config.host}:{self.proxy_config.port}")
                logger.info("  - Yöntem: UC + CDP mode (proxy auth + stealth)")
            else:
                logger.info("  - Proxy: Devre dışı")

            logger.info("  - User Agent: SeleniumBase otomatik (undetectable)")
            logger.info("  - Incognito: Evet")

            import os
            os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

            original_argv = sys.argv.copy()
            if "--quiet" not in sys.argv:
                sys.argv.append("--quiet")

            try:
                self._sb_context = SB(**sb_kwargs)
                self._sb = self._sb_context.__enter__()
                self.driver = self._sb.driver
                self._cdp_active = False

                # ── Adaptif timeout: ağ hızını ölç, timeout'u ölçekle ──
                try:
                    self.network_class = NetworkProbe().measure_and_classify(self.driver)
                except Exception:
                    self.network_class = "fast"
                self.page_load_timeout = effective_page_load_timeout(
                    self._base_page_load_timeout, self.network_class
                )
                self.driver.set_page_load_timeout(self.page_load_timeout)
                logger.info(
                    "page_load_timeout_set",
                    effective_timeout=self.page_load_timeout,
                    network_class=self.network_class,
                )
            finally:
                sys.argv = original_argv

            self.driver.set_window_size(1920, 1080)
            # Yalnızca test/doğrulama: yavaş ağ emülasyonu (varsayılan kapalı)
            maybe_emulate_slow_network(self.driver, settings)
            logger.success(f"WebDriver başarıyla başlatıldı {'(proxy ile)' if use_proxy else '(proxy yok)'}")
            return True

        except Exception as e:
            logger.error(f"WebDriver başlatma hatası: {e}")
            import traceback
            traceback.print_exc()
            return False

    def close(self):
        """WebDriver'ı kapat"""
        if self._sb_context:
            try:
                logger.info("WebDriver kapatılıyor...")
                self._sb_context.__exit__(None, None, None)
            except OSError:
                pass
            except Exception as e:
                logger.warning(f"WebDriver kapatma hatası: {e}")
            finally:
                self._sb = None
                self._sb_context = None
                self.driver = None
                self._cdp_active = False
                logger.success("WebDriver kapatıldı")
        elif self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def restart(self) -> bool:
        """WebDriver'ı kapatıp yeniden başlat"""
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
            return False

    def take_screenshot(self, name: str = "screenshot") -> str:
        """Ekran görüntüsü al — hata durumlarında debugging için"""
        if not self._sb:
            return ""
        try:
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = screenshots_dir / f"{name}_{timestamp}.png"
            if self._cdp_active:
                self._sb.cdp.save_screenshot(str(filepath))
            else:
                self.driver.save_screenshot(str(filepath))
            logger.info(f"📸 Screenshot: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.warning(f"Screenshot hatası: {e}")
            return ""

    # ------------------------------------------------------------------ #
    #  Page load helpers
    # ------------------------------------------------------------------ #

    def wait_for_page_load(self, timeout: int = 30) -> bool:
        """Sayfanın yüklenmesini bekle"""
        if self._cdp_active and self._sb:
            for _ in range(timeout * 2):
                try:
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.cdp.evaluate, "document.readyState")
                        state = future.result(timeout=2.0)
                        if state == "complete":
                            return True
                    except concurrent.futures.TimeoutError:
                        pass
                    finally:
                        executor.shutdown(wait=False)
                except Exception:
                    pass
                time.sleep(0.5)
            logger.warning("CDP: Sayfa yükleme timeout")
            return False
        elif self.driver:
            from selenium.webdriver.support.ui import WebDriverWait
            try:
                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                return True
            except Exception:
                logger.warning("Selenium: Sayfa yükleme timeout")
                return False
        return False

    def _get_title(self) -> str:
        """Mevcut sayfa başlığını döndür"""
        try:
            if self._cdp_active and self._sb:
                return self._sb.cdp.evaluate("document.title") or ""
            elif self.driver:
                return self.driver.title or ""
        except Exception:
            pass
        return ""

    def _solve_cloudflare(self) -> bool:
        """Cloudflare challenge kontrolü ve çözümü"""
        title = self._get_title()
        cf_keywords = ["just a moment", "checking", "lütfen", "moment"]

        if not any(kw in title.lower() for kw in cf_keywords):
            return True

        logger.info("Cloudflare challenge algılandı, bekleniyor...")
        time.sleep(10)
        title = self._get_title()

        if not any(kw in title.lower() for kw in cf_keywords):
            return True

        if self._sb:
            try:
                self._sb.solve_captcha()
                time.sleep(3)
                title = self._get_title()
                if not any(kw in title.lower() for kw in cf_keywords):
                    logger.success("Cloudflare solve_captcha() ile çözüldü")
                    return True
            except Exception as e:
                logger.warning(f"solve_captcha() hatası: {e}")

            try:
                self._sb.uc_gui_click_captcha()
                time.sleep(5)
                title = self._get_title()
                if not any(kw in title.lower() for kw in cf_keywords):
                    logger.success("Cloudflare uc_gui_click_captcha() ile çözüldü")
                    return True
            except Exception as e:
                logger.warning(f"uc_gui_click_captcha() hatası: {e}")

        logger.warning(f"Cloudflare geçilemedi (title: {title})")
        return False

    def _wait_for_render(self, url: str, max_attempts: int = 3) -> bool:
        """CSS/JS render kontrolü — yüklenmemişse yeniden dene"""
        if not (self._cdp_active and self._sb):
            return True

        CHECK_JS = """
        (function() {
            var cssRulesOk = Array.from(document.styleSheets).some(function(s) {
                try { return s.cssRules && s.cssRules.length > 50; }
                catch(e) { return false; }
            });
            var resources = window.performance.getEntriesByType('resource').length;
            var scripts = document.querySelectorAll('script[src]').length;
            return [cssRulesOk, resources, scripts];
        })()
        """

        for attempt in range(max_attempts):
            try:
                result = self._sb.cdp.evaluate(CHECK_JS)
                css_ok = bool(result[0]) if result else False
                resources = int(result[1]) if result else 0
                scripts = int(result[2]) if result else 0
                loaded = resources > 15 and (css_ok or scripts > 5)

                if loaded:
                    return True

                logger.warning(f"CSS/JS yüklenmedi (resources={resources}, scripts={scripts})")

                if attempt < max_attempts - 1:
                    logger.info(f"Sayfa yeniden yükleniyor ({attempt + 1}/{max_attempts - 1})...")
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.cdp.get, url)
                        future.result(timeout=self.page_load_timeout)
                    finally:
                        executor.shutdown(wait=False)
                    time.sleep(1.5)

            except Exception as e:
                logger.warning(f"Render kontrol hatası: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(1.5)

        logger.warning("CSS/JS render tamamlanamadı, devam ediliyor...")
        return False

    # ------------------------------------------------------------------ #
    #  Navigation
    # ------------------------------------------------------------------ #

    def get(self, url: str, wait_after: int = 3, max_retries: int = 2) -> bool:
        """
        Belirtilen URL'e git (her zaman CDP modu).

        İlk navigasyon: activate_cdp_mode(url) → CDP moduna geçer
        Sonraki navigasyonlar: sb.cdp.get(url) → CDP modunda kalır
        """
        breaker = get_circuit_breaker(
            'springer',
            failure_threshold=settings.cb_failure_threshold,
            recovery_timeout=settings.cb_recovery_timeout,
        )
        if not breaker.can_execute():
            logger.warning("fetch_skipped_circuit_open", scraper='springer', url=url,
                            retry_after=round(breaker.time_until_recovery, 1))
            self.last_fetch = FetchResult(ok=False, error='circuit_open',
                                          error_kind='circuit_open')
            return False

        max_attempts = max(1, settings.retry_max)
        backoff_base = settings.retry_backoff_base
        backoff_cap = settings.retry_backoff_cap
        _started = time.perf_counter()

        for attempt in range(max_attempts):
            try:
                if self._sb is None:
                    logger.warning("Driver aktif değil, başlatılıyor...")
                    if not self.start():
                        breaker.record_failure()
                        self.last_fetch = FetchResult(ok=False, attempts=attempt + 1,
                                                      error='driver_start_failed',
                                                      error_kind='fatal')
                        return False

                if attempt > 0:
                    logger.info(f"Yeniden deneniyor ({attempt}/{max_attempts - 1})...")

                logger.info(f"Açılıyor: {url}")

                if not self._cdp_active:
                    # İlk navigasyon — CDP modunu aktifleştir
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.activate_cdp_mode, url)
                        try:
                            future.result(timeout=self.page_load_timeout)
                            self._cdp_active = True
                        except concurrent.futures.TimeoutError:
                            raise TimeoutError(f"CDP activate_cdp_mode timeout: {url}")
                    finally:
                        executor.shutdown(wait=False)
                else:
                    # Sonraki navigasyonlar — CDP modunda kal
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.cdp.get, url)
                        try:
                            future.result(timeout=self.page_load_timeout)
                        except concurrent.futures.TimeoutError:
                            raise TimeoutError(f"CDP get timeout: {url}")
                    finally:
                        executor.shutdown(wait=False)

                time.sleep(0.5)
                self.wait_for_page_load(timeout=max(wait_after * 5, 15))
                self._solve_cloudflare()
                self._wait_for_render(url)

                logger.success("Sayfa yüklendi")
                breaker.record_success()
                self.last_fetch = FetchResult(
                    ok=True, attempts=attempt + 1,
                    duration_s=round(time.perf_counter() - _started, 2),
                )
                logger.info("fetch_complete", scraper='springer', url=url,
                            duration_s=self.last_fetch.duration_s, attempts=attempt + 1)
                return True

            except Exception as e:
                error_str = str(e)
                is_conn_err = isinstance(e, TimeoutError) or any(
                    err in error_str for err in [
                        'ERR_TUNNEL_CONNECTION_FAILED', 'ERR_PROXY_CONNECTION_FAILED',
                        'ERR_CONNECTION_REFUSED', 'ERR_CONNECTION_TIMED_OUT',
                        'net::ERR_', 'timeout', 'timed out',
                    ]
                )

                if is_conn_err and attempt < max_attempts - 1:
                    wait = min(backoff_base ** (attempt + 1), backoff_cap)
                    logger.warning("fetch_retry_backoff", scraper='springer', url=url,
                                   attempt=attempt + 1, backoff_s=round(wait, 1))
                    if not self.restart():
                        break
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"Sayfa yükleme hatası: {e}")
                    break

        breaker.record_failure()
        self.last_fetch = FetchResult(
            ok=False, attempts=max_attempts,
            duration_s=round(time.perf_counter() - _started, 2),
            error_kind='fatal',
        )
        logger.error("fetch_failed", scraper='springer', url=url, attempts=max_attempts)
        return False
