"""
Rate limiting and retry logic for Science Direct scraper
"""

import time


class RateLimiter:
    """Rate limiting ve retry yönetimi sınıfı"""
    
    def __init__(self, driver):
        """
        Args:
            driver: Selenium WebDriver instance
        """
        self.driver = driver
        self.failed_articles = []  # Başarısız makaleler
        self.consecutive_failures = 0  # Ardışık başarısızlık sayısı
        self.retry_queue = []  # Tekrar denenecek makaleler
    
    def check_rate_limiting(self) -> bool:
        """
        Sayfa rate limiting'e takılmış mı kontrol eder
        
        Returns:
            bool: Rate limiting varsa True, yoksa False
        """
        try:
            page_title = self.driver.title
            
            if "Request Temporarily Blocked" in page_title or "ScienceDirect Request Temporarily Blocked" in page_title:
                print(f"\n⚠ RATE LIMITING TESPİT EDİLDİ!")
                print(f"  Sayfa başlığı: {page_title}")
                return True
            
            return False
            
        except Exception as e:
            print(f"  ⚠ Rate limiting kontrolü hatası: {e}")
            return False
    
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
            print(f"\n⏳ Rate limiting nedeniyle {wait_time} saniye ({wait_time//60} dakika) bekleniyor...")
            
            # Geri sayım ile bekle
            for remaining in range(wait_time, 0, -30):
                minutes = remaining // 60
                seconds = remaining % 60
                print(f"  ⏱ Kalan süre: {minutes:02d}:{seconds:02d}")
                time.sleep(30)
            
            print(f"\n🔄 Bekleme tamamlandı, sayfa yeniden deneniyor...")
            
            # Sayfayı yeniden yükle
            self.driver.get(url)
            time.sleep(3)
            
            # Cookie popup'ını kapat
            from utils import handle_cookie_consent
            handle_cookie_consent(self.driver)
            
            # Tekrar rate limiting kontrolü
            if self.check_rate_limiting():
                print(f"  ✗ Rate limiting hala devam ediyor")
                return False
            
            print(f"  ✓ Sayfa başarıyla yüklendi")
            return True
            
        except Exception as e:
            print(f"  ✗ Rate limiting işleme hatası: {e}")
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
        print(f"\n⚠ 5 ardışık başarısızlık tespit edildi!")
        print(f"⏳ 10 dakika bekleme başlatılıyor...")
        
        # 10 dakika bekle
        for remaining in range(600, 0, -30):
            minutes = remaining // 60
            seconds = remaining % 60
            print(f"  ⏱ Kalan süre: {minutes:02d}:{seconds:02d}")
            time.sleep(30)
        
        print(f"\n🔄 Bekleme tamamlandı")
        self.consecutive_failures = 0
