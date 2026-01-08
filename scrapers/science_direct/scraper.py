"""
Main scraper class for Science Direct
"""

import os
import sys
import time
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')

from .config import ProxyConfig, ScienceDirectConfig
from .driver import SeleniumDriver
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser
from .rate_limiter import RateLimiter
from .utils import handle_cookie_consent, print_article_summary


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass


class ScienceDirectScraper:
    """Science Direct scraper ana sınıfı"""
    
    def __init__(self, use_proxy: bool = None, headless: bool = False, 
                 use_undetected: bool = True, stop_flag=None):
        """
        Science Direct scraper'ı başlatır
        
        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            use_undetected: undetected-chromedriver kullan (Cloudflare bypass)
            stop_flag: threading.Event - durdurma sinyali için
        """
        self.stop_flag = stop_flag
        self.config = ScienceDirectConfig()
        
        # Proxy yapılandırması - her zaman oluştur, içinde USE_PROXY kontrolü var
        self.proxy_config = ProxyConfig()
        
        # use_proxy parametresi ile override edilebilir
        if use_proxy is not None:
            self.proxy_config.use_proxy = use_proxy
            logger.info(f"Proxy kullanımı parametre ile belirlendi: {use_proxy}")
        else:
            logger.info(f".env'den USE_PROXY okundu: {self.proxy_config.use_proxy}")
        
        # Proxy durumunu logla
        if self.proxy_config.use_proxy:
            if self.proxy_config.is_configured():
                logger.success("Proxy yapılandırması yüklendi:")
                logger.info(f"  - Host: {self.proxy_config.proxy_host}")
                logger.info(f"  - Port: {self.proxy_config.proxy_port}")
                logger.info(f"  - User: {self.proxy_config.proxy_user}")
            else:
                logger.warning("Uyarı: USE_PROXY=true ama proxy bilgileri eksik!")
        else:
            logger.info("Proxy kullanımı devre dışı")
        
        # Selenium driver
        self.selenium_driver = SeleniumDriver(self.proxy_config, headless, use_undetected)
        self.driver = None
        
        # Yardımcı sınıflar
        self.navigator = None
        self.rate_limiter = None
    
    def initialize(self):
        """Scraper'ı başlatır"""
        logger.header("Science Direct Scraper Başlatılıyor...")
        
        self.driver = self.selenium_driver.start()
        self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
        self.rate_limiter = RateLimiter(self.driver, selenium_driver=self.selenium_driver)
        
        logger.success(f"Hedef URL: {self.config.base_url}")
    
    def check_stop_flag(self):
        """Stop flag kontrol et, set ise exception fırlat"""
        if self.stop_flag and self.stop_flag.is_set():
            logger.warning("Stop sinyali alındı, scraper durduruluyor...")
            raise ScraperStoppedException("Scraper durduruldu")
    
    def navigate_to_journals(self, max_retries: int = 2) -> bool:
        """
        Science Direct journals sayfasına gider. Bağlantı hatası alınırsa driver'ı yeniden başlatarak tekrar dener.
        
        Args:
            max_retries: Maksimum deneme sayısı (her denemede driver yeniden başlatılır)
        
        Returns:
            bool: Başarılı ise True
        """
        for attempt in range(max_retries + 1):
            try:
                # Driver yoksa başlat
                if self.driver is None:
                    logger.warning("Driver aktif değil, başlatılıyor...")
                    self.driver = self.selenium_driver.start()
                    if self.driver is None:
                        logger.error("Driver başlatılamadı!")
                        return False
                    # Navigator ve rate_limiter'ı yeniden oluştur
                    self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
                    self.rate_limiter = RateLimiter(self.driver, selenium_driver=self.selenium_driver)
                
                if attempt > 0:
                    logger.info(f"Yeniden deneniyor ({attempt}/{max_retries})...")
                
                logger.step(1, 3, f"Sayfa açılıyor: {self.config.base_url}")
                self.driver.get(self.config.base_url)
                
                # Cloudflare kontrolünü bekle
                logger.loading("Cloudflare kontrolü bekleniyor")
                time.sleep(5)  # Cloudflare challenge için ek süre
                
                # Sayfanın yüklenmesini bekle
                WebDriverWait(self.driver, self.config.timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                logger.success("Sayfa başarıyla yüklendi")
                logger.info(f"  - Sayfa başlığı: {self.driver.title}")
                logger.info(f"  - URL: {self.driver.current_url}")
                
                # Cloudflare challenge kontrolü
                if "challenge" in self.driver.current_url.lower() or "captcha" in self.driver.page_source.lower():
                    logger.warning("Cloudflare challenge algılandı, bekleniyor...")
                    time.sleep(10)  # Challenge'ın geçmesi için bekle
                
                # Kısa bekleme (sayfa tamamen render olsun)
                time.sleep(2)
                
                # Cookie popup'ını kapat
                handle_cookie_consent(self.driver)
                
                return True
                
            except TimeoutException:
                logger.error(f"Sayfa yükleme zaman aşımı ({self.config.timeout}s)")
                if attempt < max_retries:
                    logger.warning("Timeout hatası - driver yeniden başlatılarak tekrar denenecek...")
                    self.driver = self.selenium_driver.restart()
                    if self.driver:
                        self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
                        self.rate_limiter = RateLimiter(self.driver, selenium_driver=self.selenium_driver)
                    time.sleep(2)
                    continue
                return False
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
                        self.driver = self.selenium_driver.restart()
                        if self.driver:
                            # Navigator ve rate_limiter'ı yeniden oluştur
                            self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
                            self.rate_limiter = RateLimiter(self.driver, selenium_driver=self.selenium_driver)
                        else:
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
    
    def extract_journals_from_current_page(self) -> list:
        """Mevcut sayfadaki journal bilgilerini çıkarır"""
        return JournalParser.extract_journals_from_page(self.driver.page_source)
    
    def search_journals(self, search_term: str) -> list:
        """
        Journal'lar içinde arama yapar (URL parametresi ile)
        
        Args:
            search_term: Aranacak kelime/terim
            
        Returns:
            list: Bulunan journal'ların listesi
        """
        try:
            logger.section(f"'{search_term}' araması yapılıyor...")
            
            # URL'ye searchPhrase parametresini ekle
            from urllib.parse import urlencode
            search_url = f"{self.config.base_url}&searchPhrase={search_term}"
            
            logger.url(search_url, "Arama URL'si")
            self.driver.get(search_url)
            
            # Sayfanın yüklenmesini bekle
            logger.loading("Sayfa yükleniyor")
            time.sleep(3)
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # Arama sonuçlarının yüklenmesini bekle
            logger.loading("Arama sonuçları bekleniyor")
            time.sleep(2)
            
            # Sonuçları kontrol et
            logger.info("Sonuçlar kontrol ediliyor...")
            
            # Publication list'i bul
            try:
                publication_list = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "publications-list"))
                )
                
                # Li elementlerini kontrol et
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                pub_list = soup.find('ul', class_='publications-list')
                
                if pub_list:
                    # Journal içeren li'leri say
                    journal_items = pub_list.find_all('li', class_='js-publication')
                    
                    if len(journal_items) == 0:
                        logger.error(f"'{search_term}' için sonuç bulunamadı")
                        return []
                    
                    logger.found(len(journal_items), "sonuç")
                    
                    # Sonuçları extract et
                    results = self.extract_journals_from_current_page()
                    
                    logger.section(f"ARAMA SONUÇLARI: '{search_term}'"  )
                    
                    for idx, journal in enumerate(results, 1):
                        logger.item(idx, len(results), journal['name'])
                        logger.info(f"   URL: {journal['url']}")
                        logger.info(f"   Tip: {journal['type']}")
                        logger.info(f"   Open Access: {'Evet' if journal['open_access'] else 'Hayır'}")
                        if journal['letter_group']:
                            logger.info(f"   Grup: {journal['letter_group']}")
                    
                    logger.separator()
                    
                    return results
                else:
                    logger.error(f"'{search_term}' için sonuç bulunamadı")
                    return []
                    
            except TimeoutException:
                logger.error(f"'{search_term}' için sonuç bulunamadı (publications-list yüklenemedi)")
                return []
            
        except Exception as e:
            logger.failed("Arama hatası", e)
            import traceback
            traceback.print_exc()
            return []
    
    def extract_latest_issue_articles(self, journal_url: str) -> tuple:
        """
        Journal sayfasından Latest Issue'ya gidip makale URL'lerini ve issue bilgilerini çıkarır
        
        Args:
            journal_url: Journal'ın ana sayfası URL'i
            
        Returns:
            tuple: (article_urls listesi, issue_info dict)
        """
        try:
            logger.info(f"Journal sayfası açılıyor: {journal_url}")
            
            # 1. Journal ana sayfasına git
            full_url = f"https://www.sciencedirect.com{journal_url}" if journal_url.startswith('/') else journal_url
            self.driver.get(full_url)
            time.sleep(3)
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # 2. Latest issue linkini al
            logger.info("  Latest issue linki aranıyor...")
            latest_issue_url = ArticleParser.extract_latest_issue_url(self.driver.page_source)
            
            if not latest_issue_url:
                logger.warning("  Latest issue linki bulunamadı, eski yönteme geçiliyor...")
                # Eski yöntem: latest-published-articles div'inden al
                article_urls = ArticleParser.extract_article_urls(self.driver.page_source)
                return article_urls, {'volume': None, 'date': None, 'status': None}
            
            # 3. Latest issue sayfasına git
            full_issue_url = f"https://www.sciencedirect.com{latest_issue_url}" if latest_issue_url.startswith('/') else latest_issue_url
            logger.info(f"  Latest issue sayfasına gidiliyor: {full_issue_url}")
            self.driver.get(full_issue_url)
            time.sleep(3)
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # 4. Issue bilgilerini al (Volume, Date)
            logger.info("  Issue bilgileri alınıyor...")
            issue_info = ArticleParser.extract_issue_info(self.driver.page_source)
            
            # Issue URL'sini ekle (latest issue sayfasının URL'si)
            issue_info['url'] = self.driver.current_url
            logger.success(f"  Issue URL: {issue_info['url']}")
            
            # 5. Makale URL'lerini al
            logger.info("  Makale linkleri alınıyor...")
            article_urls = ArticleParser.extract_article_urls_from_issue(self.driver.page_source)
            
            return article_urls, issue_info
            
        except Exception as e:
            logger.failed("  Latest issue articles çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return [], {'volume': None, 'date': None, 'status': None}
    
    def extract_latest_articles_urls(self, journal_url: str) -> list:
        """
        Journal sayfasındaki 'latest-published-articles' div'inden makale URL'lerini çıkarır
        (Eski yöntem - geriye uyumluluk için korundu)
        
        Args:
            journal_url: Journal'ın ana sayfası URL'i
            
        Returns:
            list: Makale URL'lerinin listesi
        """
        try:
            logger.info(f"Latest articles alınıyor: {journal_url}")
            
            # Journal sayfasına git
            full_url = f"https://www.sciencedirect.com{journal_url}" if journal_url.startswith('/') else journal_url
            self.driver.get(full_url)
            time.sleep(3)
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # Article URL'lerini parse et
            article_urls = ArticleParser.extract_article_urls(self.driver.page_source)
            
            return article_urls
            
        except Exception as e:
            logger.failed("  Latest articles çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return []
    
    def extract_article_details(self, article_url: str, retry_attempt: int = 0) -> dict:
        """
        Makale sayfasından detaylı bilgileri çıkarır
        
        Args:
            article_url: Makale sayfasının URL'i
            retry_attempt: Kaçıncı deneme olduğu (0 = ilk deneme)
            
        Returns:
            dict: Makale detayları veya None
        """
        try:
            logger.info(f"Makale detayları alınıyor: {article_url}")
            if retry_attempt > 0:
                logger.info(f"  Deneme #{retry_attempt + 1}")
            
            # Makale sayfasına git
            full_url = f"https://www.sciencedirect.com{article_url}" if article_url.startswith('/') else article_url
            self.driver.get(full_url)
            time.sleep(3)
            
            # Content Error kontrolü ("There was a problem providing the content")
            if self.rate_limiter.check_content_error():
                logger.warning("Content error tespit edildi!")
                if retry_attempt == 0:
                    # İlk deneme - 3 dakika bekle (başarısız olursa yeni user agent ile tarayıcı açılır)
                    if self.rate_limiter.handle_content_error(full_url, wait_time=180):
                        # Başarılı - driver değişmiş olabilir, güncelle
                        self._update_driver_references()
                        self.rate_limiter.reset_consecutive_failures()
                    else:
                        # Başarısız, retry listesine ekle
                        self._update_driver_references()
                        logger.warning(f"  Makale retry listesine eklendi: {article_url}")
                        self.rate_limiter.add_to_retry_queue(article_url)
                        return None
                elif retry_attempt == 1:
                    # İkinci deneme - 3 dakika daha bekle
                    if self.rate_limiter.handle_content_error(full_url, wait_time=180):
                        self._update_driver_references()
                        self.rate_limiter.reset_consecutive_failures()
                    else:
                        self._update_driver_references()
                        logger.error(f"  Makale failed listesine eklendi: {article_url}")
                        self.rate_limiter.add_to_failed(article_url)
                        return None
                else:
                    # Son deneme başarısız
                    logger.error(f"  Kalıcı content error: {article_url}")
                    self.rate_limiter.add_to_failed(article_url)
                    return None
            
            # Rate limiting kontrolü
            if self.rate_limiter.check_rate_limiting():
                # İlk deneme ise 5 dakika bekle
                if retry_attempt == 0:
                    if self.rate_limiter.handle_rate_limiting_with_retry(full_url, wait_time=300):
                        # Başarılı, devam et
                        self.rate_limiter.reset_consecutive_failures()
                    else:
                        # Başarısız, listeye ekle
                        logger.warning(f"  Makale retry listesine eklendi: {article_url}")
                        self.rate_limiter.add_to_retry_queue(article_url)
                        return None
                elif retry_attempt == 1:
                    # İkinci deneme başarısız
                    logger.error(f"  Makale failed listesine eklendi: {article_url}")
                    self.rate_limiter.add_to_failed(article_url)
                    return None
                else:
                    # retry_attempt == 2 (son deneme)
                    # 5 dakika daha bekle
                    logger.warning("  Son deneme rate limiting'e takıldı, 5 dakika bekleniyor...")
                    if self.rate_limiter.handle_rate_limiting_with_retry(full_url, wait_time=300):
                        # Başarılı, devam et
                        logger.success("  Son deneme başarılı!")
                    else:
                        # Kalıcı başarısızlık
                        logger.error("  Kalıcı başarısızlık")
                        self.rate_limiter.add_to_failed(article_url)
                        return None
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # Makale detaylarını parse et
            article_details = ArticleParser.extract_article_details(self.driver.page_source, article_url)
            
            return article_details
            
        except Exception as e:
            logger.failed("  Makale detay çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return None
    
    def _update_driver_references(self):
        """
        Tarayıcı yeniden başlatıldığında driver referanslarını günceller
        """
        updated_driver = self.rate_limiter.get_updated_driver()
        if updated_driver != self.driver:
            logger.info("Driver referansları güncelleniyor...")
            self.driver = updated_driver
            self.navigator.driver = updated_driver
            logger.success("Driver referansları güncellendi")
    
    def scrape_journal_articles(self, journal_info: dict, max_articles: int = None) -> list:
        """
        Bir journal'ın tüm makalelerini tarar
        
        Args:
            journal_info: Journal bilgisi (name, url)
            max_articles: Maksimum taranacak makale sayısı (None ise hepsi)
            
        Returns:
            list: Makale detaylarının listesi
        """
        try:
            logger.header(f"JOURNAL TARANMAYA BAŞLANIYOR: {journal_info['name']}")
            
            # 1. Latest issue'ya git ve makale URL'lerini + issue bilgilerini al
            article_urls, issue_info = self.extract_latest_issue_articles(journal_info['url'])
            
            if not article_urls:
                logger.warning(f"{journal_info['name']} için makale bulunamadı")
                return []
            
            # Issue bilgilerini journal_info'ya ekle
            journal_info['latest_issue_number'] = issue_info.get('issue_number')
            journal_info['latest_issue_date'] = issue_info.get('date')
            journal_info['latest_issue_status'] = issue_info.get('status')
            journal_info['latest_issue_url'] = issue_info.get('url')
            
            logger.stats({
                'Issue Number': issue_info.get('issue_number', 'N/A'),
                'Date': issue_info.get('date', 'N/A'),
                'Status': issue_info.get('status', 'N/A'),
                'URL': issue_info.get('url', 'N/A')
            }, "Issue Bilgileri")
            
            # Max articles kontrolü
            if max_articles:
                article_urls = article_urls[:max_articles]
                logger.info(f"İlk {max_articles} makale taranacak")
            
            # 2. Her makale için detayları al
            all_articles = []
            
            for idx, article_url in enumerate(article_urls, 1):
                # Stop flag kontrolü - her makale öncesi
                self.check_stop_flag()
                
                logger.section(f"Makale {idx}/{len(article_urls)}")
                
                article_details = self.extract_article_details(article_url)
                
                if article_details:
                    # Journal ve Issue bilgilerini ekle
                    article_details['journal_name'] = journal_info['name']
                    article_details['journal_url'] = journal_info['url']
                    article_details['issue_number'] = issue_info.get('issue_number')
                    article_details['issue_date'] = issue_info.get('date')
                    
                    all_articles.append(article_details)
                    
                    # Başarılı, ardışık başarısızlık sayısını sıfırla
                    self.rate_limiter.reset_consecutive_failures()
                    
                    # Özet bilgi göster
                    print_article_summary(article_details, idx)
                else:
                    logger.warning("  Makale detayları alınamadı")
                
                # Ardışık 5 başarısızlık kontrolü
                if self.rate_limiter.should_wait_for_failures():
                    self.rate_limiter.wait_for_failures()
                    
                    # Retry queue'daki makaleleri tekrar dene
                    retry_results = self._process_retry_queue()
                    all_articles.extend(retry_results)
                
                # Random bekleme (rate limiting önleme)
                self.rate_limiter.random_wait()
            
            # Son olarak kalan retry queue'yu işle
            if self.rate_limiter.retry_queue:
                logger.info(f"Kalan {len(self.rate_limiter.retry_queue)} makale retry queue'dan işleniyor...")
                retry_results = self._process_retry_queue()
                all_articles.extend(retry_results)
            
            # Failed articles'ı son bir kez dene
            if self.rate_limiter.failed_articles:
                logger.section(f"SON DENEME: Failed articles işleniyor ({len(self.rate_limiter.failed_articles)} makale)")
                
                final_retry_results = self._process_failed_articles()
                all_articles.extend(final_retry_results)
            
            logger.header(f"{journal_info['name']} TARAMASI TAMAMLANDI")
            logger.stats({
                'Toplam Makale': len(all_articles),
                'Issue': f"{issue_info.get('issue_number', 'N/A')} - {issue_info.get('date', 'N/A')}"
            })
            if self.rate_limiter.failed_articles:
                logger.error(f"{len(self.rate_limiter.failed_articles)} makale kalıcı olarak başarısız")
                logger.info("   Başarısız makaleler:")
                for failed_url in self.rate_limiter.failed_articles:
                    logger.info(f"   - {failed_url}")
            
            return all_articles
            
        except ScraperStoppedException:
            # Stop sinyali - yukarı fırlat
            logger.warning(f"{journal_info['name']}: Stop sinyali alındı")
            raise
        except Exception as e:
            logger.failed("Journal tarama hatası", e)
            import traceback
            traceback.print_exc()
            return []
    
    def _process_retry_queue(self) -> list:
        """Retry queue'daki makaleleri işler"""
        results = []
        
        if not self.rate_limiter.retry_queue:
            return results
        
        logger.section(f"RETRY QUEUE İŞLENİYOR ({len(self.rate_limiter.retry_queue)} makale)")
        
        # Kuyruğu kopyala ve temizle
        queue_copy = self.rate_limiter.retry_queue.copy()
        self.rate_limiter.retry_queue.clear()
        
        for idx, article_url in enumerate(queue_copy, 1):
            logger.item(idx, len(queue_copy), f"Retry makale: {article_url}")
            
            # İkinci deneme (retry_attempt=1)
            article_details = self.extract_article_details(article_url, retry_attempt=1)
            
            if article_details:
                results.append(article_details)
                logger.success("  Başarılı!")
            else:
                logger.error("  Yine başarısız, failed listesine eklendi")
            
            # Random bekleme
            self.rate_limiter.random_wait()
        
        return results
    
    def _process_failed_articles(self) -> list:
        """Failed articles listesindeki makaleleri son bir kez dener"""
        results = []
        
        if not self.rate_limiter.failed_articles:
            return results
        
        # Failed listesini kopyala
        failed_copy = self.rate_limiter.failed_articles.copy()
        
        # Geçici olarak temizle (başarısızlar tekrar eklenecek)
        self.rate_limiter.failed_articles.clear()
        
        for idx, article_url in enumerate(failed_copy, 1):
            logger.item(idx, len(failed_copy), f"Son deneme makale: {article_url}")
            
            # Son deneme (retry_attempt=2)
            article_details = self.extract_article_details(article_url, retry_attempt=2)
            
            if article_details:
                results.append(article_details)
                logger.success("  Başarılı! Makale kurtarıldı.")
            else:
                # Yine başarısız, kalıcı failed listesine ekle
                self.rate_limiter.failed_articles.append(article_url)
                logger.error("  Kalıcı başarısızlık")
            
            # Son deneme için biraz daha uzun random bekleme
            self.rate_limiter.random_wait(min_wait=3.0, max_wait=6.0)
        
        if results:
            logger.success(f"{len(results)} makale son denemede başarıyla kurtarıldı!")
        
        return results
    
    def scrape_all_journals(self) -> list:
        """Tüm sayfalardaki journal'ları tarar ve toplar"""
        logger.header("Tüm Journal'lar Taranıyor...")
        
        all_journals = []
        page_count = 0
        
        while True:
            # Stop flag kontrolü - her sayfa öncesi
            self.check_stop_flag()
            
            # Sayfa bilgilerini al
            page_info = self.navigator.get_current_page_info()
            current_page = page_info['current_page']
            total_pages = page_info['total_pages']
            
            logger.section(f"Sayfa {current_page}/{total_pages} işleniyor...")
            
            # Mevcut sayfadaki journal'ları çıkar
            journals = self.extract_journals_from_current_page()
            
            # Sonuçları ekle
            for journal in journals:
                all_journals.append(journal)
                logger.success(f"{journal['name']}")
                logger.info(f"    - URL: {journal['url']}")
                logger.info(f"    - Tip: {journal['type']}")
                logger.info(f"    - Open Access: {'Evet' if journal['open_access'] else 'Hayır'}")
                logger.info(f"    - Grup: {journal['letter_group']}")
            
            page_count += 1
            
            # Sonraki sayfa var mı kontrol et
            if not page_info['has_next']:
                logger.success(f"Son sayfaya ulaşıldı (Toplam {page_count} sayfa)")
                break
            
            # Sonraki sayfaya geç
            if not self.navigator.go_to_next_page():
                logger.warning("Sonraki sayfaya geçilemedi, tarama sonlandırılıyor")
                break
            
            # Sayfa yüklenmesini bekle
            time.sleep(2)
        
        logger.header("Tarama Tamamlandı!")
        logger.stats({
            'Toplam Journal': len(all_journals),
            'Taranan Sayfa': page_count
        })
        
        return all_journals
    
    def close(self):
        """Scraper'ı kapatır"""
        logger.separator()
        self.selenium_driver.close()
