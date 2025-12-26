"""
Rate limiting and retry logic for IEEE Xplore scraper
Detects download limit warnings and handles pausing/switching to alternative scraper
"""

import sys
import time
from typing import Callable, Optional
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

sys.path.insert(0, str(__file__).rsplit('ieee_xplore', 1)[0])
from utils.logger import get_logger
logger = get_logger('ieee_xplore')


class RateLimitException(Exception):
    """Rate limit aşıldığında ve Science Direct'e geçiş gerektiğinde fırlatılır"""
    pass


class IEEERateLimiter:
    """IEEE Xplore rate limiting ve retry yönetimi sınıfı"""
    
    # Rate limit uyarı div'inin class'ı
    ERROR_CONTAINER_CLASS = "error-message-container"
    ERROR_TEXT_KEYWORDS = [
        "reached the limit",
        "automatically paused access",
        "download"
    ]
    
    def __init__(self, driver, pause_duration: int = 300):
        """
        Args:
            driver: Selenium WebDriver instance
            pause_duration: Rate limit tespit edildiğinde bekleme süresi (saniye) - varsayılan 5 dakika
        """
        self.driver = driver
        self.pause_duration = pause_duration  # 5 dakika
        self.rate_limit_detected = False
        self.retry_count = 0
        self.max_retries = 1  # Bir kez bekleyip tekrar deneyecek, hala varsa Science Direct'e geçecek
        
    def check_rate_limiting(self) -> bool:
        """
        Sayfa içinde IEEE rate limit uyarısı var mı kontrol eder
        
        Returns:
            bool: Rate limiting varsa True, yoksa False
        """
        try:
            # error-message-container div'ini bul
            error_containers = self.driver.find_elements(
                By.CLASS_NAME, 
                self.ERROR_CONTAINER_CLASS
            )
            
            for container in error_containers:
                try:
                    text = container.text.lower()
                    
                    # Tüm anahtar kelimelerin olup olmadığını kontrol et
                    if all(keyword in text for keyword in self.ERROR_TEXT_KEYWORDS):
                        logger.warning("=" * 60)
                        logger.warning("IEEE XPLORE RATE LIMIT UYARISI TESPİT EDİLDİ!")
                        logger.warning("Mesaj: 'You have reached the limit of download'")
                        logger.warning("=" * 60)
                        self.rate_limit_detected = True
                        return True
                except:
                    continue
            
            return False
            
        except NoSuchElementException:
            return False
        except Exception as e:
            logger.warning(f"Rate limiting kontrolü hatası: {e}")
            return False
    
    def wait_and_retry(self) -> bool:
        """
        Rate limit tespit edildiğinde bekler ve tekrar dener
        
        Returns:
            bool: Rate limit kaldırıldıysa True, hala devam ediyorsa False
        """
        logger.section(f"RATE LIMIT - {self.pause_duration // 60} DAKİKA BEKLEME")
        logger.info(f"IEEE Xplore erişimi duraklatıldı, {self.pause_duration} saniye bekleniyor...")
        
        # Geri sayım ile bekle
        remaining = self.pause_duration
        while remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            logger.info(f"  ⏳ Kalan süre: {minutes:02d}:{seconds:02d}")
            
            # 30 saniyelik aralıklarla log bas
            sleep_interval = min(30, remaining)
            time.sleep(sleep_interval)
            remaining -= sleep_interval
        
        logger.success("Bekleme tamamlandı, sayfa yenileniyor...")
        
        # Sayfayı yenile
        try:
            self.driver.refresh()
            time.sleep(3)
            
            # Tekrar kontrol et
            if self.check_rate_limiting():
                logger.error("Rate limit hala devam ediyor!")
                return False
            else:
                logger.success("Rate limit kaldırıldı, taramaya devam ediliyor")
                self.rate_limit_detected = False
                self.retry_count = 0
                return True
                
        except Exception as e:
            logger.error(f"Sayfa yenileme hatası: {e}")
            return False
    
    def handle_rate_limit(self) -> bool:
        """
        Rate limit durumunu yönetir
        
        Returns:
            bool: Devam edilebilirse True, Science Direct'e geçiş gerekiyorsa False
        
        Raises:
            RateLimitException: Rate limit devam ediyorsa ve Science Direct'e geçiş gerekiyorsa
        """
        if not self.check_rate_limiting():
            return True
        
        self.retry_count += 1
        
        if self.retry_count <= self.max_retries:
            logger.info(f"Deneme {self.retry_count}/{self.max_retries}")
            
            if self.wait_and_retry():
                return True
        
        # Hala rate limit varsa Science Direct'e geçiş yap
        logger.error("=" * 60)
        logger.error("RATE LIMIT DEVAM EDİYOR!")
        logger.error("Science Direct scraper'a geçiş öneriliyor...")
        logger.error("=" * 60)
        
        raise RateLimitException(
            "IEEE Xplore rate limit aşıldı. "
            "Bekleme sonrasında da erişim sağlanamadı. "
            "Science Direct scraper'a geçiş yapılması önerilir."
        )
    
    def check_and_handle_rate_limit(self) -> bool:
        """
        Rate limit kontrolü yapar ve gerekirse işlem yapar
        
        Bu method her makale sayfası yüklendikten sonra çağrılmalıdır.
        
        Returns:
            bool: Devam edilebilirse True
            
        Raises:
            RateLimitException: Science Direct'e geçiş gerekiyorsa
        """
        return self.handle_rate_limit()
    
    def reset(self):
        """Rate limiter durumunu sıfırlar"""
        self.rate_limit_detected = False
        self.retry_count = 0
