"""
Rate limiting and retry logic for Science Direct scraper
"""

import sys
import time
import random

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')

from backend.core.config import settings


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
        
        # Random wait ayarları — .env SD_MIN_WAIT / SD_MAX_WAIT'den okunur
        self.min_wait = float(settings.sd_min_wait)
        self.max_wait = float(settings.sd_max_wait)
    
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
    
    # Cloudflare JS challenge başlık anahtar kelimeleri (çok dilli)
    CLOUDFLARE_TITLE_KEYWORDS = [
        "just a moment",        # İngilizce
        "bir dakika lütfen",    # Türkçe
        "lütfen bekleyin",      # Türkçe alternatif
        "checking your browser",
        "please wait",
        "attention required",
        "bitte warten",         # Almanca
        "un moment",            # Fransızca
    ]

    def check_cloudflare(self) -> bool:
        """
        Cloudflare JS challenge sayfasını kontrol eder ('Bir dakika lütfen...' vb.)

        Returns:
            bool: Cloudflare challenge tespit edildiyse True
        """
        try:
            title = ""
            try:
                title = (self.driver.execute_script("return document.title") or "").lower()
            except Exception:
                pass

            if any(kw in title for kw in self.CLOUDFLARE_TITLE_KEYWORDS):
                logger.warning(f"CLOUDFLARE CHALLENGE TESPİT EDİLDİ! (başlık: '{title[:40]}')")
                return True

            # CF'ye özgü DOM elementleri
            cf_js = (
                "return !!(document.getElementById('cf-challenge-running') || "
                "document.querySelector('.cf-browser-verification') || "
                "document.querySelector('[data-cf-challenge]') || "
                "document.querySelector('div.cf-challenge-container'))"
            )
            try:
                if self.driver.execute_script(cf_js):
                    logger.warning("CLOUDFLARE CHALLENGE TESPİT EDİLDİ! (DOM elementi)")
                    return True
            except Exception:
                pass

            return False
        except Exception as e:
            logger.warning(f"  Cloudflare kontrolü hatası: {e}")
            return False

    def wait_for_cloudflare(self, timeout: int = 20) -> bool:
        """
        Cloudflare JS challenge'ın otomatik geçmesini bekler.
        undetected-chromedriver genellikle bunu otomatik çözer.

        Args:
            timeout: Maksimum bekleme süresi (saniye)

        Returns:
            bool: Challenge geçildiyse True, timeout olduysa False
        """
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException

        logger.warning(f"Cloudflare challenge bekleniyor (max {timeout}s)...")
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=0.5).until(
                lambda d: not self.check_cloudflare()
            )
            logger.success("Cloudflare challenge geçildi!")
            return True
        except (TimeoutException, Exception):
            logger.warning(f"Cloudflare challenge {timeout}s içinde geçilemedi")
            return False

    def check_captcha(self) -> bool:
        """
        ScienceDirect captcha / robot doğrulama sayfasını kontrol eder.

        Returns:
            bool: Captcha sayfası tespit edildiyse True
        """
        try:
            title = (self.driver.title or "").lower()
            if any(kw in title for kw in ["robot", "captcha", "human verification"]):
                logger.warning("CAPTCHA SAYFASI TESPİT EDİLDİ! (başlık)")
                return True

            page_text = (self.driver.page_source or "").lower()
            captcha_keywords = [
                "are you a robot",
                "please confirm you are a human",
                "completing the captcha challenge",
                "captcha challenge",
                "verify you are human",
            ]
            matched = [kw for kw in captcha_keywords if kw in page_text]
            if matched:
                logger.warning(f"CAPTCHA SAYFASI TESPİT EDİLDİ! ({matched[0]})")
                return True

            return False
        except Exception as e:
            logger.warning(f"  Captcha kontrolü hatası: {e}")
            return False

    def handle_captcha(self, url: str, wait_time: int = 30) -> bool:
        """
        Captcha sayfası tespit edildiğinde tarayıcıyı yeni user agent ile yeniden
        başlatır. undetected-chromedriver kullandığı için SeleniumBase yok;
        yeniden başlatma en güvenilir çözümdür.

        Args:
            url: Yeniden denecek URL
            wait_time: Yeniden başlatmadan önce kısa bekleme (saniye)

        Returns:
            bool: Başarılı ise True
        """
        logger.warning("=" * 60)
        logger.warning("CAPTCHA SAYFASI - YENİ USER AGENT İLE YENİDEN BAŞLATILIYOR")
        logger.warning("=" * 60)

        logger.info(f"  {wait_time} saniye bekleniyor...")
        time.sleep(wait_time)

        if self.selenium_driver:
            return self._restart_browser_and_retry(url)

        return False

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
    
    def handle_content_error(self, url: str, wait_time: int = 180, force_restart: bool = False) -> bool:
        """
        Content error sayfası tespit edildiğinde bekler ve tekrar dener.
        Başarısız olursa yeni user agent ile tarayıcıyı yeniden başlatır.
        Eğer force_restart True ise beklemenin ardından direkt yeni user agent ile başlatır.
        
        Args:
            url: Tekrar denenecek URL
            wait_time: Bekleme süresi (saniye) - varsayılan 3 dakika
            force_restart: Bekledikten sonra doğrudan tarayıcıyı yeniden başlat
            
        Returns:
            bool: Başarılı ise True, başarısız ise False
        """
        try:
            action_desc = "TARAYICI YENİDEN BAŞLATILACAK" if force_restart else f"{wait_time // 60} DAKİKA BEKLEME"
            if force_restart and wait_time < 60:
                action_desc = f"{wait_time} SANİYE BEKLEME VE YENİDEN BAŞLATMA"
                
            logger.section(f"CONTENT ERROR - {action_desc}")
            logger.info(f"ScienceDirect erişim sorunu tespit edildi, {wait_time} saniye bekleniyor...")
            
            # Geri sayım ile bekle
            remaining = wait_time
            while remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                logger.info(f"  ⏳ Kalan süre: {minutes:02d}:{seconds:02d}")
                
                sleep_interval = min(30, remaining)
                time.sleep(sleep_interval)
                remaining -= sleep_interval
            
            logger.success("Bekleme tamamlandı...")
            
            # Eğer force_restart True ise direkt tarayıcıyı yeniden başlatmayı dene
            if force_restart and self.selenium_driver:
                return self._restart_browser_and_retry(url)
            
            # force_restart False ise mevcut tarayıcıyla sayfayı yeniden yükle
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
            str: Hata türü ('cloudflare', 'captcha', 'rate_limit', 'content_error', 'none')
        """
        if self.check_cloudflare():
            return 'cloudflare'
        if self.check_captcha():
            return 'captcha'
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
