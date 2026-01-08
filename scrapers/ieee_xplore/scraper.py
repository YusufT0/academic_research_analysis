"""
Main scraper class for IEEE Xplore
"""

import os
import sys
import time
from typing import Optional, List, Dict, Any
from pathlib import Path

# Parent directory'yi path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
logger = get_logger('ieee_xplore')

from .config import ProxyConfig, IEEEXploreConfig
from .driver import SeleniumDriver
from .utils import handle_cookie_consent, wait_for_page_load
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser
from .rate_limiter import IEEERateLimiter, RateLimitException


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass


class IEEEXploreScraper:
    """IEEE Xplore scraper ana sınıfı"""
    
    def __init__(self, use_proxy: bool = None, headless: bool = False, stop_flag=None):
        """
        IEEE Xplore scraper'ı başlatır
        
        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            stop_flag: threading.Event - durdurma sinyali için
        """
        self.stop_flag = stop_flag
        self.config = IEEEXploreConfig()
        
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
                logger.info(f"  - Host: {self.proxy_config.host}")
                logger.info(f"  - Port: {self.proxy_config.port}")
                logger.info(f"  - User: {self.proxy_config.user}")
            else:
                logger.warning("Uyarı: USE_PROXY=true ama proxy bilgileri eksik!")
        else:
            logger.info("Proxy kullanımı devre dışı")
        
        # Selenium driver
        self.selenium_driver = SeleniumDriver(self.proxy_config, headless=headless)
        self.driver = None
        self.headless = headless
        
        # Yardımcı sınıflar
        self.navigator = None
        self.rate_limiter = None
        
        # Veri tutucular
        self.all_journals: List[Dict[str, Any]] = []
    
    def check_stop_flag(self):
        """Stop flag kontrol et, set ise exception fırlat"""
        if self.stop_flag and self.stop_flag.is_set():
            logger.warning("Stop sinyali alındı, scraper durduruluyor...")
            raise ScraperStoppedException("Scraper durduruldu")
    
    def initialize(self):
        """Scraper'ı başlatır"""
        logger.header("IEEE Xplore Scraper Başlatılıyor...")
        
        if not self.selenium_driver.start():
            raise Exception("WebDriver başlatılamadı!")
        
        self.driver = self.selenium_driver.driver
        self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
        self.rate_limiter = IEEERateLimiter(self.driver, pause_duration=300)  # 5 dakika
        
        logger.success(f"Hedef URL: {self.config.base_url}")
    
    def navigate_to_journals(self, max_retries: int = 2) -> bool:
        """
        IEEE Xplore journals sayfasına gider
        
        Args:
            max_retries: Maksimum deneme sayısı
        
        Returns:
            bool: Başarılı mı
        """
        try:
            logger.url(self.config.base_url, "IEEE Xplore'a bağlanılıyor")
            
            if not self.selenium_driver.get(self.config.base_url, wait_after=3, max_retries=max_retries):
                logger.error("Sayfa yüklenemedi!")
                return False
            
            # Sayfanın tamamen yüklenmesini bekle
            logger.loading("Sayfa yükleniyor")
            wait_for_page_load(self.driver)
            time.sleep(2)
            
            logger.success("Sayfa hazır!")
            return True
            
        except Exception as e:
            logger.error(f"Journals sayfasına gidilemedi: {e}")
            return False
    
    def scrape_all_journals(self) -> List[Dict[str, Any]]:
        """
        Tüm sayfaları tarayarak journal listesini toplar
        
        Returns:
            List[Dict]: Journal bilgileri listesi
        """
        self.all_journals = []
        
        # Sayfa navigasyon bilgisini al
        page_info = self.navigator.get_current_page_info()
        
        current_page = 1
        total_pages = page_info['total_pages']
        
        logger.section(f"TOPLAM {total_pages} SAYFA TARANACAK")
        
        # Tüm sayfaları tara
        while True:
            # Stop flag kontrolü - her sayfa öncesi
            self.check_stop_flag()
            
            logger.subsection(f"Sayfa {current_page}/{total_pages} taranıyor")
            
            # Mevcut sayfadaki journal'ları parse et
            page_source = self.driver.page_source
            journals = JournalParser.extract_journals_from_page(page_source)
            self.all_journals.extend(journals)
            
            logger.found(len(journals), f"journal (Sayfa {current_page})")
            logger.info(f"Toplam: {len(self.all_journals)} journal")
            
            # Sayfa bilgisini güncelle
            page_info = self.navigator.get_current_page_info()
            
            # Sonraki sayfa var mı?
            if not page_info['has_next']:
                logger.success("Tüm sayfalar tarandı!")
                break
            
            # Sonraki sayfaya git
            logger.info(f"Sayfa {current_page + 1}'e geçiliyor...")
            if not self.navigator.go_to_next_page():
                logger.warning("Sonraki sayfaya geçilemedi!")
                break
            
            time.sleep(2)  # Rate limiting
            current_page += 1
        
        logger.section(f"TOPLAM {len(self.all_journals)} JOURNAL BULUNDU")
        return self.all_journals
    
    def scrape_journal_articles(
        self, 
        journal: Dict[str, Any], 
        max_articles: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Bir journal'ın makalelerini toplar
        
        Args:
            journal: Journal bilgileri
            max_articles: Maksimum toplanacak makale sayısı
            
        Returns:
            List[Dict]: Makale bilgileri listesi
            
        Raises:
            RateLimitException: Rate limit aşıldığında ve Science Direct'e geçiş gerektiğinde
        """
        articles = []
        
        journal_name = journal.get('name', 'Unknown')
        
        # Most recent issue URL'sini kullan
        issue_url = journal.get('most_recent_issue_url') or journal.get('url')
        
        if not issue_url:
            logger.warning(f"{journal_name}: URL bulunamadı, atlanıyor")
            return articles
        
        # Relative URL ise full URL yap
        if issue_url.startswith('/'):
            issue_url = f"https://ieeexplore.ieee.org{issue_url}"
        
        try:
            logger.url(issue_url, f"{journal_name} sayfasına gidiliyor")
            
            # Issue sayfasına git
            if not self.selenium_driver.get(issue_url, wait_after=3):
                logger.warning(f"{journal_name}: Sayfa yüklenemedi")
                return articles
            
            wait_for_page_load(self.driver)
            time.sleep(2)
            
            # Rate limit kontrolü (issue sayfasında)
            self.rate_limiter.check_and_handle_rate_limit()
            
            page_source = self.driver.page_source
            
            # Issue bilgilerini al ve journal'a ekle
            issue_info = ArticleParser.extract_issue_info(page_source)
            if issue_info:
                journal['issue_number'] = issue_info.get('issue_number')
                journal['issue_date'] = issue_info.get('date')
                journal['issue_url'] = issue_url
            
            # Makale URL'lerini al
            article_urls = ArticleParser.extract_article_urls(page_source)
            
            # Maksimum limitini uygula
            if len(article_urls) > max_articles:
                article_urls = article_urls[:max_articles]
            
            logger.info(f"{len(article_urls)} makale detayı toplanacak...")
            
            # Her makale için detay sayfasına git
            for idx, article_url in enumerate(article_urls, 1):
                # Stop flag kontrolü - her makale öncesi
                self.check_stop_flag()
                
                try:
                    # Full URL yap
                    if article_url.startswith('/'):
                        full_url = f"https://ieeexplore.ieee.org{article_url}"
                    else:
                        full_url = article_url
                    
                    logger.info(f"[{idx}/{len(article_urls)}] Makale detayı alınıyor...")
                    
                    if not self.selenium_driver.get(full_url, wait_after=2):
                        logger.warning(f"Makale sayfası yüklenemedi: {article_url}")
                        continue
                    
                    wait_for_page_load(self.driver)
                    time.sleep(1)
                    
                    # Rate limit kontrolü (her makale sayfasında)
                    # Bu exception fırlatabilir - RateLimitException
                    self.rate_limiter.check_and_handle_rate_limit()
                    
                    # Makale detaylarını parse et
                    article_page = self.driver.page_source
                    article_data = ArticleParser.extract_article_details(article_page, full_url)
                    
                    if article_data and article_data.get('title'):
                        articles.append(article_data)
                        logger.success(f"Makale eklendi: {article_data['title'][:50]}...")
                    
                    # Rate limiting
                    time.sleep(1)
                    
                except RateLimitException:
                    # Rate limit exception'ı yukarı fırlat
                    raise
                except ScraperStoppedException:
                    # Stop sinyali - yukarı fırlat
                    raise
                except Exception as e:
                    logger.warning(f"Makale {idx} hatası: {e}")
                    continue
            
            logger.found(len(articles), f"makale ({journal_name})")
            
        except RateLimitException:
            # Rate limit exception'ı yukarı fırlat
            logger.warning(f"{journal_name}: Rate limit nedeniyle durduruldu")
            raise
        except ScraperStoppedException:
            # Stop sinyali - yukarı fırlat
            logger.warning(f"{journal_name}: Stop sinyali alındı")
            raise
        except Exception as e:
            logger.error(f"{journal_name}: Makale toplama hatası: {e}")
        
        return articles
    
    def close(self):
        """Tarayıcıyı kapat"""
        try:
            if self.selenium_driver:
                self.selenium_driver.close()
            logger.info("Tarayıcı kapatıldı")
        except Exception as e:
            logger.warning(f"Tarayıcı kapatma hatası: {e}")
