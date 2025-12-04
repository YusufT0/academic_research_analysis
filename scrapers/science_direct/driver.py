"""
Selenium WebDriver management for Science Direct scraper
"""

import sys
from typing import Optional
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

# Selenium Wire import (proxy için)
from seleniumwire import webdriver as wire_webdriver
from seleniumwire.undetected_chromedriver import Chrome as WireChrome
SELENIUM_WIRE_AVAILABLE = True

# Undetected ChromeDriver import
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')

from .config import ProxyConfig


class SeleniumDriver:
    """Selenium WebDriver yönetim sınıfı - Cloudflare bypass ve selenium-wire proxy desteği ile"""
    
    def __init__(self, proxy_config: Optional[ProxyConfig] = None, headless: bool = False, 
                 use_undetected: bool = True):
        """
        Selenium driver'ı başlatır
        
        Args:
            proxy_config: ProxyConfig nesnesi
            headless: Tarayıcıyı görünmez modda çalıştır
            use_undetected: undetected-chromedriver kullan (Cloudflare bypass için)
        """
        self.proxy_config = proxy_config
        self.headless = headless
        self.use_undetected = use_undetected and UNDETECTED_AVAILABLE
        self.use_wire = SELENIUM_WIRE_AVAILABLE and proxy_config and proxy_config.is_configured()
        self.driver = None
        
        if use_undetected and not UNDETECTED_AVAILABLE:
            logger.warning("undetected-chromedriver bulunamadı, normal Chrome kullanılacak")
            logger.info("  Cloudflare bypass için: pip install undetected-chromedriver")
        
        if proxy_config and proxy_config.is_configured() and not SELENIUM_WIRE_AVAILABLE:
            logger.warning("selenium-wire bulunamadı, proxy tam çalışmayabilir")
            logger.info("  Gelişmiş proxy desteği için: pip install selenium-wire")
    
    def _configure_chrome_options(self):
        """Chrome seçeneklerini yapılandırır"""
        if self.use_undetected:
            # undetected-chromedriver için minimal options
            chrome_options = uc.ChromeOptions()
            
            # Sadece temel ayarlar
            if self.headless:
                chrome_options.add_argument('--headless=new')
                logger.warning("Headless mod Cloudflare bypass'ı engelleyebilir")
            
            # Minimal argümanlar
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Proxy kullanılıyorsa SSL sertifika hatalarını yoksay
            if self.proxy_config and self.proxy_config.is_configured():
                proxy_string = self.proxy_config.get_proxy_string()
                chrome_options.add_argument(f'--proxy-server={proxy_string}')
                
                # SSL sertifika hatalarını yoksay (proxy için gerekli)
                chrome_options.add_argument('--ignore-certificate-errors')
                chrome_options.add_argument('--ignore-ssl-errors')
                chrome_options.add_argument('--allow-insecure-localhost')
                
                logger.success(f"Proxy yapılandırıldı: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
                logger.success("SSL sertifika doğrulaması devre dışı (proxy için)")
            
        else:
            # Normal selenium için tam options
            chrome_options = Options()
            
            # Headless mod
            if self.headless:
                chrome_options.add_argument('--headless=new')
            
            # Temel ayarlar
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--start-maximized')
            
            # Bot tespitini zorlaştıran ayarlar
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            chrome_options.add_argument('--lang=tr-TR')
            
            # User agent
            chrome_options.add_argument(
                'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Proxy ayarları - sadece normal Chrome için
            if self.proxy_config and self.proxy_config.is_configured():
                proxy_string = self.proxy_config.get_proxy_string()
                chrome_options.add_argument(f'--proxy-server={proxy_string}')
                
                # SSL sertifika hatalarını yoksay (proxy için gerekli)
                chrome_options.add_argument('--ignore-certificate-errors')
                chrome_options.add_argument('--ignore-ssl-errors')
                chrome_options.add_argument('--allow-insecure-localhost')
                
                logger.success(f"Proxy yapılandırıldı: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
                logger.success("SSL sertifika doğrulaması devre dışı (proxy için)")
            
            # Bildirimleri kapat
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_setting_values.geolocation": 2,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            }
            chrome_options.add_experimental_option("prefs", prefs)
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
        
        return chrome_options
    
    def start(self):
        """WebDriver'ı başlatır"""
        try:
            chrome_options = self._configure_chrome_options()
            
            # Selenium-wire proxy yapılandırması
            seleniumwire_options = {}
            if self.use_wire and self.proxy_config:
                proxy_url = f"http://{self.proxy_config.proxy_user}:{self.proxy_config.proxy_pass}@{self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}"
                seleniumwire_options = {
                    'proxy': {
                        'http': proxy_url,
                        'https': proxy_url,
                        'no_proxy': 'localhost,127.0.0.1'
                    },
                    # SSL sertifika doğrulamasını devre dışı bırak
                    'verify_ssl': False,
                    'suppress_connection_errors': True
                }
                logger.info("selenium-wire proxy yapılandırıldı:")
                logger.info(f"  - Host: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
                logger.info(f"  - User: {self.proxy_config.proxy_user}")
                logger.info("  - SSL doğrulama: Devre dışı")
            
            if self.use_undetected:
                # undetected-chromedriver kullan (Cloudflare bypass)
                logger.info("undetected-chromedriver kullanılıyor (Cloudflare bypass)")
                
                if self.use_wire:
                    # selenium-wire + undetected-chromedriver kombinasyonu
                    try:
                        self.driver = WireChrome(
                            options=chrome_options,
                            seleniumwire_options=seleniumwire_options,
                            version_main=142
                        )
                        logger.success("selenium-wire + undetected-chromedriver aktif")
                    except Exception as e:
                        logger.warning(f"selenium-wire hatası, normal undetected-chromedriver deneniyor: {e}")
                        self.driver = uc.Chrome(options=chrome_options, version_main=142)
                else:
                    # Sadece undetected-chromedriver
                    try:
                        self.driver = uc.Chrome(options=chrome_options, version_main=142)
                    except TypeError:
                        # Options ile sorun varsa, hiç options olmadan dene
                        logger.warning("Options ile hata, options olmadan deneniyor...")
                        self.driver = uc.Chrome(version_main=142)
                
            else:
                # Normal Selenium kullan
                logger.info("Normal Chrome WebDriver kullanılıyor")
                
                if self.use_wire:
                    # selenium-wire ile
                    self.driver = wire_webdriver.Chrome(
                        options=chrome_options,
                        seleniumwire_options=seleniumwire_options
                    )
                    logger.success("selenium-wire aktif")
                else:
                    # Normal selenium
                    from selenium import webdriver as normal_webdriver
                    self.driver = normal_webdriver.Chrome(options=chrome_options)
            
            self.driver.implicitly_wait(10)
            logger.success("Chrome WebDriver başarıyla başlatıldı")
            return self.driver
            
        except WebDriverException as e:
            logger.failed("WebDriver başlatma hatası", e)
            raise
    
    def close(self):
        """WebDriver'ı kapatır"""
        if self.driver:
            try:
                self.driver.quit()
                logger.success("WebDriver kapatıldı")
            except Exception as e:
                # Kapanma sırasında oluşan hataları görmezden gel
                logger.info("WebDriver kapatılırken küçük bir hata oluştu (görmezden gelindi)")
                pass
