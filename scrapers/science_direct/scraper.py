"""
Main scraper class for Science Direct
"""

import os
import time
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import ProxyConfig, ScienceDirectConfig
from driver import SeleniumDriver
from navigation import PageNavigator
from parsers import JournalParser, ArticleParser
from rate_limiter import RateLimiter
from utils import handle_cookie_consent, print_article_summary


class ScienceDirectScraper:
    """Science Direct scraper ana sınıfı"""
    
    def __init__(self, use_proxy: bool = None, headless: bool = False, 
                 use_undetected: bool = True):
        """
        Science Direct scraper'ı başlatır
        
        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            use_undetected: undetected-chromedriver kullan (Cloudflare bypass)
        """
        self.config = ScienceDirectConfig()
        
        # Proxy kullanımı .env'den veya parametre ile belirlenir
        if use_proxy is None:
            use_proxy_env = os.getenv('USE_PROXY', 'false')
            use_proxy = use_proxy_env.lower() in ('true', '1', 'yes', 'on')
            print(f"ℹ .env'den USE_PROXY okundu: '{use_proxy_env}' -> {use_proxy}")
        
        # Proxy yapılandırması
        self.proxy_config = ProxyConfig() if use_proxy else None
        if use_proxy:
            if self.proxy_config and self.proxy_config.is_configured():
                print(f"✓ Proxy yapılandırması yüklendi:")
                print(f"  - Host: {self.proxy_config.proxy_host}")
                print(f"  - Port: {self.proxy_config.proxy_port}")
                print(f"  - User: {self.proxy_config.proxy_user}")
            else:
                print("⚠ Uyarı: Proxy bilgileri .env dosyasında bulunamadı!")
        else:
            print("ℹ Proxy kullanımı devre dışı")
        
        # Selenium driver
        self.selenium_driver = SeleniumDriver(self.proxy_config, headless, use_undetected)
        self.driver = None
        
        # Yardımcı sınıflar
        self.navigator = None
        self.rate_limiter = None
    
    def initialize(self):
        """Scraper'ı başlatır"""
        print("=" * 60)
        print("Science Direct Scraper Başlatılıyor...")
        print("=" * 60)
        
        self.driver = self.selenium_driver.start()
        self.navigator = PageNavigator(self.driver)
        self.rate_limiter = RateLimiter(self.driver)
        
        print(f"✓ Hedef URL: {self.config.base_url}")
    
    def navigate_to_journals(self) -> bool:
        """
        Science Direct journals sayfasına gider
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            print(f"\n→ Sayfa açılıyor: {self.config.base_url}")
            self.driver.get(self.config.base_url)
            
            # Cloudflare kontrolünü bekle
            print("⏳ Cloudflare kontrolü bekleniyor...")
            time.sleep(5)  # Cloudflare challenge için ek süre
            
            # Sayfanın yüklenmesini bekle
            WebDriverWait(self.driver, self.config.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            print(f"✓ Sayfa başarıyla yüklendi")
            print(f"  - Sayfa başlığı: {self.driver.title}")
            print(f"  - URL: {self.driver.current_url}")
            
            # Cloudflare challenge kontrolü
            if "challenge" in self.driver.current_url.lower() or "captcha" in self.driver.page_source.lower():
                print("⚠ Cloudflare challenge algılandı, bekleniyor...")
                time.sleep(10)  # Challenge'ın geçmesi için bekle
            
            # Kısa bekleme (sayfa tamamen render olsun)
            time.sleep(2)
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            return True
            
        except TimeoutException:
            print(f"✗ Sayfa yükleme zaman aşımı ({self.config.timeout}s)")
            return False
        except Exception as e:
            print(f"✗ Sayfa yükleme hatası: {e}")
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
            print("\n" + "=" * 60)
            print(f"🔍 '{search_term}' araması yapılıyor...")
            print("=" * 60)
            
            # URL'ye searchPhrase parametresini ekle
            from urllib.parse import urlencode
            search_url = f"{self.config.base_url}&searchPhrase={search_term}"
            
            print(f"\n→ Arama URL'si: {search_url}")
            self.driver.get(search_url)
            
            # Sayfanın yüklenmesini bekle
            print(f"⏳ Sayfa yükleniyor...")
            time.sleep(3)
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # Arama sonuçlarının yüklenmesini bekle
            print(f"⏳ Arama sonuçları bekleniyor...")
            time.sleep(2)
            
            # Sonuçları kontrol et
            print(f"→ Sonuçlar kontrol ediliyor...")
            
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
                        print(f"\n❌ '{search_term}' için sonuç bulunamadı")
                        return []
                    
                    print(f"\n✓ {len(journal_items)} sonuç bulundu!")
                    
                    # Sonuçları extract et
                    results = self.extract_journals_from_current_page()
                    
                    print("\n" + "=" * 60)
                    print(f"🔍 ARAMA SONUÇLARI: '{search_term}'")
                    print("=" * 60)
                    
                    for idx, journal in enumerate(results, 1):
                        print(f"\n{idx}. {journal['name']}")
                        print(f"   URL: {journal['url']}")
                        print(f"   Tip: {journal['type']}")
                        print(f"   Open Access: {'Evet' if journal['open_access'] else 'Hayır'}")
                        if journal['letter_group']:
                            print(f"   Grup: {journal['letter_group']}")
                    
                    print("\n" + "=" * 60)
                    
                    return results
                else:
                    print(f"\n❌ '{search_term}' için sonuç bulunamadı")
                    return []
                    
            except TimeoutException:
                print(f"\n❌ '{search_term}' için sonuç bulunamadı (publications-list yüklenemedi)")
                return []
            
        except Exception as e:
            print(f"\n✗ Arama hatası: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def extract_latest_articles_urls(self, journal_url: str) -> list:
        """
        Journal sayfasındaki 'latest-published-articles' div'inden makale URL'lerini çıkarır
        
        Args:
            journal_url: Journal'ın ana sayfası URL'i
            
        Returns:
            list: Makale URL'lerinin listesi
        """
        try:
            print(f"\n🔍 Latest articles alınıyor: {journal_url}")
            
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
            print(f"  ✗ Latest articles çıkarma hatası: {e}")
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
            print(f"\n📄 Makale detayları alınıyor: {article_url}")
            if retry_attempt > 0:
                print(f"  🔄 Deneme #{retry_attempt + 1}")
            
            # Makale sayfasına git
            full_url = f"https://www.sciencedirect.com{article_url}" if article_url.startswith('/') else article_url
            self.driver.get(full_url)
            time.sleep(3)
            
            # Rate limiting kontrolü
            if self.rate_limiter.check_rate_limiting():
                # İlk deneme ise 5 dakika bekle
                if retry_attempt == 0:
                    if self.rate_limiter.handle_rate_limiting_with_retry(full_url, wait_time=300):
                        # Başarılı, devam et
                        self.rate_limiter.reset_consecutive_failures()
                    else:
                        # Başarısız, listeye ekle
                        print(f"  ⚠ Makale retry listesine eklendi: {article_url}")
                        self.rate_limiter.add_to_retry_queue(article_url)
                        return None
                elif retry_attempt == 1:
                    # İkinci deneme başarısız
                    print(f"  ✗ Makale failed listesine eklendi: {article_url}")
                    self.rate_limiter.add_to_failed(article_url)
                    return None
                else:
                    # retry_attempt == 2 (son deneme)
                    # 5 dakika daha bekle
                    print(f"  ⚠ Son deneme rate limiting'e takıldı, 5 dakika bekleniyor...")
                    if self.rate_limiter.handle_rate_limiting_with_retry(full_url, wait_time=300):
                        # Başarılı, devam et
                        print(f"  ✓ Son deneme başarılı!")
                    else:
                        # Kalıcı başarısızlık
                        print(f"  ✗ Kalıcı başarısızlık")
                        self.rate_limiter.add_to_failed(article_url)
                        return None
            
            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)
            
            # Makale detaylarını parse et
            article_details = ArticleParser.extract_article_details(self.driver.page_source, article_url)
            
            return article_details
            
        except Exception as e:
            print(f"  ✗ Makale detay çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
            print("\n" + "=" * 80)
            print(f"📚 JOURNAL TARANMAYA BAŞLANIYOR: {journal_info['name']}")
            print("=" * 80)
            
            # 1. Latest articles URL'lerini al
            article_urls = self.extract_latest_articles_urls(journal_info['url'])
            
            if not article_urls:
                print(f"\n⚠ {journal_info['name']} için makale bulunamadı")
                return []
            
            # Max articles kontrolü
            if max_articles:
                article_urls = article_urls[:max_articles]
                print(f"\nℹ İlk {max_articles} makale taranacak")
            
            # 2. Her makale için detayları al
            all_articles = []
            
            for idx, article_url in enumerate(article_urls, 1):
                print(f"\n{'=' * 80}")
                print(f"📄 Makale {idx}/{len(article_urls)}")
                print(f"{'=' * 80}")
                
                article_details = self.extract_article_details(article_url)
                
                if article_details:
                    # Journal bilgisini ekle
                    article_details['journal_name'] = journal_info['name']
                    article_details['journal_url'] = journal_info['url']
                    
                    all_articles.append(article_details)
                    
                    # Başarılı, ardışık başarısızlık sayısını sıfırla
                    self.rate_limiter.reset_consecutive_failures()
                    
                    # Özet bilgi göster
                    print_article_summary(article_details, idx)
                else:
                    print(f"  ⚠ Makale detayları alınamadı")
                
                # Ardışık 5 başarısızlık kontrolü
                if self.rate_limiter.should_wait_for_failures():
                    self.rate_limiter.wait_for_failures()
                    
                    # Retry queue'daki makaleleri tekrar dene
                    retry_results = self._process_retry_queue()
                    all_articles.extend(retry_results)
                
                # Rate limiting
                time.sleep(2)
            
            # Son olarak kalan retry queue'yu işle
            if self.rate_limiter.retry_queue:
                print(f"\n📋 Kalan {len(self.rate_limiter.retry_queue)} makale retry queue'dan işleniyor...")
                retry_results = self._process_retry_queue()
                all_articles.extend(retry_results)
            
            # Failed articles'ı son bir kez dene
            if self.rate_limiter.failed_articles:
                print(f"\n{'=' * 80}")
                print(f"🔄 SON DENEME: Failed articles işleniyor ({len(self.rate_limiter.failed_articles)} makale)")
                print(f"{'=' * 80}")
                
                final_retry_results = self._process_failed_articles()
                all_articles.extend(final_retry_results)
            
            print("\n" + "=" * 80)
            print(f"✅ {journal_info['name']} TARAMASI TAMAMLANDI")
            print(f"📊 Toplam {len(all_articles)} makale toplandı")
            if self.rate_limiter.failed_articles:
                print(f"❌ {len(self.rate_limiter.failed_articles)} makale kalıcı olarak başarısız")
                print(f"   Başarısız makaleler:")
                for failed_url in self.rate_limiter.failed_articles:
                    print(f"   - {failed_url}")
            print("=" * 80)
            
            return all_articles
            
        except Exception as e:
            print(f"\n✗ Journal tarama hatası: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _process_retry_queue(self) -> list:
        """Retry queue'daki makaleleri işler"""
        results = []
        
        if not self.rate_limiter.retry_queue:
            return results
        
        print(f"\n{'=' * 80}")
        print(f"🔄 RETRY QUEUE İŞLENİYOR ({len(self.rate_limiter.retry_queue)} makale)")
        print(f"{'=' * 80}")
        
        # Kuyruğu kopyala ve temizle
        queue_copy = self.rate_limiter.retry_queue.copy()
        self.rate_limiter.retry_queue.clear()
        
        for idx, article_url in enumerate(queue_copy, 1):
            print(f"\n📄 Retry makale {idx}/{len(queue_copy)}: {article_url}")
            
            # İkinci deneme (retry_attempt=1)
            article_details = self.extract_article_details(article_url, retry_attempt=1)
            
            if article_details:
                results.append(article_details)
                print(f"  ✓ Başarılı!")
            else:
                print(f"  ✗ Yine başarısız, failed listesine eklendi")
            
            time.sleep(2)
        
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
            print(f"\n📄 Son deneme makale {idx}/{len(failed_copy)}: {article_url}")
            
            # Son deneme (retry_attempt=2)
            article_details = self.extract_article_details(article_url, retry_attempt=2)
            
            if article_details:
                results.append(article_details)
                print(f"  ✓ Başarılı! Makale kurtarıldı.")
            else:
                # Yine başarısız, kalıcı failed listesine ekle
                self.rate_limiter.failed_articles.append(article_url)
                print(f"  ✗ Kalıcı başarısızlık")
            
            time.sleep(3)  # Biraz daha uzun bekle son deneme için
        
        if results:
            print(f"\n✅ {len(results)} makale son denemede başarıyla kurtarıldı!")
        
        return results
    
    def scrape_all_journals(self) -> list:
        """Tüm sayfalardaki journal'ları tarar ve toplar"""
        print("\n" + "=" * 60)
        print("📚 Tüm Journal'lar Taranıyor...")
        print("=" * 60)
        
        all_journals = []
        page_count = 0
        
        while True:
            # Sayfa bilgilerini al
            page_info = self.navigator.get_current_page_info()
            current_page = page_info['current_page']
            total_pages = page_info['total_pages']
            
            print(f"\n{'=' * 60}")
            print(f"📄 Sayfa {current_page}/{total_pages} işleniyor...")
            print(f"{'=' * 60}")
            
            # Mevcut sayfadaki journal'ları çıkar
            journals = self.extract_journals_from_current_page()
            
            # Sonuçları ekle
            for journal in journals:
                all_journals.append(journal)
                print(f"  ✓ {journal['name']}")
                print(f"    - URL: {journal['url']}")
                print(f"    - Tip: {journal['type']}")
                print(f"    - Open Access: {'Evet' if journal['open_access'] else 'Hayır'}")
                print(f"    - Grup: {journal['letter_group']}")
            
            page_count += 1
            
            # Sonraki sayfa var mı kontrol et
            if not page_info['has_next']:
                print(f"\n✓ Son sayfaya ulaşıldı (Toplam {page_count} sayfa)")
                break
            
            # Sonraki sayfaya geç
            if not self.navigator.go_to_next_page():
                print("⚠ Sonraki sayfaya geçilemedi, tarama sonlandırılıyor")
                break
            
            # Sayfa yüklenmesini bekle
            time.sleep(2)
        
        print("\n" + "=" * 60)
        print(f"✅ Tarama Tamamlandı!")
        print(f"📊 Toplam {len(all_journals)} journal bulundu")
        print(f"📄 {page_count} sayfa tarandı")
        print("=" * 60)
        
        return all_journals
    
    def close(self):
        """Scraper'ı kapatır"""
        print("\n" + "=" * 60)
        self.selenium_driver.close()
        print("=" * 60)
