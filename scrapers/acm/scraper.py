"""
Main scraper class for ACM Digital Library
"""

import os
import sys
import time
import random
from typing import Optional, List, Dict, Any
from pathlib import Path

# Parent directory'yi path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
logger = get_logger('acm')

from .config import ProxyConfig, ACMConfig
from .driver import SeleniumDriver
from .utils import handle_cookie_consent, handle_open_access_modal, wait_for_page_load
from .parsers import JournalParser, ArticleParser, ArticleDetailParser
from .navigation import PageNavigator


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass

class CloudflareBlockedException(Exception):
    """Cloudflare engeli aşılamadığında fırlatılır"""
    pass


class ACMScraper:
    """ACM Digital Library scraper ana sınıfı"""
    
    ACM_BASE = "https://dl.acm.org"
    
    def __init__(self, use_proxy: bool = None, headless: bool = False, stop_flag=None):
        """
        ACM scraper'ı başlatır
        
        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            stop_flag: threading.Event - durdurma sinyali için
        """
        self.stop_flag = stop_flag
        self.config = ACMConfig()
        
        # Proxy yapılandırması
        self.proxy_config = ProxyConfig()
        
        if use_proxy is not None:
            self.proxy_config.use_proxy = use_proxy
            logger.info(f"Proxy kullanımı parametre ile belirlendi: {use_proxy}")
        else:
            logger.info(f".env'den USE_PROXY okundu: {self.proxy_config.use_proxy}")
        
        if self.proxy_config.use_proxy:
            if self.proxy_config.is_configured():
                logger.success("Proxy yapılandırması yüklendi")
            else:
                logger.warning("Uyarı: USE_PROXY=true ama proxy bilgileri eksik!")
        else:
            logger.info("Proxy kullanımı devre dışı")
        
        # Selenium driver
        self.selenium_driver = SeleniumDriver(
            self.proxy_config,
            headless=headless,
            page_load_timeout=self.config.page_load_timeout,
        )
        self.headless = headless
        
        # Journal listesi
        self.all_journals = []
        
    def check_stop_flag(self):
        """Stop flag kontrol et, set ise exception fırlat"""
        if self.stop_flag and self.stop_flag.is_set():
            logger.warning("Stop sinyali alındı, scraper durduruluyor...")
            raise ScraperStoppedException("Scraper durduruldu")
    
    def initialize(self):
        """Scraper'ı başlatır"""
        logger.header("ACM Scraper Başlatılıyor...")
        
        if not self.selenium_driver.start():
            raise Exception("WebDriver başlatılamadı!")
        
        logger.success(f"Hedef URL: {self.config.base_url}")
    
    def _close_modals(self):
        """Cookie ve Open Access modallarını kapat"""
        handle_cookie_consent(self.selenium_driver, timeout=5)
        handle_open_access_modal(self.selenium_driver, timeout=5)
    
    def _random_wait(self):
        """Rate limiting için rastgele bekleme"""
        wait = random.uniform(self.config.min_wait, self.config.max_wait)
        logger.info(f"Rate limiting: {wait:.2f} saniye bekleniyor...")
        time.sleep(wait)
    
    def navigate_to_journals(self, max_retries: int = 2) -> bool:
        """
        ACM Journals sayfasına gider, modallari kapatır ve tüm journal'ları 
        yüklemek için sayfanın en altına kadar kaydırır (infinite scroll).
        
        Args:
            max_retries: Maksimum deneme sayısı
        
        Returns:
            bool: Başarılı mı
        """
        for attempt in range(max_retries + 1):
            try:
                logger.url(self.config.base_url, "ACM'e bağlanılıyor")
                
                if not self.selenium_driver.get(self.config.base_url, wait_after=5, max_retries=2):
                    logger.error("Sayfa yüklenemedi!")
                    if attempt < max_retries:
                        logger.warning("Yeniden deneniyor...")
                        self.selenium_driver.restart()
                        continue
                    return False
                
                # Sayfanın tamamen yüklenmesini bekle
                logger.loading("Sayfa yükleniyor")
                wait_for_page_load(self.selenium_driver)
                time.sleep(3)
                
                # Modalları kapat
                self._close_modals()
                
                # Kaydırma (Scrolling) İşlemi: Tüm dergileri yükle
                logger.info("Daha fazla dergi yüklemek için sayfa kaydırılıyor...")
                last_height = self.selenium_driver.execute_script("return document.body.scrollHeight")
                scroll_count = 0
                max_scrolls = 100 # Güvenlik limiti
                
                while scroll_count < max_scrolls:
                    self.check_stop_flag()
                    
                    # En alta kaydır
                    self.selenium_driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(5) # Yüklenmesi için bekle
                    
                    # Modallar tekrar çıkabilir
                    if scroll_count % 5 == 0:
                        self._close_modals()
                    
                    new_height = self.selenium_driver.execute_script("return document.body.scrollHeight")
                    
                    if new_height == last_height:
                        logger.info("Sayfa sonuna ulaşıldı, kontrol için tekrar bekleniyor...")
                        time.sleep(5)
                        final_height = self.selenium_driver.execute_script("return document.body.scrollHeight")
                        if final_height == last_height:
                            break
                    
                    last_height = new_height
                    scroll_count += 1
                    logger.info(f"Kaydırma {scroll_count} tamamlandı.")
                
                logger.success("Sayfa kaydırma tamamlandı, tüm liste hazır!")
                return True
                
            except ScraperStoppedException:
                raise
            except CloudflareBlockedException:
                raise
            except Exception as e:
                logger.error(f"Journals sayfasına gidilemedi: {e}")
                if attempt < max_retries:
                    logger.warning("Yeniden deneniyor (hata sebebiyle)...")
                    self.selenium_driver.restart()
                    continue
                return False
                
        return False
    
    def scrape_journals(self) -> list:
        """
        Mevcut sayfadaki journal listesini parse eder
        
        Returns:
            list: Journal bilgileri listesi
        """
        try:
            self.check_stop_flag()
            
            logger.section("JOURNAL LİSTESİ ALINIYOR")
            
            # Sayfa kaynağını al
            page_source = self.selenium_driver.page_source
            
            # Parser ile journal listesini çıkar
            self.all_journals = JournalParser.extract_journals_from_page(page_source)
            
            if self.all_journals:
                logger.success(f"{len(self.all_journals)} journal bulundu")
            else:
                logger.warning("Hiç journal bulunamadı!")
            
            return self.all_journals
            
        except ScraperStoppedException:
            raise
        except Exception as e:
            logger.failed("Journal listesi alınamadı", e)
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_issue_info_from_url(self, url: str) -> dict:
        """
        Issue URL'sinden volume/issue bilgisini çıkarır.
        Örnek: /toc/acmjcss/2025/3/4 -> volume=3, issue=4
        
        Args:
            url: Mevcut sayfa URL'i
            
        Returns:
            dict: {'issue_number': str, 'date': str, 'url': str}
        """
        import re
        issue_info = {'issue_number': None, 'date': None, 'url': url}
        
        # /toc/CODE/YEAR/VOLUME/ISSUE pattern
        match = re.search(r'/toc/\w+/(\d{4})/(\d+)/(\d+)', url)
        if match:
            year = match.group(1)
            volume = match.group(2)
            issue_num = match.group(3)
            issue_info['issue_number'] = f"Volume {volume}, Issue {issue_num}"
            issue_info['date'] = year
            return issue_info
        
        # /toc/CODE/current pattern
        match = re.search(r'/toc/\w+/current', url)
        if match:
            issue_info['issue_number'] = 'Current'
        
        return issue_info
    
    def scrape_journal_articles(
        self,
        journal: Dict[str, Any],
        max_articles: int = None,
        article_progress_callback=None,
        article_list_callback=None,
    ) -> List[Dict[str, Any]]:
        """
        Bir journal'ın son sayısındaki makaleleri toplar:
        1. Latest issue sayfasına git (/toc/CODE/current)
        2. Modalları kapat
        3. Makale URL'lerini parse et
        4. Her makale sayfasına gidip detayları topla
        
        Args:
            journal: Journal bilgileri dict'i
            max_articles: Maksimum toplanacak makale sayısı (None ise config'den)
            
        Returns:
            List[Dict]: Makale detay bilgileri listesi (DB uyumlu)
        """
        if max_articles is None:
            max_articles = self.config.max_articles
        
        journal_code = journal.get('code', '')
        journal_name = journal.get('name', 'Unknown')
        
        articles = []
        
        try:
            self.check_stop_flag()
            
            logger.section(f"JOURNAL İŞLENİYOR: {journal_name} ({journal_code})")
            
            # 1) Latest issue sayfasına doğrudan git ve Cloudflare kontrolü
            cf_blocked = False
            for attempt in range(2):
                if attempt > 0:
                    logger.warning("Cloudflare bloğu veya bağlantı hatası: Farklı bir tarayıcı oturumu ile tekrar deneniyor...")
                    if not self.selenium_driver.restart():
                        logger.error("Tarayıcı yeniden başlatılamadı!")
                        return articles
                    
                if not PageNavigator.navigate_to_latest_issue(self.selenium_driver, journal, wait_after=5):
                    logger.warning(f"{journal_name}: Latest issue sayfasına gidilemedi")
                    if attempt == 0:
                        continue
                    return articles
                
                # Cookie popup kapanmadan hemen önce sayfa title'ı kontrol et
                title = self.selenium_driver.execute_script("return document.title") or ""
                if "just a moment" in title.lower() or "checking your browser" in title.lower() or "cloudflare" in title.lower():
                    logger.warning(f"Cloudflare bloğu algılandı! Title: {title}")
                    if attempt == 0:
                        continue
                    logger.error("İkinci denemede de Cloudflare geçilemedi. İşlem başarısız sonlandırılıyor.")
                    raise CloudflareBlockedException("Cloudflare engeli aşılamadı (Just a moment...)")
                else:
                    break
            
            # 2) Modalları kapat (her sayfada çıkabiliyor)
            self._close_modals()
            
            # Sayfanın tamamen yüklenmesini bekle
            wait_for_page_load(self.selenium_driver)
            time.sleep(2)
            
            # Issue bilgisini URL'den çıkar ve journal'a ekle
            current_url = self.selenium_driver.current_url
            issue_info = self._extract_issue_info_from_url(current_url)
            journal['issue_number'] = issue_info.get('issue_number')
            journal['issue_date'] = issue_info.get('date')
            journal['issue_url'] = current_url
            
            # 3) Issue sayfasındaki makale URL'lerini parse et
            page_source = self.selenium_driver.page_source
            article_list = ArticleParser.extract_article_urls(page_source)
            
            if not article_list:
                logger.warning(f"{journal_name}: Makale bulunamadı")
                return articles
            
            # Max limit uygula
            if len(article_list) > max_articles:
                logger.info(f"Makale sayısı {len(article_list)} -> {max_articles} ile sınırlandı")
                article_list = article_list[:max_articles]
            
            logger.info(f"{len(article_list)} makale detayı toplanacak...")

            # Makale listesini (başlıklarla birlikte) UI'a bildir
            if article_list_callback:
                try:
                    article_list_callback([a.get('title', '') for a in article_list])
                except Exception:
                    pass

            # 4) Her makale için detay sayfasına git ve bilgileri topla
            retry_queue = []
            consecutive_failures = 0
            
            for idx, article_stub in enumerate(article_list, 1):
                self.check_stop_flag()

                # Makale başlamadan önce UI'a bildir (anlık güncelleme)
                if article_progress_callback:
                    try:
                        article_progress_callback(idx, len(article_list), None)
                    except Exception:
                        pass

                try:
                    article_url = article_stub.get('url', '')
                    
                    # Full URL yap
                    if article_url.startswith('/'):
                        full_url = f"{self.ACM_BASE}{article_url}"
                    else:
                        full_url = article_url
                    
                    logger.info(f"[{idx}/{len(article_list)}] Makale detayı alınıyor: {full_url}")
                    
                    article_data = None
                    success = False
                    
                    # Anında deneme (2 defa)
                    for attempt in range(2):
                        if attempt > 0:
                            logger.info(f"Makale tekrar deneniyor (Deneme {attempt+1})...")
                            # Küçük bir bekleme
                            time.sleep(2)
                        
                        # Makale sayfasına git
                        if not self.selenium_driver.get(full_url, wait_after=3):
                            logger.warning(f"Makale sayfası yüklenemedi: {article_url}")
                            continue
                        
                        wait_for_page_load(self.selenium_driver)
                        time.sleep(1)
                        
                        # Modalları kapat
                        self._close_modals()
                        
                        # Makale detaylarını parse et
                        article_page = self.selenium_driver.page_source
                        article_data = ArticleDetailParser.extract_article_details(article_page, full_url)
                        
                        if article_data and article_data.get('title'):
                            success = True
                            break
                    
                    if success and article_data:
                        articles.append(article_data)
                        logger.success(f"Makale eklendi: {article_data['title'][:50]}...")
                        consecutive_failures = 0
                    else:
                        logger.warning(f"Makale başarısız oldu, kuyruğa ekleniyor: {full_url}")
                        retry_queue.append(full_url)
                        consecutive_failures += 1

                    if article_progress_callback:
                        try:
                            article_progress_callback(idx, len(article_list), article_data.get('title') if (success and article_data) else None)
                        except Exception:
                            pass
                    
                    # Üst üste çok hata olursa soğuma & restart
                    if consecutive_failures >= 3:
                        logger.error("Üst üste 3 makale hatası! Koruma mekanizması devreye giriyor...")
                        logger.info("Tarayıcı tamamen yeniden başlatılacak ve 60 saniye beklenecek.")
                        self.selenium_driver.restart()
                        time.sleep(60)
                        consecutive_failures = 0
                        
                    # Rate limiting (Random Wait)
                    self._random_wait()
                    
                except ScraperStoppedException:
                    raise
                except CloudflareBlockedException:
                    raise
                except Exception as e:
                    logger.warning(f"Makale {idx} hatası: {e}")
                    consecutive_failures += 1
                    continue
            
            # 5) Kuyruktaki başarısız makaleleri son bir kez dene
            if retry_queue:
                logger.section(f"KUYRUK İŞLENİYOR: {len(retry_queue)} başarısız makale tekrar denenecek...")
                failed_permanently = []
                
                for idx, r_url in enumerate(retry_queue, 1):
                    self.check_stop_flag()
                    logger.info(f"[Kuyruk {idx}/{len(retry_queue)}] Deneniyor: {r_url}")
                    
                    try:
                        success = False
                        
                        if not self.selenium_driver.get(r_url, wait_after=3):
                            failed_permanently.append(r_url)
                            continue
                        
                        wait_for_page_load(self.selenium_driver)
                        time.sleep(1)
                        self._close_modals()
                        
                        article_page = self.selenium_driver.page_source
                        article_data = ArticleDetailParser.extract_article_details(article_page, r_url)
                        
                        if article_data and article_data.get('title'):
                            articles.append(article_data)
                            logger.success(f"Kuyruktan başarıyla kurtarıldı: {article_data['title'][:50]}...")
                        else:
                            failed_permanently.append(r_url)
                            logger.error("Makale kalıcı olarak başarısız oldu.")
                            
                        self._random_wait()
                        
                    except ScraperStoppedException:
                        raise
                    except CloudflareBlockedException:
                        raise
                    except Exception as e:
                        logger.warning(f"Kuyrukta hata: {e}")
                        failed_permanently.append(r_url)
                        continue
                        
                if failed_permanently:
                    logger.error(f"{len(failed_permanently)} makale kuyruktaki denemelere rağmen kurtarılamadı!")
            
            logger.found(len(articles), f"makale ({journal_name})")
            
        except (ScraperStoppedException, CloudflareBlockedException):
            raise
        except Exception as e:
            logger.error(f"{journal_name}: Makale toplama hatası: {e}")
            import traceback
            traceback.print_exc()
        
        return articles

    def process_article(self, article_url: str) -> Optional[Dict[str, Any]]:
        """
        Tek bir makale sayfasına gidip detayları toplar.
        
        Args:
            article_url: Makale URL'i (relative veya absolute)
            
        Returns:
            Dict: Makale detayları veya None
        """
        try:
            self.check_stop_flag()
            
            # Full URL yap
            if article_url.startswith('/'):
                full_url = f"{self.ACM_BASE}{article_url}"
            else:
                full_url = article_url
            
            logger.url(full_url, "Makale sayfasına gidiliyor...")
            
            # Makale sayfasına git
            if not self.selenium_driver.get(full_url, wait_after=3):
                logger.warning(f"Makale sayfası yüklenemedi: {article_url}")
                return None
            
            wait_for_page_load(self.selenium_driver)
            time.sleep(1)
            
            # Modalları kapat
            self._close_modals()
            
            # Makale detaylarını parse et
            page_source = self.selenium_driver.page_source
            article_data = ArticleDetailParser.extract_article_details(page_source, full_url)
            
            if article_data and article_data.get('title'):
                logger.success(f"Makale detayları alındı: {article_data['title'][:50]}...")
            
            # Rate limiting
            self._random_wait()
            
            return article_data
            
        except ScraperStoppedException:
            raise
        except Exception as e:
            logger.warning(f"Makale hatası: {e}")
            return None
    
    def scrape_all(self, max_articles_per_journal: int = None) -> Dict[str, Any]:
        """
        Tüm journal'ları sırayla dolaşır:
        1. Journals sayfasına git -> Journal listesini al
        2. Her journal için latest issue sayfasına git -> Makale link'lerini al
        3. Her makale için detay sayfasına git (opsiyonel)
        
        Args:
            max_articles_per_journal: Journal başına max makale sayısı
            
        Returns:
            Dict: {'journals': [...], 'articles': [...]}
        """
        result = {
            'journals': [],
            'articles': []
        }
        
        try:
            # 1) Journal listesini al
            if not self.navigate_to_journals():
                return result
            
            journals = self.scrape_journals()
            result['journals'] = journals
            
            if not journals:
                return result
            
            logger.section(f"TOPLAM {len(journals)} JOURNAL İŞLENECEK")
            
            # 2) Her journal için latest issue -> makale linkleri
            for idx, journal in enumerate(journals, 1):
                self.check_stop_flag()
                
                logger.subsection(f"[{idx}/{len(journals)}] {journal.get('name', 'Unknown')}")
                
                # Journal'ın latest issue'sundaki makaleleri al
                articles = self.scrape_journal_articles(
                    journal, 
                    max_articles=max_articles_per_journal
                )
                
                # Sonuçlara ekle
                result['articles'].extend(articles)
                
                logger.info(f"Toplam makale sayısı: {len(result['articles'])}")
                
                # Rate limiting (journal'lar arası)
                self._random_wait()
            
            logger.section(f"TAMAMLANDI: {len(result['journals'])} journal, {len(result['articles'])} makale")
            
        except ScraperStoppedException:
            logger.warning("Scraper durduruldu!")
        except CloudflareBlockedException as e:
            logger.error(f"Scraper işlemi Cloudflare engeline takıldığı için sonlandırıldı: {e}")
            # İşlemin başarısız sayılması için exception'ı fırlatmaya devam et veya boş sonuç dön
            raise
        except Exception as e:
            logger.error(f"Genel scraping hatası: {e}")
            import traceback
            traceback.print_exc()
        
        return result
            
    def close(self):
        """Tarayıcıyı kapat"""
        try:
            if self.selenium_driver:
                self.selenium_driver.close()
            logger.info("Tarayıcı kapatıldı")
        except Exception as e:
            logger.warning(f"Tarayıcı kapatma hatası: {e}")
