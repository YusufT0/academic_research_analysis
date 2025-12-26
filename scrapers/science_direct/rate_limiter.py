"""
Rate limiting and retry logic for Science Direct scraper
"""

import sys
import time
import random

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')


class RateLimiter:
    """Rate limiting ve retry yönetimi sınıfı"""
    
    def __init__(self, driver, selenium_driver=None):
        """
        Args:
            driver: Selenium WebDriver instance
            selenium_driver: SeleniumDriver instance (tarayıcı yeniden başlatma için)
        """
        self.driver = driver
        self.selenium_driver = selenium_driver  # SeleniumDriver instance
        self.failed_articles = []  # Başarısız makaleler
        self.consecutive_failures = 0  # Ardışık başarısızlık sayısı
        self.retry_queue = []  # Tekrar denenecek makaleler
        self.browser_restart_count = 0  # Tarayıcı yeniden başlatma sayısı (bilgi amaçlı)
        
        # Random wait ayarları (saniye)
        self.min_wait = 2.0
        self.max_wait = 5.0
    
    def random_wait(self, min_wait: float = None, max_wait: float = None):
        """
        Random süre bekler (IEEE Xplore'daki gibi)
        
        Args:
            min_wait: Minimum bekleme süresi (saniye)
            max_wait: Maksimum bekleme süresi (saniye)
        """
        min_w = min_wait if min_wait is not None else self.min_wait
        max_w = max_wait if max_wait is not None else self.max_wait
        
        wait_time = random.uniform(min_w, max_w)
        logger.info(f"  ⏳ Random bekleme: {wait_time:.2f} saniye")
        time.sleep(wait_time)
    
    def check_rate_limiting(self) -> bool:
        """
        Sayfa rate limiting'e takılmış mı kontrol eder
        
        Returns:
            bool: Rate limiting varsa True, yoksa False
        """
        try:
            page_title = self.driver.title
            
            if "Request Temporarily Blocked" in page_title or "ScienceDirect Request Temporarily Blocked" in page_title:
                logger.warning("RATE LIMITING TESPİT EDİLDİ!")
                logger.info(f"  Sayfa başlığı: {page_title}")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"  Rate limiting kontrolü hatası: {e}")
            return False
    
    def check_content_error(self) -> bool:
        """
        "There was a problem providing the content you requested" hata sayfasını kontrol eder
        
        Returns:
            bool: Hata sayfası varsa True, yoksa False
        """
        try:
            page_source = self.driver.page_source.lower()
            page_title = self.driver.title.lower() if self.driver.title else ""
            
            # Hata sayfası içerik kontrolü
            error_indicators = [
                "there was a problem providing the content you requested",
                "contact our support team",
                "reference number:",
                "error-card"
            ]
            
            # En az 2 indicator bulunmalı
            found_count = sum(1 for indicator in error_indicators if indicator in page_source)
            
            if found_count >= 2:
                logger.warning("=" * 60)
                logger.warning("CONTENT ERROR SAYFASI TESPİT EDİLDİ!")
                logger.warning("'There was a problem providing the content you requested'")
                logger.warning("=" * 60)
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"  Content error kontrolü hatası: {e}")
            return False
    
    def handle_content_error(self, url: str, wait_time: int = 180) -> bool:
        """
        Content error sayfası tespit edildiğinde bekler ve tekrar dener.
        Başarısız olursa yeni user agent ile tarayıcıyı yeniden başlatır.
        
        Args:
            url: Tekrar denenecek URL
            wait_time: Bekleme süresi (saniye) - varsayılan 3 dakika
            
        Returns:
            bool: Başarılı ise True, başarısız ise False
        """
        try:
            logger.section(f"CONTENT ERROR - {wait_time // 60} DAKİKA BEKLEME")
            logger.info(f"ScienceDirect erişim sorunu tespit edildi, {wait_time} saniye ({wait_time // 60} dakika) bekleniyor...")
            
            # Geri sayım ile bekle
            remaining = wait_time
            while remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                logger.info(f"  ⏳ Kalan süre: {minutes:02d}:{seconds:02d}")
                
                sleep_interval = min(30, remaining)
                time.sleep(sleep_interval)
                remaining -= sleep_interval
            
            logger.success("Bekleme tamamlandı, sayfa yeniden deneniyor...")
            
            # Sayfayı yeniden yükle
            self.driver.get(url)
            time.sleep(3)
            
            # Cookie popup'ını kapat
            try:
                from .utils import handle_cookie_consent
                handle_cookie_consent(self.driver)
            except:
                pass
            
            # Tekrar content error kontrolü
            if self.check_content_error():
                logger.error("  Content error hala devam ediyor!")
                
                # Tarayıcıyı yeni user agent ile yeniden başlatmayı dene
                if self.selenium_driver:
                    return self._restart_browser_and_retry(url)
                else:
                    return False
            
            # Rate limiting kontrolü de yap
            if self.check_rate_limiting():
                logger.error("  Rate limiting tespit edildi!")
                return False
            
            logger.success("  Sayfa başarıyla yüklendi!")
            return True
            
        except Exception as e:
            logger.failed("  Content error işleme hatası", e)
            return False
    
    def _restart_browser_and_retry(self, url: str) -> bool:
        """
        Tarayıcıyı yeni user agent ile yeniden başlatıp sayfayı tekrar dener
        
        Args:
            url: Yüklenecek URL
            
        Returns:
            bool: Başarılı ise True
        """
        try:
            self.browser_restart_count += 1
            logger.section(f"TARAYICI YENİDEN BAŞLATILIYOR (#{self.browser_restart_count})")
            logger.info("Yeni User Agent ile tarayıcı başlatılıyor...")
            
            # Tarayıcıyı yeni user agent ile yeniden başlat
            if self.selenium_driver.restart_with_new_user_agent():
                # Driver referansını güncelle
                self.driver = self.selenium_driver.driver
                
                # Kısa bekleme
                time.sleep(2)
                
                # Sayfayı yükle
                logger.info(f"Sayfa yeniden yükleniyor: {url}")
                self.driver.get(url)
                time.sleep(5)  # Yeni tarayıcı için biraz daha uzun bekle
                
                # Cookie popup'ını kapat
                try:
                    from .utils import handle_cookie_consent
                    handle_cookie_consent(self.driver)
                except:
                    pass
                
                # Hata kontrolü
                if self.check_content_error():
                    logger.error("  Yeni tarayıcı ile de content error alındı!")
                    return False
                
                if self.check_rate_limiting():
                    logger.error("  Yeni tarayıcı ile rate limiting tespit edildi!")
                    return False
                
                logger.success("  Yeni tarayıcı ile sayfa başarıyla yüklendi!")
                return True
            else:
                logger.error("  Tarayıcı yeniden başlatılamadı!")
                return False
                
        except Exception as e:
            logger.error(f"  Tarayıcı yeniden başlatma hatası: {e}")
            return False
    
    def get_updated_driver(self):
        """
        Güncel driver referansını döndürür (tarayıcı yeniden başlatıldıysa)
        
        Returns:
            WebDriver: Güncel driver
        """
        return self.driver
    
    def check_all_errors(self) -> str:
        """
        Tüm hata türlerini kontrol eder
        
        Returns:
            str: Hata türü ('rate_limit', 'content_error', 'none')
        """
        if self.check_rate_limiting():
            return 'rate_limit'
        if self.check_content_error():
            return 'content_error'
        return 'none'
    
    def handle_rate_limiting_with_retry(self, url: str, wait_time: int = 300) -> bool:
        """
        Rate limiting durumunda bekler ve tekrar dener
        
        Args:
            url: Tekrar denenecek URL
            wait_time: Bekleme süresi (saniye) - varsayılan 5 dakika
            
        Returns:
            bool: Başarılı ise True, başarısız ise False
        """
        try:
            logger.loading(f"Rate limiting nedeniyle {wait_time} saniye ({wait_time//60} dakika) bekleniyor")
            
            # Geri sayım ile bekle
            for remaining in range(wait_time, 0, -30):
                minutes = remaining // 60
                seconds = remaining % 60
                logger.info(f"  Kalan süre: {minutes:02d}:{seconds:02d}")
                time.sleep(30)
            
            logger.info("Bekleme tamamlandı, sayfa yeniden deneniyor...")
            
            # Sayfayı yeniden yükle
            self.driver.get(url)
            time.sleep(3)
            
            # Cookie popup'ını kapat
            from utils import handle_cookie_consent
            handle_cookie_consent(self.driver)
            
            # Tekrar rate limiting kontrolü
            if self.check_rate_limiting():
                logger.error("  Rate limiting hala devam ediyor")
                return False
            
            logger.success("  Sayfa başarıyla yüklendi")
            return True
            
        except Exception as e:
            logger.failed("  Rate limiting işleme hatası", e)
            return False
    
    def add_to_retry_queue(self, article_url: str):
        """Retry queue'ya makale ekler"""
        self.retry_queue.append(article_url)
        self.consecutive_failures += 1
    
    def add_to_failed(self, article_url: str):
        """Failed listesine makale ekler"""
        self.failed_articles.append(article_url)
        self.consecutive_failures += 1
    
    def reset_consecutive_failures(self):
        """Ardışık başarısızlık sayısını sıfırlar"""
        self.consecutive_failures = 0
    
    def should_wait_for_failures(self) -> bool:
        """5 ardışık başarısızlık var mı kontrol eder"""
        return self.consecutive_failures >= 5
    
    def wait_for_failures(self):
        """5 ardışık başarısızlık sonrası 10 dakika bekler"""
        logger.warning("5 ardışık başarısızlık tespit edildi!")
        logger.loading("10 dakika bekleme başlatılıyor")
        
        # 10 dakika bekle
        for remaining in range(600, 0, -30):
            minutes = remaining // 60
            seconds = remaining % 60
            logger.info(f"  Kalan süre: {minutes:02d}:{seconds:02d}")
            time.sleep(30)
        
        logger.success("Bekleme tamamlandı")
        self.consecutive_failures = 0
