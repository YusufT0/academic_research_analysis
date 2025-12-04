"""
Selenium WebDriver management for IEEE Xplore scraper
"""

import time
import sys
from selenium.webdriver.chrome.options import Options as ChromeOptions
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
            options.add_argument('--headless=new')
        
        # Performans ve güvenlik ayarları
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--log-level=3')
        
        # Undetected-chromedriver için minimal seçenekler
        if use_uc:
            # UC kendi automation ayarlarını yönetir
            return options
        
        # Normal Chrome için ek ayarlar
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # User agent (sadece normal Chrome için)
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Automation önleme (sadece normal Chrome için)
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
            
            # Her zaman undetected-chromedriver kullan
            options = self._configure_chrome_options(use_uc=True)
            
            # Proxy varsa seleniumwire_options ekle
            if self.proxy_config.is_configured():
                logger.info(f"Proxy kullanılıyor: {self.proxy_config.host}:{self.proxy_config.port}")
                
                seleniumwire_options = {
                    'proxy': {
                        'http': self.proxy_config.get_proxy_string(),
                        'https': self.proxy_config.get_proxy_string(),
                        'no_proxy': 'localhost,127.0.0.1'
                    },
                    'verify_ssl': False
                }
                
                # Undetected-chromedriver + selenium-wire
                self.driver = uc.Chrome(
                    options=options,
                    version_main=142,
                    use_subprocess=True,
                    seleniumwire_options=seleniumwire_options
                )
            else:
                logger.info("Proxy kullanılmıyor")
                
                # Sadece undetected-chromedriver
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
            
            logger.success("WebDriver başarıyla başlatıldı")
            return True
            
        except Exception as e:
            logger.failed("WebDriver başlatma hatası", e)
            import traceback
            traceback.print_exc()
            return False
    
    def close(self):
        """WebDriver'ı kapat"""
        if self.driver:
            try:
                logger.info("WebDriver kapatılıyor...")
                self.driver.quit()
                logger.success("WebDriver kapatıldı")
            except Exception as e:
                logger.warning(f"WebDriver kapatma hatası: {e}")
    
    def get(self, url: str, wait_after: int = 3) -> bool:
        """
        Belirtilen URL'e git
        
        Args:
            url: Gidilecek URL
            wait_after: Sayfa yüklendikten sonra bekleme süresi (saniye)
            
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.url(url, "Açılıyor")
            self.driver.get(url)
            time.sleep(wait_after)
            logger.success("Sayfa yüklendi")
            return True
        except Exception as e:
            logger.failed("Sayfa yükleme hatası", e)
            return False
