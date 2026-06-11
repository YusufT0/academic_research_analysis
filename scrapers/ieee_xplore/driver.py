"""
Selenium WebDriver management for IEEE Xplore scraper
"""

import time
import sys
import os
from datetime import datetime
from pathlib import Path
from selenium.webdriver.chrome.options import Options as ChromeOptions

# Selenium Wire import (proxy için)
try:
    from seleniumwire import webdriver as wire_webdriver
    from seleniumwire.undetected_chromedriver import Chrome as WireChrome
    SELENIUM_WIRE_AVAILABLE = True
except ImportError:
    SELENIUM_WIRE_AVAILABLE = False
    WireChrome = None

# Undetected ChromeDriver import (fallback)
import undetected_chromedriver as uc

sys.path.insert(0, str(__file__).rsplit('ieee_xplore', 1)[0])
from utils.logger import get_logger
logger = get_logger('ieee_xplore')

from .config import ProxyConfig, ARTICLE_READY_SELECTOR
import random

# Farklı User Agent'lar utils altından import ediliyor
from utils.user_agents import USER_AGENTS

# Yavaş internet optimizasyonu — paylaşımlı yardımcılar
from backend.core.config import settings
from utils.chrome_tuning import (
    apply_page_load_strategy,
    build_perf_prefs,
    perf_chrome_args,
    enable_cdp_request_blocking,
    blocked_url_patterns,
    maybe_emulate_slow_network,
)
from utils.network_probe import NetworkProbe, effective_page_load_timeout
from utils.resilient_fetch import resilient_get

class SeleniumDriver:
    """Selenium WebDriver'ı yöneten sınıf"""
    
    def __init__(self, proxy_config: ProxyConfig, headless: bool = False):
        """
        SeleniumDriver başlatıcı
        
        Args:
            proxy_config: ProxyConfig instance
            headless: Tarayıcı görünmez modda mı çalışsın
        """
        self.proxy_config = proxy_config
        self.headless = headless
        self.driver = None
        self.current_user_agent = None
        self._used_user_agents = []
        # Yavaş internet adaptasyonu için durum
        self.network_class = "fast"
        self.last_fetch = None

    def get_random_user_agent(self, exclude_current: bool = True) -> str:
        """Rastgele bir user agent seçer"""
        available_agents = USER_AGENTS.copy()
        
        if exclude_current and self.current_user_agent:
            if self.current_user_agent in available_agents:
                available_agents.remove(self.current_user_agent)
        
        for used_agent in self._used_user_agents:
            if used_agent in available_agents:
                available_agents.remove(used_agent)
        
        if not available_agents:
            available_agents = USER_AGENTS.copy()
            self._used_user_agents.clear()
            if self.current_user_agent in available_agents:
                available_agents.remove(self.current_user_agent)
        
        new_agent = random.choice(available_agents)
        self._used_user_agents.append(new_agent)
        
        return new_agent
    
    def _configure_chrome_options(self, use_uc: bool = False) -> ChromeOptions:
        """
        Chrome seçeneklerini yapılandır
        
        Args:
            use_uc: Undetected-chromedriver için mi (daha az seçenek)
        """
        options = ChromeOptions()
        
        if self.headless:
            # Yeni headless modu kullan (daha az tespit edilebilir)
            options.add_argument('--headless=new')
            # Headless modda gerçek bir pencere boyutu ayarla
            options.add_argument('--window-size=1920,1080')
            # Headless tespitini zorlaştıran ayarlar
            options.add_argument('--disable-blink-features=AutomationControlled')
            # WebGL ve Canvas fingerprint'i normal göster
            options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        
        # Performans ve güvenlik ayarları
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--log-level=3')
        
        # Bot tespitini zorlaştıran ek ayarlar (her zaman uygula)
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--start-maximized')
        options.add_argument('--lang=en-US,en')
        
        # SSL sertifika hatalarını her zaman yoksay
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')
        options.add_argument('--ignore-certificate-errors-spki-list')
        options.add_argument('--allow-insecure-localhost')
        options.add_argument('--disable-web-security')
        options.add_argument('--allow-running-insecure-content')
        
        # Proxy loopback (kendi selenium-wire proxy trafiği ile çakışmaması için)
        options.add_argument('--proxy-bypass-list=<-loopback>')

        # ── Yavaş internet optimizasyonu (her iki driver yolu için) ──
        apply_page_load_strategy(options, settings.page_load_strategy)
        if settings.block_resources_for('ieee'):
            for _arg in perf_chrome_args(block_images=settings.block_images):
                options.add_argument(_arg)
            try:
                options.add_experimental_option('prefs', build_perf_prefs(
                    block_images=settings.block_images,
                    block_fonts=settings.block_fonts,
                    block_media=settings.block_media,
                    block_stylesheets=settings.block_stylesheets,
                ))
            except Exception as e:
                logger.warning(f"prefs ayarlanamadı (CDP fallback aktif): {e}")

        # Undetected-chromedriver için
        if use_uc:
            return options
        
        # Normal Chrome için ek ayarlar
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # User agent (sadece normal Chrome için)
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Automation önleme (sadece normal Chrome için - UC ile uyumlu değil!)
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option('useAutomationExtension', False)
        
        return options
    
    def start(self) -> bool:
        """
        WebDriver'ı başlat
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.info("WebDriver başlatılıyor...")
            logger.info(f"  - Headless: {self.headless}")
            
            # Yeni User Agent seç
            self.current_user_agent = self.get_random_user_agent()
            logger.info(f"  - User Agent: {self.current_user_agent[:60]}...")
            
            # Her zaman undetected-chromedriver kullan
            options = self._configure_chrome_options(use_uc=True)
            # Selenium-wire options
            seleniumwire_options = {
                'verify_ssl': False,
                'suppress_connection_errors': True,
                'connection_timeout': 60,  # Proxy yavaşsa bağlantı kopmaması için artırıldı
                'connection_keep_alive': True # Bağlantıyı canlı tut
            }
            
            # Proxy varsa proxy ayarlarını ekle
            if self.proxy_config.use_proxy and self.proxy_config.is_configured():
                proxy_url = self.proxy_config.get_proxy_string()
                logger.info(f"Proxy kullanılıyor: {self.proxy_config.host}:{self.proxy_config.port}")
                logger.info(f"  - User: {self.proxy_config.user}")
                seleniumwire_options['proxy'] = {
                    'http': proxy_url,
                    'https': proxy_url,
                    'no_proxy': 'localhost,127.0.0.1'
                }
            else:
                logger.info("Proxy kullanılmıyor")
            
            # Sistemdeki Chrome versiyonunu tespit etmeye çalış
            import subprocess
            import re
            import sys
            
            client_version = None
            try:
                output = ""
                if sys.platform == "win32":
                    # Windows Chrome path'leri
                    paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                    ]
                    for path in paths:
                        if os.path.exists(path):
                            cmd = f'(Get-Item "{path}").VersionInfo.ProductVersion'
                            result = subprocess.run(["powershell", "-command", cmd], capture_output=True, text=True)
                            output = result.stdout.strip()
                            if output:
                                break
                elif sys.platform.startswith("linux"):
                    # Linux için komut satırından versiyon oku
                    for cmd_name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
                        try:
                            result = subprocess.run([cmd_name, "--version"], capture_output=True, text=True)
                            if result.stdout:
                                output = result.stdout.strip()
                                break
                        except Exception:
                            continue
                elif sys.platform == "darwin":
                    # macOS için
                    path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                    if os.path.exists(path):
                        result = subprocess.run([path, "--version"], capture_output=True, text=True)
                        output = result.stdout.strip()
                            
                if output:
                    match = re.search(r'(\d+)\.', output)
                    if match:
                        client_version = int(match.group(1))
                        logger.info(f"Oto-tespit edilen Chrome sürümü ({sys.platform}): {client_version}")
            except Exception as e:
                logger.debug(f"Chrome sürümü tespit edilemedi: {e}")
            
            # selenium-wire + undetected-chromedriver kullan (proxy desteği için)
            if SELENIUM_WIRE_AVAILABLE and WireChrome is not None:
                logger.info(f"  - Driver: selenium-wire + undetected-chromedriver (v{client_version or 'auto'})")
                try:
                    kwargs = {
                        "options": options,
                        "seleniumwire_options": seleniumwire_options
                    }
                    if client_version:
                        kwargs["version_main"] = client_version
                        
                    self.driver = WireChrome(**kwargs)
                    logger.success("selenium-wire + undetected-chromedriver aktif")
                except Exception as e:
                    logger.warning(f"WireChrome başlatılamadı, normal uc.Chrome deneniyor: {e}")
                    # Fallback: normal undetected-chromedriver (proxy çalışmayabilir)
                    # uc.ChromeOptions yeniden oluşturulmalı çünkü WireChrome içerde kullanılmış/tüketilmiş olabilir
                    fallback_options = self._configure_chrome_options(use_uc=True)
                    
                    fallback_kwargs = {
                        "options": fallback_options,
                        "use_subprocess": True
                    }
                    if client_version:
                        fallback_kwargs["version_main"] = client_version
                        
                    self.driver = uc.Chrome(**fallback_kwargs)
                    logger.warning("Normal undetected-chromedriver kullanılıyor (proxy desteği yok!)")
            else:
                logger.warning("selenium-wire bulunamadı, proxy desteği olmadan başlatılıyor")
                logger.info(f"  - Driver: undetected-chromedriver (proxy yok, v{client_version or 'auto'})")
                
                kwargs = {
                    "options": options,
                    "use_subprocess": True
                }
                if client_version:
                    kwargs["version_main"] = client_version
                    
                self.driver = uc.Chrome(**kwargs)
            
            # ── Adaptif timeout: ağ hızını ölç, timeout'u ölçekle ──
            try:
                self.network_class = NetworkProbe().measure_and_classify(self.driver)
            except Exception:
                self.network_class = "fast"
            eff_timeout = effective_page_load_timeout(
                settings.ieee_page_load_timeout, self.network_class
            )
            self.driver.set_page_load_timeout(eff_timeout)
            self.driver.implicitly_wait(settings.implicit_wait)
            logger.info(
                "page_load_timeout_set",
                effective_timeout=eff_timeout,
                network_class=self.network_class,
            )
            
            # Pencere boyutu
            self.driver.set_window_size(1920, 1080)
            
            # User Agent'ı CDP ile ayarla
            try:
                self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                    "userAgent": self.current_user_agent
                })
            except Exception as e:
                logger.warning(f"CDP User Agent ayarlanamadı: {e}")
            
            # Bot tespitini zorlaştıran JavaScript injection
            if self.headless:
                self._apply_stealth_scripts()

            # ── Kaynak engelleme (CDP — uc prefs'i strip etse de garanti yol) ──
            if settings.block_resources_for('ieee'):
                enable_cdp_request_blocking(
                    self.driver,
                    patterns=blocked_url_patterns(settings.blocked_url_patterns_csv),
                    block_images=settings.block_images,
                    block_fonts=settings.block_fonts,
                    block_media=settings.block_media,
                )
            # Yalnızca test/doğrulama: yavaş ağ emülasyonu (varsayılan kapalı)
            maybe_emulate_slow_network(self.driver, settings)

            logger.success("WebDriver başarıyla başlatıldı")
            return True
            
        except Exception as e:
            logger.failed("WebDriver başlatma hatası", e)
            import traceback
            traceback.print_exc()
            return False
    
    def _apply_stealth_scripts(self):
        """
        Headless modda bot tespitini zorlaştıran JavaScript kodlarını uygula
        """
        try:
            # navigator.webdriver özelliğini gizle
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    // webdriver özelliğini gizle
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // plugins dizisini doldur
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // languages dizisini ayarla
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Chrome özelliğini ekle
                    window.chrome = {
                        runtime: {}
                    };
                    
                    // Permissions API'yi düzelt
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                '''
            })
            logger.info("Stealth scripts uygulandı (headless mod)")
        except Exception as e:
            logger.warning(f"Stealth scripts uygulanamadı: {e}")
    
    def close(self):
        """WebDriver'ı kapat"""
        if self.driver:
            try:
                logger.info("WebDriver kapatılıyor...")
                self.driver.quit()
                self.driver = None
                logger.success("WebDriver kapatıldı")
            except Exception as e:
                logger.warning(f"WebDriver kapatma hatası: {e}")
                self.driver = None
    
    def restart(self) -> bool:
        """
        WebDriver'ı kapatıp yeniden başlat
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.section("TARAYICI YENİDEN BAŞLATILIYOR")
            
            # Mevcut driver'ı kapat
            self.close()
            
            # Kısa bekleme
            time.sleep(2)
            
            # Yeni driver başlat
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
        """
        Ekran görüntüsü al
        
        Args:
            name: Screenshot dosya adı öneki
            
        Returns:
            str: Kaydedilen dosya yolu veya boş string
        """
        if not self.driver:
            logger.warning("Screenshot alınamadı: Driver aktif değil")
            return ""
            
        try:
            # Screenshots klasörünü oluştur
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            
            # Dosya adını oluştur (tarih-saat ile)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Screenshot al
            self.driver.save_screenshot(str(filepath))
            logger.info(f"📸 Screenshot kaydedildi: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            logger.warning(f"Screenshot alma hatası: {e}")
            return ""
    
    def get(self, url: str, wait_after: int = 3, max_retries: int = 2) -> bool:
        """
        Belirtilen URL'e git. Dayanıklı getirme (resilient_get) kullanır:
        - yavaş timeout → aynı driver'da artan timeout + backoff (RESTART YOK)
        - net::ERR_/session ölümü → driver restart
        - timeout'ta window.stop() + selector kontrolü ile kısmi sayfa kurtarma

        Geriye dönük imza korunur (bool döner). Detay için self.last_fetch.

        Args:
            url: Gidilecek URL
            wait_after: readyState beklemesi için taban (saniye)
            max_retries: KULLANILMIYOR — retry artık settings.retry_max ile merkezi
        """
        base_timeout = effective_page_load_timeout(
            settings.ieee_page_load_timeout,
            getattr(self, "network_class", "fast"),
        )
        result = resilient_get(
            self,
            url,
            expected_selector=ARTICLE_READY_SELECTOR,
            wait_after=wait_after,
            scraper_name="ieee",
            base_timeout=base_timeout,
        )
        self.last_fetch = result
        return result.ok
