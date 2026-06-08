"""
Main scraper class for IEEE Xplore
"""

import os
import sys
import time
import queue
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
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
from utils.adaptive_concurrency import controller as concurrency_controller


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass

class CloudflareBlockedException(Exception):
    """Cloudflare engeli aşılamadığında fırlatılır"""
    pass


class IEEEXploreScraper:
    """IEEE Xplore scraper ana sınıfı"""
    
    def __init__(self, use_proxy: bool = None, headless: bool = False, stop_flag=None, pause_flag=None):
        """
        IEEE Xplore scraper'ı başlatır

        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            stop_flag: threading.Event - durdurma sinyali için
            pause_flag: threading.Event - duraklatma sinyali için
        """
        self.stop_flag = stop_flag
        self.pause_flag = pause_flag
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
        
        # Oturum boyunca yaşayan paralel worker driver havuzu.
        # Bir kez açılır; tüm journal/issue'larda yeniden kullanılır,
        # geçişlerde KAPATILMAZ. Yalnızca close() ile kapanır.
        self._worker_pool: List[SeleniumDriver] = []

        # Veri tutucular
        self.all_journals: List[Dict[str, Any]] = []
    
    def check_stop_flag(self):
        """Stop flag kontrol et, set ise exception fırlat"""
        if self.stop_flag and self.stop_flag.is_set():
            logger.warning("Stop sinyali alındı, scraper durduruluyor...")
            raise ScraperStoppedException("Scraper durduruldu")

    def _interruptible_sleep(self, seconds: float) -> None:
        """Stop/pause flag kontrolü yaparak bekle. Stop flag set ise exception fırlatır."""
        end = time.time() + seconds
        while True:
            self.check_stop_flag()
            if self.pause_flag and self.pause_flag.is_set():
                while self.pause_flag.is_set():
                    self.check_stop_flag()
                    time.sleep(0.3)
            remaining = end - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.3, remaining))
    
    def initialize(self):
        """Scraper'ı başlatır"""
        logger.header("IEEE Xplore Scraper Başlatılıyor...")
        
        if not self.selenium_driver.start():
            raise Exception("WebDriver başlatılamadı!")
        
        self.driver = self.selenium_driver.driver
        self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
        self.rate_limiter = IEEERateLimiter(self.driver, pause_duration=300)  # 5 dakika
        
        logger.success(f"Hedef URL: {self.config.base_url}")

    def _ensure_worker_pool(self, max_tabs: int) -> List[SeleniumDriver]:
        """
        Oturum boyunca yaşayan paralel worker driver havuzunu döndür.

        İlk ihtiyaçta bir kez açılır; tüm journal ve issue'larda yeniden
        kullanılır. Journal/issue geçişlerinde KAPATILMAZ. Tekil driver
        hataları (rate limit / erişim / tarayıcı çökmesi) ilgili driver'ın
        kendi get()/restart() mantığıyla iyileşir; havuz korunur. 
        
        Eksik worker varsa ekler. Fazla worker varsa kapatmaz (israf olsa da).
        Havuz yalnızca scraper.close() ile (oturum sonu) kapatılır.
        Hata durumunda _reset_worker_pool_on_error() ile tamamen sıfırlanır.
        """
        if max_tabs <= 1:
            return []
        # Eksik worker varsa tamamla (ilk açılış ya da daha büyük max_tabs)
        while len(self._worker_pool) < max_tabs:
            worker_id = len(self._worker_pool) + 1
            wd = SeleniumDriver(self.proxy_config, headless=self.headless)
            if wd.start():
                self._worker_pool.append(wd)
                logger.info(f"Worker-{worker_id}: oturum havuzuna eklendi")
            else:
                logger.warning(f"Worker-{worker_id}: havuz driver'ı başlatılamadı")
                break
        if self._worker_pool:
            logger.info(
                f"Oturum worker havuzu hazır: {len(self._worker_pool)} driver "
                f"(journal/issue boyunca yeniden kullanılır, sabit tutulur)"
            )
        return self._worker_pool

    def _restart_single_worker(self, worker_id: int, pool_index: int, reason: str = "unknown"):
        """
        Hata durumunda tek bir worker'ı (tarayıcı) kapatıp yeniden açar.
        Diğer worker'lar çalışmaya devam eder.
        
        Args:
            worker_id: Worker'ın ID'si (loglama için)
            pool_index: Worker pool'da index
            reason: Restart nedeni (loglama için)
        """
        if pool_index < 0 or pool_index >= len(self._worker_pool):
            logger.warning(f"Worker-{worker_id}: havuzda geçersiz index {pool_index}, atlanıyor")
            return False
        
        old_driver = self._worker_pool[pool_index]
        logger.warning(f"Worker-{worker_id}: yeniden başlatılıyor (neden: {reason})")
        
        try:
            old_driver.close()
            logger.info(f"Worker-{worker_id}: eski tarayıcı kapatıldı")
        except Exception as e:
            logger.warning(f"Worker-{worker_id}: eski tarayıcı kapatma hatası: {e}")
        
        try:
            new_driver = SeleniumDriver(self.proxy_config, headless=self.headless)
            if new_driver.start():
                self._worker_pool[pool_index] = new_driver
                logger.success(f"Worker-{worker_id}: yeni tarayıcı başlatıldı ve havuza kondu")
                return True
            else:
                logger.error(f"Worker-{worker_id}: yeni tarayıcı başlatılamadı")
                self._worker_pool[pool_index] = None  # slot'u null yap
                return False
        except Exception as e:
            logger.error(f"Worker-{worker_id}: yeni tarayıcı oluşturma hatası: {e}")
            self._worker_pool[pool_index] = None
            return False

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
            
            # Angular SPA: readyState complete olsa bile pagination render edilmemiş olabilir.
            # pagination-bar'ı bekle — bu hazır olunca get_current_page_info() anında çalışır.
            logger.loading("Sayfa yükleniyor")
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.pagination-bar ul"))
                )
            except TimeoutException:
                # Pagination bulunamadı ama devam et (tek sayfa olabilir)
                wait_for_page_load(self.driver)
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
        
        last_page_urls = set()
        restart_count = 0

        # Tüm sayfaları tara
        while True:
            # Stop flag kontrolü - her sayfa öncesi
            self.check_stop_flag()
            
            logger.subsection(f"Sayfa {current_page}/{total_pages} taranıyor")
            
            # Mevcut sayfadaki journal'ları parse et
            page_source = self.driver.page_source
            journals = JournalParser.extract_journals_from_page(page_source)
            
            current_urls = {j['url'] for j in journals if j.get('url')}
            if current_urls and current_urls.issubset(last_page_urls):
                logger.warning("Kopya liste tespit edildi (aynı sayfa tekrar yüklendi/aynı makaleler alındı)!")
                if restart_count < 3:
                    logger.info("Liste komple sıfırlanıyor, sayfa 1'e dönülüyor...")
                    self.all_journals.clear()
                    current_page = 1
                    restart_count += 1
                    last_page_urls.clear()
                    
                    self.driver.get(self.config.base_url)
                    wait_for_page_load(self.driver)
                    self._interruptible_sleep(2)
                    
                    # Update navigator info
                    self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
                    page_info = self.navigator.get_current_page_info()
                    if 'total_pages' in page_info:
                        total_pages = page_info['total_pages']
                    continue
                else:
                    logger.error("Maksimum sayfa sıfırlama limitine ulaşıldı, geçiliyor.")
                    break
                    
            last_page_urls = current_urls
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
            
            self._interruptible_sleep(2)  # Rate limiting
            current_page += 1
        
        logger.section(f"TOPLAM {len(self.all_journals)} JOURNAL BULUNDU")
        return self.all_journals
    
    def extract_all_issues(
        self,
        journal_home_url: str,
        depth: int = None,
        existing_urls: set = None,
        issues_order: str = "newest_first",
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
            self.rate_limiter.check_and_handle_rate_limit()

            # 5. Sayfa tipini tespit et: All Volumes mu, yoksa All Issues mi?
            page_source = self.driver.page_source

            if IssuesPageParser.is_volumes_page(page_source):
                # --- All Volumes tipi: her yıl doğrudan bir issue/volume URL'ine sahip ---
                logger.info("All Volumes tipi sayfa tespit edildi")
                volume_links = IssuesPageParser.extract_volumes_year_links(page_source)
                if issues_order == "oldest_first":
                    volume_links = list(reversed(volume_links))
                logger.info(f"Volume/yıl linkleri: {[v['title'] for v in volume_links]}")

                for vol in volume_links:
                    if depth and count_new(all_issues) >= depth:
                        break
                    all_issues.append({'url': vol['url'], 'title': vol['title']})
                    logger.info(f"Volume eklendi: {vol['title']} -> {vol['url']}")

            else:
                # --- All Issues tipi: decade sekmeleri ve yıl listesi ---
                has_decades = IssuesPageParser.has_decade_tabs(page_source)
                decade_tabs = IssuesPageParser.extract_decade_tab_texts(page_source) if has_decades else []

                logger.info(f"Decade sekmeleri: {decade_tabs if has_decades else 'yok'}")

                # 6. Her decade'i işle (yoksa tek geçiş) — issues_order'a göre yön belirle
                if has_decades:
                    ordered_decade_tabs = list(reversed(decade_tabs)) if issues_order == "oldest_first" else decade_tabs
                else:
                    ordered_decade_tabs = [None]
                for decade_idx, decade in enumerate(ordered_decade_tabs):
                    if depth and count_new(all_issues) >= depth:
                        break

                    # oldest_first'te tüm decade'ler tıklanmalı (ilki de aktif değil)
                    if has_decades and decade is not None and (decade_idx > 0 or issues_order == "oldest_first"):
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
                                    self._interruptible_sleep(1.5)
                                    break
                        except Exception as e:
                            logger.warning(f"Decade sekmesi tıklanamadı ({decade}): {e}")
                            continue

                    # 7. Bu decade'deki yılları işle
                    done = self._process_year_list(all_issues, depth, existing_urls, count_new, issues_order)
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

    def _process_year_list(self, all_issues: list, depth, existing_urls: set, count_new, issues_order: str = "newest_first") -> bool:
        """
        Mevcut All Issues sayfasındaki yıl listesini işler.
        Doğrudan href'li yıllar issue olarak eklenir; href'siz yıllar tıklanıp
        genişletilen issue listesinden eklenir.

        Returns:
            bool: depth dolmuşsa True
        """
        year_items = IssuesPageParser.extract_year_items(self.driver.page_source)
        if issues_order == "oldest_first":
            year_items = list(reversed(year_items))
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
                                self._interruptible_sleep(2)
                            clicked = True
                            break

                    if clicked:
                        year_issues = IssuesPageParser.extract_issue_list(self.driver.page_source)
                        if issues_order == "oldest_first":
                            year_issues = list(reversed(year_issues))
                        all_issues.extend(year_issues)
                        logger.info(f"{year_text}: {len(year_issues)} issue bulundu")
                    else:
                        logger.warning(f"Yıl linki bulunamadı: {year_text}")

                except Exception as e:
                    logger.warning(f"Yıl işleme hatası ({year_text}): {e}")

            if depth and count_new(all_issues) >= depth:
                return True

        return False

    def _fetch_issue_page(
        self,
        issue_stub: Dict[str, Any],
        issue_idx: int = 0,
        total_issues: int = 0,
    ) -> tuple:
        """
        Ana tab ile issue sayfasına gider, issue bilgilerini ve makale stub listesini döndürür.

        Paralel pipeline'da worker'lar mevcut issue'yu işlerken bu metot ayrı bir thread'den
        çağrılarak bir sonraki issue önceden yüklenir; worker'lar biter bitmez makalelere
        anında başlayabilirler.

        Returns:
            (issue_info: dict, article_stubs: list)  —  hata durumunda exception fırlatır
        """
        issue_url = issue_stub['url']
        full_issue_url = (
            f"https://ieeexplore.ieee.org{issue_url}"
            if issue_url.startswith('/') else issue_url
        )
        if issue_idx and total_issues:
            logger.section(
                f"Issue {issue_idx}/{total_issues} yükleniyor: "
                f"{issue_stub.get('title', issue_url)}"
            )
        logger.info(f"  Issue URL: {full_issue_url}")

        if not self.selenium_driver.get(full_issue_url, wait_after=3):
            raise Exception(f"Issue sayfası yüklenemedi: {full_issue_url}")

        wait_for_page_load(self.driver)
        self.rate_limiter.check_and_handle_rate_limit()

        try:
            WebDriverWait(self.driver, 12).until(
                lambda d: d.execute_script(
                    """
                    return !!document.querySelector(
                        'xpl-issue-results-items, section.issue-container, a[href*="/document/"]'
                    );
                    """
                )
            )
        except TimeoutException:
            pass

        page_source = self.driver.page_source
        issue_info = ArticleParser.extract_issue_info(page_source) or {}
        issue_info['url'] = self.driver.current_url

        stub_title = issue_stub.get('title', '').strip()
        if stub_title:
            issue_info['issue_number'] = stub_title

        logger.success(
            f"  Issue bilgisi alındı: "
            f"{issue_info.get('issue_number')} | {issue_info.get('date')}"
        )
        article_stubs = ArticleParser.extract_article_urls(page_source)
        logger.info(f"  {len(article_stubs)} makale linki bulundu")
        return issue_info, article_stubs

    def _process_single_issue(
        self,
        issue_stub: Dict[str, Any],
        max_articles: int = None,
        max_tabs: int = 1,
        parallel_drivers: Optional[List[SeleniumDriver]] = None,
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
        self.rate_limiter.check_and_handle_rate_limit()

        # TOC sayfalarında içerik çoğu zaman XHR ile sonradan geliyor.
        # ReadyState=complete hemen dönse de makale listesi henüz DOM'a düşmemiş olabilir.
        try:
            WebDriverWait(self.driver, 12).until(
                lambda d: d.execute_script(
                    """
                    return !!document.querySelector(
                        'xpl-issue-results-items, section.issue-container, a[href*="/document/"]'
                    );
                    """
                )
            )
        except TimeoutException:
            # Bazı issue/volume sayfalarında makale yerine sadece yıl/issue listesi olabilir.
            # Bu durumda mevcut akış fallback parser ile devam eder.
            pass

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

        # Makale URL'lerini ve başlıklarını çıkar
        article_stubs = ArticleParser.extract_article_urls(page_source)
        if not article_stubs:
            logger.warning(f"  Issue için makale bulunamadı: {issue_stub.get('title')}")
            return {'issue_info': issue_info, 'articles': []}

        if max_articles:
            article_stubs = article_stubs[:max_articles]

        # UI'a makale listesini (başlıklarıyla) bildir
        if article_list_callback:
            try:
                article_list_callback([a.get('title', '') for a in article_stubs])
            except Exception:
                pass

        if max_tabs > 1:
            articles, failed_stubs = self._process_issue_articles_parallel(
                article_stubs=article_stubs,
                max_tabs=max_tabs,
                reusable_drivers=parallel_drivers,
                article_progress_callback=article_progress_callback,
            )
        else:
            articles = []
            failed_stubs = []  # Yüklenemeyen makaleler için retry kuyruğu

            for idx, article_stub in enumerate(article_stubs, 1):
                article_url = article_stub['url']
                self.check_stop_flag()

                if article_progress_callback:
                    try:
                        article_progress_callback(idx, len(article_stubs), None)
                    except Exception:
                        pass

                try:
                    full_url = (
                        f"https://ieeexplore.ieee.org{article_url}"
                        if article_url.startswith('/') else article_url
                    )

                    stub_title = article_stub.get('title', '')
                    logger.info(f"[{idx}/{len(article_stubs)}] Makale detayı alınıyor: {stub_title[:60] if stub_title else article_url}")

                    if not self.selenium_driver.get(full_url, wait_after=2):
                        logger.warning(f"Makale sayfası yüklenemedi, retry kuyruğuna eklendi: {article_url}")
                        failed_stubs.append(article_stub)
                        continue

                    wait_for_page_load(self.driver)
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
                                idx, len(article_stubs),
                                article_data.get('title') if article_data else None
                            )
                        except Exception:
                            pass

                    self._interruptible_sleep(0.3)  # anti-bot politeness (azaltıldı)

                except RateLimitException:
                    raise
                except ScraperStoppedException:
                    raise
                except Exception as e:
                    logger.warning(f"Makale {idx} hatası, retry kuyruğuna eklendi: {e}")
                    failed_stubs.append(article_stub)
                    continue

        # Retry kuyruğunu işle
        if failed_stubs:
            logger.info(f"{len(failed_stubs)} makale yüklenemedi, {len(failed_stubs)} saniye bekleniyor...")
            self._interruptible_sleep(min(len(failed_stubs) * 2, 30))
            logger.info(f"Retry başlıyor ({len(failed_stubs)} makale)...")

            for retry_idx, article_stub in enumerate(failed_stubs, 1):
                article_url = article_stub['url']
                self.check_stop_flag()
                try:
                    full_url = (
                        f"https://ieeexplore.ieee.org{article_url}"
                        if article_url.startswith('/') else article_url
                    )
                    logger.info(f"[Retry {retry_idx}/{len(failed_stubs)}] {article_url}")

                    if not self.selenium_driver.get(full_url, wait_after=4):
                        logger.warning(f"Retry başarısız, makale atlanıyor: {article_url}")
                        continue

                    wait_for_page_load(self.driver)
                    self.rate_limiter.check_and_handle_rate_limit()

                    article_data = ArticleParser.extract_article_details(
                        self.driver.page_source, full_url
                    )
                    if article_data and article_data.get('title'):
                        articles.append(article_data)
                        logger.success(f"Retry başarılı: {article_data['title'][:50]}...")
                    else:
                        logger.warning(f"Retry: makale detayları alınamadı ({article_url})")

                    self._interruptible_sleep(2)
                except RateLimitException:
                    raise
                except ScraperStoppedException:
                    raise
                except Exception as e:
                    logger.warning(f"Retry hatası ({article_url}): {e}")
                    continue

        logger.found(len(articles), f"makale (issue {issue_idx})")
        return {'issue_info': issue_info, 'articles': articles}

    def _process_issue_articles_parallel(
        self,
        article_stubs: List[Dict[str, Any]],
        max_tabs: int,
        reusable_drivers: Optional[List[SeleniumDriver]] = None,
        article_progress_callback=None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Issue içindeki makaleleri worker havuzu ile paralel işler."""
        total = len(article_stubs)
        # Adaptif eşzamanlılık: yavaş/dengesiz hatta worker havuzunu kısıtla
        adaptive_tabs = concurrency_controller.effective_max_tabs('ieee', max_tabs)
        requested_worker_count = max(1, min(adaptive_tabs, total))

        worker_slots: List[Tuple[int, SeleniumDriver, bool, int]] = []
        if reusable_drivers:
            for pool_idx, driver in enumerate(reusable_drivers[:requested_worker_count]):
                worker_id = pool_idx + 1
                worker_slots.append((worker_id, driver, False, pool_idx))
        else:
            for worker_id in range(1, requested_worker_count + 1):
                local_driver = SeleniumDriver(self.proxy_config, headless=self.headless)
                if local_driver.start():
                    worker_slots.append((worker_id, local_driver, True, -1))
                else:
                    logger.warning(f"Worker-{worker_id}: local driver başlatılamadı")

        if not worker_slots:
            logger.warning("Parallel mod için kullanılabilir worker driver yok")
            return [], article_stubs[:]

        jobs: queue.Queue[tuple[int, Dict[str, Any]]] = queue.Queue()
        for idx, stub in enumerate(article_stubs, 1):
            jobs.put((idx, stub))

        results_by_index: Dict[int, Dict[str, Any]] = {}
        failed_stubs: List[Dict[str, Any]] = []
        lock = threading.Lock()
        processed_count = 0

        def _worker(worker_id: int, local_driver: SeleniumDriver, owns_driver: bool, pool_index: int = -1):
            """
            Worker thread: makale'leri paralel işler.
            Hata durumunda:
              - Pool worker (owns_driver=False): _restart_single_worker() çağrılır
              - Local worker (owns_driver=True): driver'ı restart etmeye çalışır
            """
            try:
                while True:
                    if self.stop_flag and self.stop_flag.is_set():
                        return
                    if self.pause_flag and self.pause_flag.is_set():
                        while self.pause_flag.is_set():
                            if self.stop_flag and self.stop_flag.is_set():
                                return
                            time.sleep(0.2)

                    try:
                        idx, article_stub = jobs.get_nowait()
                    except queue.Empty:
                        return

                    article_url = article_stub.get('url', '')
                    full_url = (
                        f"https://ieeexplore.ieee.org{article_url}"
                        if article_url.startswith('/') else article_url
                    )

                    article_data = None
                    try:
                        if local_driver.get(full_url, wait_after=2):
                            wait_for_page_load(local_driver.driver)
                            article_data = ArticleParser.extract_article_details(
                                local_driver.driver.page_source,
                                full_url,
                            )
                    except RateLimitException:
                        # Rate limit hatasında worker'ı restart et
                        logger.warning(f"Worker-{worker_id}: Rate limit hatası, tarayıcı yeniden başlatılıyor")
                        if not owns_driver and pool_index >= 0:
                            # Pool worker: havuzda restart et
                            self._restart_single_worker(worker_id, pool_index, "rate_limit")
                            # Tarayıcı yenilendikten sonra retry
                            if pool_index < len(self._worker_pool):
                                local_driver = self._worker_pool[pool_index]
                        else:
                            # Local worker: restart etmeye çalış
                            try:
                                local_driver.restart()
                            except Exception as restart_err:
                                logger.warning(f"Worker-{worker_id}: Restart hatası: {restart_err}")
                        article_data = None
                    except CloudflareBlockedException:
                        # Cloudflare engelinde worker'ı restart et
                        logger.warning(f"Worker-{worker_id}: Cloudflare engeli, tarayıcı yeniden başlatılıyor")
                        if not owns_driver and pool_index >= 0:
                            self._restart_single_worker(worker_id, pool_index, "cloudflare")
                            if pool_index < len(self._worker_pool):
                                local_driver = self._worker_pool[pool_index]
                        else:
                            try:
                                local_driver.restart()
                            except Exception as restart_err:
                                logger.warning(f"Worker-{worker_id}: Restart hatası: {restart_err}")
                        article_data = None
                    except Exception:
                        article_data = None

                    article_ok = bool(article_data and article_data.get('title'))
                    callback_payload = None

                    with lock:
                        nonlocal processed_count
                        processed_count += 1
                        if article_ok:
                            results_by_index[idx] = article_data
                        else:
                            failed_stubs.append(article_stub)

                        if article_progress_callback:
                            callback_payload = (
                                processed_count,
                                total,
                                article_data.get('title') if article_data else None,
                            )

                    if callback_payload:
                        try:
                            article_progress_callback(*callback_payload)
                        except Exception:
                            pass

                    # Adaptif eşzamanlılık geri beslemesi (lock dışında — kendi lock'lı)
                    _fetch = getattr(local_driver, 'last_fetch', None)
                    concurrency_controller.record(
                        'ieee',
                        ok=article_ok,
                        duration_s=getattr(_fetch, 'duration_s', 0.0) if _fetch else 0.0,
                        recovered=getattr(_fetch, 'recovered', False) if _fetch else False,
                    )
            finally:
                # Sadece bu worker'ın kendi açtığı driver kapatılır.
                # reusable_drivers (owns_driver=False) journal boyunca canlı
                # kalır; issue geçişlerinde KAPATILMAZ, journal sonunda
                # scrape_journal_articles finally'sinde tek sefer kapatılır.
                if owns_driver:
                    local_driver.close()

        threads = [
            threading.Thread(target=_worker, args=(worker_id, driver, owns_driver, pool_idx), daemon=True)
            for worker_id, driver, owns_driver, pool_idx in worker_slots
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ordered_articles = [results_by_index[idx] for idx in sorted(results_by_index.keys())]
        logger.info(
            "issue_fetch_summary",
            total=total,
            ok=len(ordered_articles),
            failed=len(failed_stubs),
            effective_tabs=requested_worker_count,
        )
        return ordered_articles, failed_stubs

    def scrape_journal_articles(
        self,
        journal: Dict[str, Any],
        depth: int = 1,
        max_articles: int = 100,
        max_tabs: int = 1,
        article_progress_callback=None,
        article_list_callback=None,
        journal_name_callback=None,
        existing_issue_urls: set = None,
        issue_start_callback=None,
        issue_complete_callback=None,
        issues_order: str = "newest_first",
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

        # Tekil URL analizi akışında gerçek journal adını sayfadan çözümle
        if journal.get('resolve_name_from_url'):
            full_home_url = (
                f"https://ieeexplore.ieee.org{journal_home_url}"
                if journal_home_url.startswith('/') else journal_home_url
            )
            try:
                if self.selenium_driver.get(full_home_url, wait_after=3):
                    wait_for_page_load(self.driver)
                    resolved_name = JournalParser.extract_journal_name_from_journal_page(self.driver.page_source)
                    if resolved_name:
                        journal['name'] = resolved_name
                        journal_name = resolved_name
                        if journal_name_callback:
                            try:
                                journal_name_callback(resolved_name)
                            except Exception:
                                pass
                        logger.success(f"IEEE journal adı çözümlendi: {resolved_name}")
                    else:
                        logger.warning("IEEE journal adı çözümlenemedi, mevcut isim kullanılacak")
            except Exception as e:
                logger.warning(f"IEEE journal adı çözümleme hatası: {e}")

        logger.header(f"JOURNAL TARANMAYA BAŞLANIYOR: {journal_name}")

        try:
            # Worker havuzunu arka planda başlat; issue listesi yüklenirken tarayıcılar açılır
            _pool_container: list = []
            _pool_bg: Optional[threading.Thread] = None
            if max_tabs > 1:
                _pool_bg = threading.Thread(
                    target=lambda: _pool_container.extend(self._ensure_worker_pool(max_tabs)),
                    daemon=True,
                )
                _pool_bg.start()
                logger.info(f"Worker havuzu arka planda başlatılıyor ({max_tabs} tarayıcı)...")
            parallel_drivers = _pool_container

            # 1. Aims & scope + tüm issue listesini al
            aims_and_scope, all_issues = self.extract_all_issues(
                journal_home_url,
                depth=depth,
                existing_urls=existing_issue_urls,
                issues_order=issues_order,
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

            # Issue sırası toplama aşamasında uygulandı
            if issues_order == "oldest_first":
                logger.info("[IEEE] Issue sırası: eskiden yeniye (oldest_first)")
            else:
                logger.info("[IEEE] Issue sırası: yeniden eskiye (newest_first)")

            issues_to_process = new_issues if not depth else new_issues[:depth]
            logger.info(
                f"Toplam {len(all_issues)} issue, {len(issues_to_process)} tanesi işlenecek "
                f"(depth={depth})"
            )

            # 3. Her issue'yu işle
            # Paralel modda: ana tab sonraki issue'yu önceden yükler (prefetch pipeline).
            issue_results = []

            _pf_thread: Optional[threading.Thread] = None
            _pf_next_idx: int = -1
            _pf_holder: dict = {}

            for issue_idx, issue_stub in enumerate(issues_to_process, 1):
                self.check_stop_flag()

                if issue_start_callback:
                    try:
                        pending_titles = [
                            s.get('title', f'Issue {i}')
                            for i, s in enumerate(issues_to_process[issue_idx:], issue_idx + 1)
                        ]
                        issue_start_callback(
                            issue_idx,
                            len(issues_to_process),
                            issue_stub.get('title', f'Issue {issue_idx}'),
                            pending_titles,
                        )
                    except Exception:
                        pass

                if (parallel_drivers or _pool_bg) and max_tabs > 1:
                    # ── Pipeline modu ──────────────────────────────────────────────

                    # Issue verilerini al: önceden yüklendiyse hazır, yoksa şimdi çek
                    if _pf_next_idx == issue_idx:
                        if _pf_thread and _pf_thread.is_alive():
                            _pf_thread.join()
                        if _pf_holder.get('data'):
                            issue_info, article_stubs = _pf_holder['data']
                            logger.info(f"Issue {issue_idx}: önceden yüklenmiş veri kullanılıyor")
                        else:
                            logger.warning(f"Issue {issue_idx}: prefetch başarısız, şimdi yükleniyor")
                            try:
                                issue_info, article_stubs = self._fetch_issue_page(
                                    issue_stub, issue_idx, len(issues_to_process)
                                )
                            except Exception as fe:
                                logger.warning(f"Issue {issue_idx} yüklenemedi: {fe}")
                                result = {'issue_info': {'url': issue_stub['url']}, 'articles': []}
                                issue_results.append(result)
                                continue
                    else:
                        try:
                            issue_info, article_stubs = self._fetch_issue_page(
                                issue_stub, issue_idx, len(issues_to_process)
                            )
                        except Exception as fe:
                            logger.warning(f"Issue {issue_idx} yüklenemedi: {fe}")
                            result = {'issue_info': {'url': issue_stub['url']}, 'articles': []}
                            issue_results.append(result)
                            continue

                    _pf_thread = None
                    _pf_next_idx = -1
                    _pf_holder = {}

                    if not article_stubs:
                        logger.warning(f"  Issue için makale bulunamadı: {issue_stub.get('title')}")
                        result = {'issue_info': issue_info, 'articles': []}
                    else:
                        if max_articles:
                            article_stubs = article_stubs[:max_articles]

                        if article_list_callback:
                            try:
                                article_list_callback([a.get('title', '') for a in article_stubs])
                            except Exception:
                                pass

                        # Worker'lar bu issue'yu işlerken sonraki issue'yu önceden yükle
                        next_idx = issue_idx + 1
                        if next_idx <= len(issues_to_process):
                            next_stub = issues_to_process[next_idx - 1]
                            holder_ref: dict = {}
                            _pf_holder = holder_ref
                            _pf_next_idx = next_idx
                            total_count = len(issues_to_process)

                            def _do_prefetch(
                                stub=next_stub, idx=next_idx,
                                h=holder_ref, total=total_count,
                            ):
                                try:
                                    self.check_stop_flag()
                                    ni, ns = self._fetch_issue_page(stub, idx, total)
                                    h['data'] = (ni, ns)
                                    logger.info(
                                        f"Issue {idx} prefetch tamamlandı "
                                        f"({len(ns)} makale linki worker'lar için hazır)"
                                    )
                                except ScraperStoppedException:
                                    pass
                                except Exception as e:
                                    logger.warning(f"Issue {idx} prefetch hatası: {e}")

                            _pf_thread = threading.Thread(target=_do_prefetch, daemon=True)
                            _pf_thread.start()

                        # Havuz hazır değilse bekle (issue fetch ile örtüşmesi beklenir)
                        if _pool_bg and _pool_bg.is_alive():
                            logger.info(
                                "Worker tarayıcıları hazırlanmayı bekleniyor "
                                "(issue fetch ile örtüşmesi beklenir)..."
                            )
                            _pool_bg.join()
                            _pool_bg = None

                        # Makaleleri worker tablarla işle
                        articles, failed_stubs = self._process_issue_articles_parallel(
                            article_stubs=article_stubs,
                            max_tabs=max_tabs,
                            reusable_drivers=parallel_drivers,
                            article_progress_callback=article_progress_callback,
                        )

                        # Retry öncesi prefetch thread'ini bekle (self.driver çakışmasını önle)
                        if _pf_thread and _pf_thread.is_alive():
                            logger.info(
                                f"Issue {issue_idx + 1} prefetch bitmesini bekleniyor "
                                f"(retry için ana tab gerekiyor)..."
                            )
                            _pf_thread.join()
                            _pf_thread = None

                        # Başarısız makaleleri retry (ana tab)
                        if failed_stubs:
                            logger.info(
                                f"{len(failed_stubs)} makale yüklenemedi, "
                                f"{min(len(failed_stubs) * 2, 30)} saniye bekleniyor..."
                            )
                            self._interruptible_sleep(min(len(failed_stubs) * 2, 30))
                            logger.info(f"Retry başlıyor ({len(failed_stubs)} makale)...")
                            for retry_idx, article_stub in enumerate(failed_stubs, 1):
                                article_url = article_stub['url']
                                self.check_stop_flag()
                                try:
                                    full_url = (
                                        f"https://ieeexplore.ieee.org{article_url}"
                                        if article_url.startswith('/') else article_url
                                    )
                                    logger.info(f"[Retry {retry_idx}/{len(failed_stubs)}] {article_url}")
                                    if not self.selenium_driver.get(full_url, wait_after=4):
                                        logger.warning(f"Retry başarısız, makale atlanıyor: {article_url}")
                                        continue
                                    wait_for_page_load(self.driver)
                                    self.rate_limiter.check_and_handle_rate_limit()
                                    article_data = ArticleParser.extract_article_details(
                                        self.driver.page_source, full_url
                                    )
                                    if article_data and article_data.get('title'):
                                        articles.append(article_data)
                                        logger.success(f"Retry başarılı: {article_data['title'][:50]}...")
                                    else:
                                        logger.warning(f"Retry: makale detayları alınamadı ({article_url})")
                                    self._interruptible_sleep(2)
                                except RateLimitException:
                                    raise
                                except ScraperStoppedException:
                                    raise
                                except Exception as e:
                                    logger.warning(f"Retry hatası ({article_url}): {e}")
                                    continue

                        logger.found(len(articles), f"makale (issue {issue_idx})")
                        result = {'issue_info': issue_info, 'articles': articles}

                else:
                    # ── Tekli tab modu (mevcut kod, değiştirilmedi) ────────────────
                    result = self._process_single_issue(
                        issue_stub=issue_stub,
                        max_articles=max_articles,
                        max_tabs=1,
                        parallel_drivers=None,
                        article_progress_callback=article_progress_callback,
                        article_list_callback=article_list_callback,
                        issue_idx=issue_idx,
                        total_issues=len(issues_to_process),
                    )

                for article in result['articles']:
                    article['journal_name'] = journal_name
                issue_results.append(result)

                if issue_complete_callback:
                    try:
                        issue_complete_callback(
                            issue_idx,
                            len(result['articles']),
                            [a.get('title', '') for a in result['articles']],
                        )
                    except Exception:
                        pass

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
        """Tarayıcıyı kapat (oturum sonu — worker havuzu dahil)"""
        for wd in self._worker_pool:
            try:
                wd.close()
            except Exception as close_err:
                logger.warning(f"Worker driver kapatma hatası: {close_err}")
        self._worker_pool = []
        try:
            if self.selenium_driver:
                self.selenium_driver.close()
            logger.info("Tarayıcı kapatıldı")
        except Exception as e:
            logger.warning(f"Tarayıcı kapatma hatası: {e}")
