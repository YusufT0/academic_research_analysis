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

from .config import ProxyConfig


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
            
            # Her zaman undetected-chromedriver kullan
            options = self._configure_chrome_options(use_uc=True)
            
            # Selenium-wire options
            seleniumwire_options = {
                'verify_ssl': False,
                'suppress_connection_errors': True
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
            
            # selenium-wire + undetected-chromedriver kullan (proxy desteği için)
            if SELENIUM_WIRE_AVAILABLE and WireChrome is not None:
                logger.info("  - Driver: selenium-wire + undetected-chromedriver")
                try:
                    self.driver = WireChrome(
                        options=options,
                        seleniumwire_options=seleniumwire_options,
                        version_main=142
                    )
                    logger.success("selenium-wire + undetected-chromedriver aktif")
                except Exception as e:
                    logger.warning(f"WireChrome başlatılamadı, normal uc.Chrome deneniyor: {e}")
                    # Fallback: normal undetected-chromedriver (proxy çalışmayabilir)
                    self.driver = uc.Chrome(
                        options=options,
                        version_main=142,
                        use_subprocess=True
                    )
                    logger.warning("Normal undetected-chromedriver kullanılıyor (proxy desteği yok!)")
            else:
                logger.warning("selenium-wire bulunamadı, proxy desteği olmadan başlatılıyor")
                logger.info("  - Driver: undetected-chromedriver (proxy yok)")
                self.driver = uc.Chrome(
                    options=options,
                    version_main=142,
                    use_subprocess=True
                )
            
            # Timeout ayarları
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            
            # Pencere boyutu
            self.driver.set_window_size(1920, 1080)
            
            # Bot tespitini zorlaştıran JavaScript injection
            if self.headless:
                self._apply_stealth_scripts()
            
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
        Belirtilen URL'e git. Bağlantı hatası alınırsa driver'ı yeniden başlatarak tekrar dener.
        
        Args:
            url: Gidilecek URL
            wait_after: Sayfa yüklendikten sonra bekleme süresi (saniye)
            max_retries: Maksimum deneme sayısı (her denemede driver yeniden başlatılır)
            
        Returns:
            bool: Başarılı ise True
        """
        for attempt in range(max_retries + 1):
            try:
                # Driver yoksa başlat
                if self.driver is None:
                    logger.warning("Driver aktif değil, başlatılıyor...")
                    if not self.start():
                        logger.error("Driver başlatılamadı!")
                        return False
                
                if attempt > 0:
                    logger.info(f"Yeniden deneniyor ({attempt}/{max_retries})...")
                
                logger.url(url, "Açılıyor")
                self.driver.get(url)
                time.sleep(wait_after)
                logger.success("Sayfa yüklendi")
                return True
                
            except Exception as e:
                error_str = str(e)
                
                # Bağlantı hatalarını kontrol et
                is_connection_error = any(err in error_str for err in [
                    'ERR_TUNNEL_CONNECTION_FAILED',
                    'ERR_PROXY_CONNECTION_FAILED', 
                    'ERR_CONNECTION_REFUSED',
                    'ERR_CONNECTION_TIMED_OUT',
                    'ERR_NAME_NOT_RESOLVED',
                    'net::ERR_'
                ])
                
                if is_connection_error:
                    logger.failed("Sayfa yükleme hatası (bağlantı sorunu)", e)
                    
                    if attempt < max_retries:
                        logger.warning(f"Bağlantı hatası - driver yeniden başlatılarak tekrar denenecek...")
                        # Driver'ı kapat ve yeniden başlat
                        if not self.restart():
                            logger.error("Driver yeniden başlatılamadı!")
                            return False
                        time.sleep(2)  # Yeniden başlatma sonrası kısa bekleme
                        continue
                    else:
                        logger.error("Maksimum deneme sayısına ulaşıldı - bağlantı sorunu devam ediyor")
                        return False
                else:
                    logger.failed("Sayfa yükleme hatası", e)
                    return False
        
        return False
