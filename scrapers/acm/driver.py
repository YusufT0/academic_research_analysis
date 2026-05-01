"""
Selenium WebDriver management for ACM scraper

Uses SeleniumBase UC mode + CDP mode for:
1. Cloudflare bypass (undetected browsing)
2. Proxy authentication (CDP mode handles 407 auth internally)

Key design decisions (from SeleniumBase maintainer):
- Do NOT set custom user agent in UC mode (auto-set to undetectable agent)
- Use activate_cdp_mode() for proxy auth + stealth navigation
- Stay in CDP mode — never reconnect to Selenium (causes black screen)
- Use sb.cdp.get_page_source() / get_current_url() for data reads
- Use sb.cdp.get(url) for subsequent navigations after first activate_cdp_mode
- Use incognito=True for maximum anti-detection

SeleniumBase's rsplit patch (browser_launcher.py & browser.py) allows
@ in proxy username (e.g. user@domain.com:pass@host:port).
"""

import time
import sys
import concurrent.futures
from datetime import datetime
from pathlib import Path

from seleniumbase import SB

# ── mycdp monkey-patch ────────────────────────────────────────────────────────
# mycdp 1.3.2 doesn't know about DOM.adoptedStyleSheetsModified (Chrome 115+).
# Without this patch every such CDP event causes a KeyError traceback in
# seleniumbase's listener_loop, flooding the console with noise.
try:
    import mycdp.util as _cdp_util
    _orig_parse = _cdp_util.parse_json_event

    def _safe_parse_json_event(json_dict):
        try:
            return _orig_parse(json_dict)
        except KeyError:
            return None  # Unknown/unregistered CDP event — silently skip

    _cdp_util.parse_json_event = _safe_parse_json_event
except Exception:
    pass
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(__file__).rsplit('acm', 1)[0])
from utils.logger import get_logger
logger = get_logger('acm')

from .config import ProxyConfig


class SeleniumDriver:
    """
    Selenium WebDriver yönetici sınıfı.
    
    SeleniumBase SB (uc=True) + CDP mode kullanır.
    Her zaman CDP modu kullanılır (proxy olsun olmasın).
    Proxy, browser başlatılırken sb_kwargs["proxy"] ile Chrome'a verilir.
    
    page_source, current_url gibi veriler property olarak sunulur
    ve aktif moda göre doğru API kullanılır.
    """
    
    def __init__(self, proxy_config: ProxyConfig, headless: bool = False, page_load_timeout: int = 90):
        self.proxy_config = proxy_config
        self.headless = headless
        self.page_load_timeout = page_load_timeout
        self.driver = None  # Selenium WebDriver (sb.driver) — proxy yoksa kullanılır
        self._sb = None     # SB instance
        self._sb_context = None
        self._cdp_active = False  # CDP mode aktif mi?
    
    @property
    def page_source(self) -> str:
        """Sayfa kaynağını döndür (CDP veya Selenium moduna göre)"""
        if self._cdp_active and self._sb:
            return self._sb.cdp.get_page_source()
        elif self.driver:
            return self.driver.page_source
        return ""
    
    @property
    def current_url(self) -> str:
        """Mevcut URL'i döndür (CDP veya Selenium moduna göre)"""
        if self._cdp_active and self._sb:
            return self._sb.cdp.get_current_url()
        elif self.driver:
            return self.driver.current_url
        return ""
    
    def execute_script(self, script: str) -> any:
        """JavaScript çalıştır (CDP veya Selenium moduna göre)"""
        try:
            if self._cdp_active and self._sb:
                # CDP evaluate expression bekler; "return X" → "X" olarak normalize et
                expr = script.strip()
                if expr.startswith("return "):
                    expr = expr[len("return "):]
                return self._sb.cdp.evaluate(expr)
            elif self.driver:
                return self.driver.execute_script(script)
        except Exception as e:
            logger.warning(f"execute_script hatası (CDP/Selenium): {e}")
        return None
    
    def _get_proxy_string(self) -> str:
        """SeleniumBase proxy format: user:pass@host:port"""
        return (
            f"{self.proxy_config.user}:{self.proxy_config.password}"
            f"@{self.proxy_config.host}:{self.proxy_config.port}"
        )
    
    def start(self) -> bool:
        """
        WebDriver'ı başlat.
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.info("WebDriver başlatılıyor (SeleniumBase UC + CDP mode)...")
            logger.info(f"  - Headless: {self.headless}")
            
            use_proxy = self.proxy_config.use_proxy and self.proxy_config.is_configured()
            
            sb_kwargs = {
                "uc": True,
                "test": True,
                "incognito": True,
                "locale_code": "en",
            }
            
            if self.headless:
                sb_kwargs["headless"] = True
            
            if use_proxy:
                sb_kwargs["proxy"] = self._get_proxy_string()
                logger.info(f"  - Proxy: {self.proxy_config.host}:{self.proxy_config.port}")
                logger.info(f"  - User: {self.proxy_config.user}")
                logger.info("  - Yöntem: UC + CDP mode (proxy auth + stealth)")
            else:
                logger.info("  - Proxy: Devre dışı")
            
            logger.info("  - User Agent: SeleniumBase otomatik (undetectable)")
            logger.info("  - Incognito: Evet")
            
            import os
            # Suppress Pytest/SB verbose outputs
            os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
            
            # Add basic arguments to sys.argv temporarily if needed by SB to silence it
            original_argv = sys.argv.copy()
            if "--quiet" not in sys.argv:
                sys.argv.append("--quiet")
            
            try:
                # SB context manager'ı başlat
                self._sb_context = SB(**sb_kwargs)
                self._sb = self._sb_context.__enter__()
                
                # Underlying Selenium driver'ı al
                self.driver = self._sb.driver
                self._cdp_active = False

                # .env'den okunan timeout değerini uygula
                self.driver.set_page_load_timeout(self.page_load_timeout)
            finally:
                sys.argv = original_argv
            
            logger.success(f"SeleniumBase UC mode aktif {'(proxy ile)' if use_proxy else '(proxy yok)'}")
            
            # Pencere boyutu
            self.driver.set_window_size(1920, 1080)
            
            logger.success("WebDriver başarıyla başlatıldı")
            return True
            
        except Exception as e:
            logger.failed("WebDriver başlatma hatası", e)
            import traceback
            traceback.print_exc()
            return False
    
    def close(self):
        """WebDriver'ı kapat"""
        if self._sb_context:
            try:
                logger.info("WebDriver kapatılıyor...")
                self._sb_context.__exit__(None, None, None)
                self._sb = None
                self._sb_context = None
                self.driver = None
                self._cdp_active = False
                logger.success("WebDriver kapatıldı")
            except OSError:
                self._sb = None
                self._sb_context = None
                self.driver = None
                self._cdp_active = False
            except Exception as e:
                logger.warning(f"WebDriver kapatma hatası: {e}")
                self._sb = None
                self._sb_context = None
                self.driver = None
                self._cdp_active = False
        elif self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
    
    def restart(self) -> bool:
        """WebDriver'ı kapatıp yeniden başlat"""
        try:
            logger.section("TARAYICI YENİDEN BAŞLATILIYOR")
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
        """Ekran görüntüsü al"""
        if not self._sb:
            logger.warning("Screenshot alınamadı: Driver aktif değil")
            return ""
            
        try:
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            if self._cdp_active:
                self._sb.cdp.save_screenshot(str(filepath))
            else:
                self.driver.save_screenshot(str(filepath))
            logger.info(f"📸 Screenshot kaydedildi: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.warning(f"Screenshot alma hatası: {e}")
            return ""
    
    def wait_for_page_load(self, timeout: int = 30) -> bool:
        """Sayfanın yüklenmesini bekle (CDP veya Selenium moduna göre)"""
        if self._cdp_active and self._sb:
            # CDP modunda: polling ile readyState kontrol et
            # Her evaluate çağrısına ayrı timeout uygula — modal kapat / navigasyon
            # sonrası CDP bağlantısı askıya alınırsa sonsuz bloklanmayı önler.
            for _ in range(timeout * 2):
                try:
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.cdp.evaluate, "document.readyState")
                        state = future.result(timeout=2.0)
                        if state == "complete":
                            return True
                    except concurrent.futures.TimeoutError:
                        pass  # CDP evaluate askıda, sonraki iterasyonda tekrar dene
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
        """Mevcut sayfa başlığını döndürür (CDP veya Selenium moduna göre)."""
        try:
            if self._cdp_active and self._sb:
                return self._sb.cdp.evaluate("document.title") or ""
            elif self.driver:
                return self.driver.title or ""
        except Exception:
            pass
        return ""

    def _wait_for_render(self, url: str, max_attempts: int = 3) -> bool:
        """
        CSS/JS render kontrolü: sayfa tam render edilene kadar bekler/yeniden dener.

        Tespit yöntemi:
          1. cssRules: en az bir stylesheet'in gerçekten parse edilmiş rule'u var mı?
             (document.styleSheets.length yanıltıcıdır — <link> tag DOM'da olunca
              dosya fetch edilmese bile sheet nesnesi oluşur; cssRules.length ise
              ancak dosya gerçekten indirildiyse > 0 olur)
          2. resources: Performance API ile kaç ağ isteği yapıldı?
             (CSS/JS yüklendiyse Chrome 30+ istek yapar; kırık sayfada < 5 olur)

        Başarısız olursa sb.cdp.get(url) ile sayfayı yeniden yükler.

        Returns:
            bool: Render tamamlandıysa True, max_attempts sonunda hala yoksa False
        """
        if not (self._cdp_active and self._sb):
            return True  # CDP modu değilse kontrol gerekmiyor

        WAIT_BETWEEN = 1.5

        # Tek bir cdp.evaluate çağrısıyla iki metriği birden al (round-trip azalt)
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
                css_rules_ok   = bool(result[0]) if result else False
                resource_count = int(result[1]) if result else 0
                script_count   = int(result[2]) if result else 0

                # resource_count > 15: tarayıcı gerçekten CSS/JS/font istekleri yaptı
                # css_rules_ok veya script_count > 5: içerik gerçekten parse edildi
                loaded = resource_count > 15 and (css_rules_ok or script_count > 5)

                if loaded:
                    logger.info(
                        f"CSS/JS render OK "
                        f"(deneme {attempt + 1}, resources={resource_count}, "
                        f"scripts={script_count}, css_rules_ok={css_rules_ok})"
                    )
                    return True

                logger.warning(
                    f"CSS/JS yüklenmedi "
                    f"(resources={resource_count}, scripts={script_count}, css_rules_ok={css_rules_ok})"
                )

                if attempt < max_attempts - 1:
                    logger.info(f"Sayfa yeniden yükleniyor ({attempt + 1}/{max_attempts - 1})...")
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.cdp.get, url)
                        future.result(timeout=self.page_load_timeout)
                    finally:
                        executor.shutdown(wait=False)
                    time.sleep(WAIT_BETWEEN)

            except Exception as e:
                logger.warning(f"CSS/JS render kontrolü hatası: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(WAIT_BETWEEN)

        logger.warning(f"CSS/JS {max_attempts} denemede yüklenemedi, devam ediliyor...")
        return False

    def _solve_cloudflare(self) -> bool:
        """
        Cloudflare challenge kontrolü ve çözümü.

        Returns:
            bool: Sayfa hazır ise True
        """
        title = self._get_title()
        cf_keywords = ["lütfen", "moment", "checking", "just a"]

        if not any(kw in title.lower() for kw in cf_keywords):
            return True

        # İlk bekleme — çoğu challenge otomatik çözülür
        logger.info("Cloudflare challenge algılandı, bekleniyor...")
        time.sleep(8)
        title = self._get_title()

        if not any(kw in title.lower() for kw in cf_keywords):
            return True

        # CDP-native captcha çözücü
        logger.info("Cloudflare hala aktif, solve_captcha() deneniyor...")
        try:
            self._sb.solve_captcha()
            time.sleep(3)
            title = self._get_title()
            if not any(kw in title.lower() for kw in cf_keywords):
                logger.success("Cloudflare solve_captcha() ile çözüldü")
                return True
        except Exception as e:
            logger.warning(f"solve_captcha() hatası: {e}")

        # Fallback: uc_gui_click_captcha
        logger.info("Fallback: uc_gui_click_captcha() deneniyor...")
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
    
    def get(self, url: str, wait_after: int = 3, max_retries: int = 2) -> bool:
        """
        Belirtilen URL'e git (her zaman CDP modu).

        İlk navigasyon: activate_cdp_mode(url) → CDP moduna geçer
        Sonraki navigasyonlar: sb.cdp.get(url) → CDP modunda kalır

        Proxy, browser başlatılırken sb_kwargs["proxy"] ile ayarlanır;
        CDP seçimi proxy yönlendirmesini etkilemez.
        
        Args:
            url: Gidilecek URL
            wait_after: Sayfa yüklendikten sonra bekleme süresi (saniye)
            max_retries: Maksimum deneme sayısı
            
        Returns:
            bool: Başarılı ise True
        """
        for attempt in range(max_retries + 1):
            try:
                if self._sb is None:
                    logger.warning("Driver aktif değil, başlatılıyor...")
                    if not self.start():
                        logger.error("Driver başlatılamadı!")
                        return False
                
                if attempt > 0:
                    logger.info(f"Yeniden deneniyor ({attempt}/{max_retries})...")
                
                logger.url(url, "Açılıyor")
                
                # ── Her zaman CDP modu ───────────────────────────────────────
                # Proxy, browser başlatılırken sb_kwargs["proxy"] ile Chrome'a
                # verilir; CDP vs Selenium seçimi proxy yönlendirmesini etkilemez.
                # uc_open_with_reconnect WebDriver bağlantısını keserek JS runtime
                # state'ini mahveder → CSS/JS yüklenmez. CDP bu sorunu yaşamaz.
                if not self._cdp_active:
                    # İlk navigasyon: CDP modunu aktifleştir
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.activate_cdp_mode, url)
                        try:
                            future.result(timeout=self.page_load_timeout)
                            self._cdp_active = True
                        except concurrent.futures.TimeoutError:
                            raise TimeoutError(
                                f"CDP activate_cdp_mode timeout ({self.page_load_timeout}s): {url}"
                            )
                    finally:
                        executor.shutdown(wait=False)
                else:
                    # Sonraki navigasyonlar: CDP modunda kal
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = executor.submit(self._sb.cdp.get, url)
                        try:
                            future.result(timeout=self.page_load_timeout)
                        except concurrent.futures.TimeoutError:
                            raise TimeoutError(
                                f"CDP get timeout ({self.page_load_timeout}s): {url}"
                            )
                    finally:
                        executor.shutdown(wait=False)

                # CDP cdp.get() load event'i garanti etmez; readyState polling
                # ile mümkün olan en erken anda devam et
                time.sleep(0.5)  # CDP bağlantı stabilitesi için minimum buffer
                self.wait_for_page_load(timeout=max(wait_after * 5, 15))

                # CSS/JS render kontrolü — yüklenmemişse yeniden dene
                self._wait_for_render(url)

                cf_solved = self._solve_cloudflare()
                if not cf_solved:
                    logger.warning("Cloudflare geçilemedi, sayfa içeriği eksik olabilir")

                logger.success("Sayfa yüklendi")
                return True
                
            except Exception as e:
                error_str = str(e)
                is_connection_error = isinstance(e, TimeoutError) or any(err in error_str for err in [
                    'ERR_TUNNEL_CONNECTION_FAILED',
                    'ERR_PROXY_CONNECTION_FAILED',
                    'ERR_CONNECTION_REFUSED',
                    'ERR_CONNECTION_TIMED_OUT',
                    'ERR_NAME_NOT_RESOLVED',
                    'net::ERR_',
                    'timeout',
                    'timed out',
                ])
                
                if is_connection_error:
                    logger.failed("Sayfa yükleme hatası (bağlantı sorunu)", e)
                    if attempt < max_retries:
                        logger.warning("Bağlantı hatası - driver yeniden başlatılarak tekrar denenecek...")
                        if not self.restart():
                            logger.error("Driver yeniden başlatılamadı!")
                            return False
                        time.sleep(2)
                        continue
                    else:
                        logger.error("Maksimum deneme sayısına ulaşıldı")
                        return False
                else:
                    logger.failed("Sayfa yükleme hatası", e)
                    return False
        
        return False
