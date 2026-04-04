"""
Main scraper class for IEEE Xplore
"""

import os
import sys
import time
from typing import Optional, List, Dict, Any
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Parent directory'yi path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
logger = get_logger('ieee_xplore')

from .config import ProxyConfig, IEEEXploreConfig
from .driver import SeleniumDriver
from .utils import handle_cookie_consent, wait_for_page_load
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser, IssuesPageParser
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
    
    def extract_all_issues(
        self,
        journal_home_url: str,
        depth: int = None,
        existing_urls: set = None,
    ):
        """
        Journal ana sayfasından Aims & Scope alır ve All Issues sayfasından
        tüm issue bağlantılarını toplar.

        Args:
            journal_home_url: Journal'ın ana/recent issue sayfası URL'i
            depth: Hedef YENİ issue sayısı (None = tümü)
            existing_urls: DB'de zaten var olan issue URL'leri (relative path)

        Returns:
            tuple: (aims_and_scope: str|None, issues: list[{'url': str, 'title': str}])
        """
        existing_urls = existing_urls or set()

        def count_new(issues):
            if not existing_urls:
                return len(issues)
            return sum(1 for i in issues if i['url'] not in existing_urls)

        full_home_url = (
            f"https://ieeexplore.ieee.org{journal_home_url}"
            if journal_home_url.startswith('/') else journal_home_url
        )

        all_issues = []
        aims_and_scope = None

        try:
            # 1. Journal ana sayfasına git
            logger.info(f"Journal ana sayfasına gidiliyor: {full_home_url}")
            if not self.selenium_driver.get(full_home_url, wait_after=3):
                logger.warning("Journal sayfası yüklenemedi")
                return None, []

            wait_for_page_load(self.driver)
            time.sleep(2)
            self.rate_limiter.check_and_handle_rate_limit()

            page_source = self.driver.page_source

            # 2. Aims & scope çıkar
            aims_and_scope = JournalParser.extract_aims_and_scope(page_source)
            if aims_and_scope:
                logger.success(f"Aims & scope alındı ({len(aims_and_scope)} karakter)")
            else:
                logger.warning("Aims & scope bulunamadı")

            # 3. All Issues bağlantısını bul
            all_issues_href = JournalParser.extract_all_issues_tab_url(page_source)
            if not all_issues_href:
                logger.warning("All Issues linki bulunamadı")
                return aims_and_scope, []

            all_issues_url = (
                f"https://ieeexplore.ieee.org{all_issues_href}"
                if all_issues_href.startswith('/') else all_issues_href
            )

            # 4. All Issues sayfasına git
            logger.info(f"All Issues sayfasına gidiliyor: {all_issues_url}")
            if not self.selenium_driver.get(all_issues_url, wait_after=3):
                logger.warning("All Issues sayfası yüklenemedi")
                return aims_and_scope, []

            wait_for_page_load(self.driver)
            time.sleep(2)
            self.rate_limiter.check_and_handle_rate_limit()

            # 5. Decade sekmeleri var mı?
            page_source = self.driver.page_source
            has_decades = IssuesPageParser.has_decade_tabs(page_source)
            decade_tabs = IssuesPageParser.extract_decade_tab_texts(page_source) if has_decades else []

            logger.info(f"Decade sekmeleri: {decade_tabs if has_decades else 'yok'}")

            # 6. Her decade'i işle (yoksa tek geçiş)
            for decade_idx, decade in enumerate(decade_tabs if has_decades else [None]):
                if depth and count_new(all_issues) >= depth:
                    break

                if decade_idx > 0:
                    # Decade sekmesini tıkla
                    try:
                        tab_links = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            ".issue-details-past-tabs:not(.year) li a"
                        )
                        for link in tab_links:
                            if link.text.strip() == decade:
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'});", link
                                )
                                self.driver.execute_script("arguments[0].click();", link)
                                time.sleep(1.5)
                                break
                    except Exception as e:
                        logger.warning(f"Decade sekmesi tıklanamadı ({decade}): {e}")
                        continue

                # 7. Bu decade'deki yılları işle
                done = self._process_year_list(all_issues, depth, existing_urls, count_new)
                if done:
                    break

            logger.success(
                f"Toplam {len(all_issues)} issue bulundu ({count_new(all_issues)} yeni)"
            )
            return aims_and_scope, all_issues

        except RateLimitException:
            raise
        except ScraperStoppedException:
            raise
        except Exception as e:
            logger.failed("All issues çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return aims_and_scope, all_issues

    def _process_year_list(self, all_issues: list, depth, existing_urls: set, count_new) -> bool:
        """
        Mevcut All Issues sayfasındaki yıl listesini işler.
        Doğrudan href'li yıllar issue olarak eklenir; href'siz yıllar tıklanıp
        genişletilen issue listesinden eklenir.

        Returns:
            bool: depth dolmuşsa True
        """
        year_items = IssuesPageParser.extract_year_items(self.driver.page_source)
        logger.info(f"Yıl listesi: {[y['year'] for y in year_items]}")

        for year_item in year_items:
            year_text = year_item['year']
            year_href = year_item['href']

            if year_href:
                # Tek issue olan yıl — doğrudan link kullan
                all_issues.append({'url': year_href, 'title': year_text})
                logger.info(f"Doğrudan issue linki: {year_href} ({year_text})")
            else:
                # Birden fazla issue — tıkla ve listeyi genişlet
                try:
                    year_links = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        ".issue-details-past-tabs.year li a"
                    )
                    clicked = False
                    for link in year_links:
                        if link.text.strip() == year_text:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", link
                            )
                            self.driver.execute_script("arguments[0].click();", link)
                            # Issue listesinin yüklenmesini bekle
                            try:
                                WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((
                                        By.CSS_SELECTOR, ".u-mt-2 section.issue-container"
                                    ))
                                )
                            except TimeoutException:
                                time.sleep(2)
                            clicked = True
                            break

                    if clicked:
                        year_issues = IssuesPageParser.extract_issue_list(self.driver.page_source)
                        all_issues.extend(year_issues)
                        logger.info(f"{year_text}: {len(year_issues)} issue bulundu")
                    else:
                        logger.warning(f"Yıl linki bulunamadı: {year_text}")

                except Exception as e:
                    logger.warning(f"Yıl işleme hatası ({year_text}): {e}")

            if depth and count_new(all_issues) >= depth:
                return True

        return False

    def _process_single_issue(
        self,
        issue_stub: Dict[str, Any],
        max_articles: int = None,
        article_progress_callback=None,
        article_list_callback=None,
        issue_idx: int = 1,
        total_issues: int = 1,
    ) -> Dict[str, Any]:
        """
        Tek bir issue sayfasına gider, makale detaylarını toplar.

        Args:
            issue_stub: {'url': str, 'title': str}
            max_articles: Bu issue için maksimum makale sayısı
            issue_idx / total_issues: Loglama için konum bilgisi

        Returns:
            dict: {'issue_info': {...}, 'articles': [...]}
        """
        issue_url = issue_stub['url']
        full_issue_url = (
            f"https://ieeexplore.ieee.org{issue_url}"
            if issue_url.startswith('/') else issue_url
        )

        logger.section(f"Issue {issue_idx}/{total_issues}: {issue_stub.get('title', issue_url)}")
        logger.info(f"  Issue URL: {full_issue_url}")

        if not self.selenium_driver.get(full_issue_url, wait_after=3):
            logger.warning(f"Issue sayfası yüklenemedi: {full_issue_url}")
            return {'issue_info': {'url': full_issue_url}, 'articles': []}

        wait_for_page_load(self.driver)
        time.sleep(2)
        self.rate_limiter.check_and_handle_rate_limit()

        page_source = self.driver.page_source

        # Issue bilgilerini çıkar
        issue_info = ArticleParser.extract_issue_info(page_source) or {}
        issue_info['url'] = self.driver.current_url

        # issue_stub'daki başlık (ör. "Volume 61 Issue 2") sayfadan parse edilenden
        # daha açıklayıcı — varsa onu kullan, yoksa sayfa içeriğinden geleni koru
        stub_title = issue_stub.get('title', '').strip()
        if stub_title:
            issue_info['issue_number'] = stub_title

        logger.success(f"  Issue: {issue_info.get('issue_number')} | {issue_info.get('date')}")

        # Makale URL'lerini çıkar
        article_urls = ArticleParser.extract_article_urls(page_source)
        if not article_urls:
            logger.warning(f"  Issue için makale bulunamadı: {issue_stub.get('title')}")
            return {'issue_info': issue_info, 'articles': []}

        if max_articles:
            article_urls = article_urls[:max_articles]

        # UI'a makale listesini bildir
        if article_list_callback:
            try:
                article_list_callback(['' for _ in article_urls])
            except Exception:
                pass

        articles = []
        for idx, article_url in enumerate(article_urls, 1):
            self.check_stop_flag()

            if article_progress_callback:
                try:
                    article_progress_callback(idx, len(article_urls), None)
                except Exception:
                    pass

            try:
                full_url = (
                    f"https://ieeexplore.ieee.org{article_url}"
                    if article_url.startswith('/') else article_url
                )

                logger.info(f"[{idx}/{len(article_urls)}] Makale detayı alınıyor...")

                if not self.selenium_driver.get(full_url, wait_after=2):
                    logger.warning(f"Makale sayfası yüklenemedi: {article_url}")
                    continue

                wait_for_page_load(self.driver)
                time.sleep(1)
                self.rate_limiter.check_and_handle_rate_limit()

                article_data = ArticleParser.extract_article_details(
                    self.driver.page_source, full_url
                )

                if article_data and article_data.get('title'):
                    articles.append(article_data)
                    logger.success(f"Makale eklendi: {article_data['title'][:50]}...")

                if article_progress_callback:
                    try:
                        article_progress_callback(
                            idx, len(article_urls),
                            article_data.get('title') if article_data else None
                        )
                    except Exception:
                        pass

                time.sleep(1)

            except RateLimitException:
                raise
            except ScraperStoppedException:
                raise
            except Exception as e:
                logger.warning(f"Makale {idx} hatası: {e}")
                continue

        logger.found(len(articles), f"makale (issue {issue_idx})")
        return {'issue_info': issue_info, 'articles': articles}

    def scrape_journal_articles(
        self,
        journal: Dict[str, Any],
        depth: int = 1,
        max_articles: int = 100,
        article_progress_callback=None,
        article_list_callback=None,
        existing_issue_urls: set = None,
    ) -> List[Dict[str, Any]]:
        """
        Bir journal'ın issue'larını ve makalelerini toplar.

        Args:
            journal: Journal bilgileri (name, url, most_recent_issue_url, ...)
            depth: Kaç YENİ issue işlenecek (1 = sadece en yeni, None = tümü)
            max_articles: Her issue için maksimum makale sayısı
            article_progress_callback: İlerleme callback'i
            article_list_callback: Makale listesi callback'i
            existing_issue_urls: DB'de zaten var olan issue URL'leri (relative path).
                                  Bu URL'lere sahip issue'lar depth sayımına dahil edilmez.

        Returns:
            list[dict]: Her eleman bir issue'ya ait sonuç:
                        {'issue_info': {...}, 'articles': [...]}

        Raises:
            RateLimitException: Rate limit aşıldığında
        """
        existing_issue_urls = existing_issue_urls or set()
        journal_name = journal.get('name', 'Unknown')

        # Journal ana sayfası URL'i — RecentIssue.jsp (aims & scope + All Issues sekmesi burada)
        # most_recent_issue_url mostRecentIssue.jsp olduğu için tercih edilmiyor
        journal_home_url = journal.get('url') or journal.get('most_recent_issue_url')
        if not journal_home_url:
            logger.warning(f"{journal_name}: URL bulunamadı, atlanıyor")
            return []

        logger.header(f"JOURNAL TARANMAYA BAŞLANIYOR: {journal_name}")

        try:
            # 1. Aims & scope + tüm issue listesini al
            aims_and_scope, all_issues = self.extract_all_issues(
                journal_home_url,
                depth=depth,
                existing_urls=existing_issue_urls,
            )
            journal['aims_and_scope'] = aims_and_scope

            if not all_issues:
                logger.warning(f"{journal_name} için issue bulunamadı")
                return []

            # 2. DB'de olanları atla; yeni issue'lardan depth kadar al
            new_issues = [i for i in all_issues if i['url'] not in existing_issue_urls]
            skipped = len(all_issues) - len(new_issues)
            if skipped:
                logger.info(f"{skipped} issue daha önce işlenmiş, atlanıyor. Yeni: {len(new_issues)}")

            issues_to_process = new_issues if not depth else new_issues[:depth]
            logger.info(
                f"Toplam {len(all_issues)} issue, {len(issues_to_process)} tanesi işlenecek "
                f"(depth={depth})"
            )

            # 3. Her issue'yu işle
            issue_results = []
            for issue_idx, issue_stub in enumerate(issues_to_process, 1):
                self.check_stop_flag()

                result = self._process_single_issue(
                    issue_stub=issue_stub,
                    max_articles=max_articles,
                    article_progress_callback=article_progress_callback,
                    article_list_callback=article_list_callback,
                    issue_idx=issue_idx,
                    total_issues=len(issues_to_process),
                )
                for article in result['articles']:
                    article['journal_name'] = journal_name
                issue_results.append(result)

            logger.found(
                sum(len(r['articles']) for r in issue_results),
                f"makale ({journal_name})"
            )
            return issue_results

        except RateLimitException:
            logger.warning(f"{journal_name}: Rate limit nedeniyle durduruldu")
            raise
        except ScraperStoppedException:
            logger.warning(f"{journal_name}: Stop sinyali alındı")
            raise
        except Exception as e:
            logger.error(f"{journal_name}: Hata: {e}")
            import traceback
            traceback.print_exc()
            return []

    def close(self):
        """Tarayıcıyı kapat"""
        try:
            if self.selenium_driver:
                self.selenium_driver.close()
            logger.info("Tarayıcı kapatıldı")
        except Exception as e:
            logger.warning(f"Tarayıcı kapatma hatası: {e}")
