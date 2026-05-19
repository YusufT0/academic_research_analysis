"""
Main scraper class for Wiley Online Library.

Supports two journal formats:
  - Issue-based:   /loi/{id} → issues → /toc/{id}/{year}/{vol}/{issue} → articles
  - Article-based: /index/{id} → paginated article list → articles
"""

import os
import sys
import time
import random
import queue
import threading
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
logger = get_logger('wiley')

from .config import ProxyConfig, WileyConfig
from .driver import SeleniumDriver
from utils.adaptive_concurrency import controller as concurrency_controller
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser
from .utils import (
    handle_cookie_consent, wait_for_page_load,
    extract_journal_id_from_url, clean_text
)
from .rate_limiter import WileyRateLimiter, RateLimitException


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass


class CloudflareBlockedException(Exception):
    """Cloudflare engeli aşılamadığında fırlatılır"""
    pass


class WileyScraper:
    """
    Wiley Online Library scraper ana sınıfı.

    Kullanım (ScraperManager'dan çağrılır):
        scraper = WileyScraper(headless=True, stop_flag=evt, pause_flag=evt)
        scraper.initialize()
        journals = scraper.scrape_all_journals()
        scraper.scrape_journal_articles(journal, ...)
        scraper.close()
    """

    WILEY_BASE = "https://onlinelibrary.wiley.com"

    def __init__(self, use_proxy: bool = None, headless: bool = False,
                 stop_flag=None, pause_flag=None):
        self.stop_flag = stop_flag
        self.pause_flag = pause_flag
        self.config = WileyConfig()

        self.proxy_config = ProxyConfig()
        if use_proxy is not None:
            self.proxy_config.use_proxy = use_proxy
            logger.info(f"Proxy kullanımı parametre ile belirlendi: {use_proxy}")
        else:
            logger.info(f".env'den USE_PROXY okundu: {self.proxy_config.use_proxy}")

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

        self.selenium_driver = SeleniumDriver(
            self.proxy_config,
            headless=headless,
            page_load_timeout=self.config.page_load_timeout,
        )
        self.navigator = None  # initialized after driver starts
        self.rate_limiter = WileyRateLimiter(
            self.selenium_driver,
            min_wait=self.config.min_wait,
            max_wait=self.config.max_wait,
        )
        self.headless = headless
        self.all_journals: List[Dict] = []

        # Oturum boyunca yaşayan paralel worker driver havuzu.
        # Bir kez açılır; tüm journal/issue'larda yeniden kullanılır,
        # geçişlerde KAPATILMAZ. Yalnızca close() ile kapanır.
        self._worker_pool: List[SeleniumDriver] = []

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def initialize(self):
        """Scraper'ı başlat — WebDriver'ı başlatır"""
        logger.header("Wiley Scraper Başlatılıyor...")
        if not self.selenium_driver.start():
            raise Exception("WebDriver başlatılamadı!")
        self.navigator = PageNavigator(self.selenium_driver, self.WILEY_BASE)
        logger.success(f"Hedef URL: {self.config.base_url}")

    def _ensure_worker_pool(self, max_tabs: int) -> List[SeleniumDriver]:
        """
        Oturum boyunca yaşayan paralel worker driver havuzunu döndür.

        İlk ihtiyaçta bir kez açılır; tüm journal ve issue'larda yeniden
        kullanılır. Journal/issue geçişlerinde KAPATILMAZ. Tekil driver
        hataları (rate limit / erişim / tarayıcı çökmesi) ilgili driver'ın
        kendi get()/restart() mantığıyla iyileşir; havuz korunur. Havuz
        yalnızca scraper.close() ile (oturum sonu) kapatılır.
        """
        if max_tabs <= 1:
            return []
        # Eksik worker varsa tamamla (ilk açılış ya da daha büyük max_tabs)
        while len(self._worker_pool) < max_tabs:
            worker_id = len(self._worker_pool) + 1
            local_driver = SeleniumDriver(self.proxy_config, headless=self.headless)
            if local_driver.start():
                self._worker_pool.append(local_driver)
                logger.info(f"Worker-{worker_id}: oturum havuzuna eklendi")
            else:
                logger.warning(f"Worker-{worker_id}: havuz driver'ı başlatılamadı")
                break
        if self._worker_pool:
            logger.info(
                f"Oturum worker havuzu hazır: {len(self._worker_pool)} driver "
                f"(journal/issue boyunca yeniden kullanılır)"
            )
        return self._worker_pool

    def close(self):
        """Scraper'ı kapat (oturum sonu — worker havuzu dahil)"""
        for wd in self._worker_pool:
            try:
                wd.close()
            except Exception as close_err:
                logger.warning(f"Worker driver kapatma hatası: {close_err}")
        self._worker_pool = []
        self.selenium_driver.close()
        logger.info("Wiley Scraper kapatıldı")

    # ------------------------------------------------------------------ #
    #  Stop / Pause helpers
    # ------------------------------------------------------------------ #

    def check_stop_flag(self):
        """Stop flag set ise exception fırlat"""
        if self.stop_flag and self.stop_flag.is_set():
            logger.warning("Stop sinyali alındı, scraper durduruluyor...")
            raise ScraperStoppedException("Scraper durduruldu")

    def _interruptible_sleep(self, seconds: float):
        """Stop/pause kontrolü yaparak bekle"""
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

    def _random_wait(self):
        """Rate limiting için rastgele bekleme"""
        wait = random.uniform(self.config.min_wait, self.config.max_wait)
        logger.info(f"Rate limiting: {wait:.1f}s bekleniyor...")
        self._interruptible_sleep(wait)

    def _close_modals(self):
        """Cookie ve diğer popup'ları kapat"""
        handle_cookie_consent(self.selenium_driver, timeout=4)

    def _check_cloudflare_and_handle(self) -> bool:
        """Cloudflare varsa handle et, yoksa True döner"""
        if self.rate_limiter.check_cloudflare():
            return self.rate_limiter.handle_cloudflare()
        return True

    # ------------------------------------------------------------------ #
    #  Journal List
    # ------------------------------------------------------------------ #

    def navigate_to_journals(self) -> bool:
        """Ana journal listesi sayfasına git"""
        logger.url(self.config.base_url, "Wiley'a bağlanılıyor")
        logger.loading("Sayfa yükleniyor")
        success = self.navigator.go_to_journal_list_page(self.config.base_url, page=0)
        if success:
            self._close_modals()
            logger.success("Sayfa hazır!")
        else:
            logger.error("Sayfa yüklenemedi!")
        return success

    def scrape_all_journals(self) -> List[Dict[str, Any]]:
        """
        Tüm sayfaları dolaşarak journal listesini topla.

        Wiley pagination: startPage=0,1,2,... (her sayfada ~20 journal)
        Toplam sayfa sayısı parse_pagination() ile belirlenir.

        Returns:
            list: Tüm journal'ların bilgileri
        """
        logger.section("JOURNAL LİSTESİ TOPLANMAYA BAŞLANIYOR")
        all_journals = []
        page = 0
        max_pages = 200  # güvenlik limiti

        while page < max_pages:
            self.check_stop_flag()

            logger.subsection(f"Sayfa {page + 1} taranıyor")

            if page > 0:
                success = self.navigator.go_to_journal_list_page(
                    self.config.base_url, page=page
                )
                if not success:
                    logger.warning(f"Sayfa {page} yüklenemedi, duruyoruz")
                    break
                self._close_modals()

            html = self.selenium_driver.page_source
            if not html:
                logger.warning(f"Sayfa {page}: HTML alınamadı")
                break

            # Cloudflare kontrolü
            if not self._check_cloudflare_and_handle():
                logger.error("Cloudflare engeli aşılamadı")
                break

            journals = JournalParser.parse_journal_list(html)
            if not journals:
                logger.info(f"Sayfa {page}: journal bulunamadı, tamamlandı")
                break

            all_journals.extend(journals)
            logger.found(len(journals), f"journal (Sayfa {page + 1})")
            logger.info(f"Toplam: {len(all_journals)} journal")

            # Pagination bilgisi
            pagination = JournalParser.parse_pagination(html)
            total_pages = pagination.get('total_pages', 1)

            # Pagination HTML'de bulunamadıysa (AJAX yüklü olabilir):
            # DOM'da "next" butonuna JS ile bak
            if total_pages <= 1 and not pagination.get('has_next'):
                try:
                    js_has_next = self.selenium_driver.execute_script(
                        "return !!(document.querySelector("
                        "'li.next a, a[aria-label*=\"next\" i], a[rel=\"next\"], "
                        "li[class*=\"next\"]:not([class*=\"disabled\"]) a'"
                        "))"
                    )
                    if js_has_next:
                        pagination['has_next'] = True
                        total_pages = page + 2  # en az bir sonraki sayfa var
                except Exception:
                    pass

            if page >= total_pages - 1 and not pagination.get('has_next'):
                logger.success("Tüm sayfalar tarandı!")
                break

            page += 1

        self.all_journals = all_journals
        logger.section(f"TOPLAM {len(all_journals)} JOURNAL BULUNDU")
        return all_journals

    # ------------------------------------------------------------------ #
    #  Aims & Scope
    # ------------------------------------------------------------------ #

    def extract_aims_and_scope(self, journal_id: str) -> Optional[str]:
        """
        /hub/journal/{journal_id}/overview sayfasından Aims & Scope çıkar.
        """
        url = f"{self.WILEY_BASE}/hub/journal/{journal_id}/overview"
        try:
            logger.info(f"Aims & Scope alınıyor: {url}")
            if not self.selenium_driver.get(url, wait_after=4):
                return None
            self._close_modals()
            self.check_stop_flag()

            aims = JournalParser.parse_aims_and_scope(self.selenium_driver.page_source)
            if aims:
                logger.success(f"Aims & Scope alındı ({len(aims)} karakter)")
            return aims
        except ScraperStoppedException:
            raise
        except Exception as e:
            logger.warning(f"Aims & Scope alınamadı ({url}): {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Issue-based journal
    # ------------------------------------------------------------------ #

    def _extract_all_issues(
        self,
        journal_id: str,
        depth: int = None,
        existing_urls: set = None,
        issues_order: str = "newest_first",
    ) -> List[Dict[str, Any]]:
        """
        /loi/{journal_id} sayfasından issue listesi topla.

        - Sayfa yüklendikten sonra kapalı decade/yıl bölümlerini genişlet
        - depth: Kaç YENİ issue işlenecek (None=tümü)
        - issues_order: "newest_first" | "oldest_first"

        Returns:
            list: [{url, title, volume, year}]
        """
        existing_urls = existing_urls or set()
        loi_url = f"{self.WILEY_BASE}/loi/{journal_id}"
        all_issues = []
        seen_urls = set()

        def count_new():
            return sum(1 for i in all_issues if i['url'] not in existing_urls)

        logger.info(f"LOI sayfasına gidiliyor: {loi_url}")
        if not self.selenium_driver.get(loi_url, wait_after=5):
            logger.warning("LOI sayfası yüklenemedi")
            return []

        self._close_modals()
        self.check_stop_flag()

        # Expandable bölümleri genişlet (kapalı decade/yıl grupları)
        expandable = JournalParser.get_expandable_decade_selectors(self.selenium_driver.page_source)
        for section in expandable:
            self.check_stop_flag()
            if depth and count_new() >= depth:
                break
            try:
                js = f"""
                (function() {{
                    var el = document.querySelector('{section["selector"]}');
                    if (el && el.getAttribute('aria-expanded') !== 'true') {{
                        el.click(); return true;
                    }}
                    return false;
                }})()
                """
                clicked = self.selenium_driver.execute_script(js)
                if clicked:
                    logger.info(f"Genişletildi: {section['label']}")
                    self._interruptible_sleep(1.5)
            except Exception as e:
                logger.warning(f"Decade genişletme hatası: {e}")

        # Tüm issue'ları parse et
        issues = JournalParser.parse_issue_list(self.selenium_driver.page_source)
        for i in issues:
            if i['url'] not in seen_urls:
                seen_urls.add(i['url'])
                all_issues.append(i)

        # issues_order'a göre sırala
        if issues_order == 'oldest_first':
            all_issues = list(reversed(all_issues))

        logger.success(f"Toplam {len(all_issues)} issue bulundu ({count_new()} yeni)")
        return all_issues

    def _process_single_issue(
        self,
        issue: Dict[str, Any],
        max_articles: int = None,
        max_tabs: int = 1,
        article_progress_callback: Callable = None,
        article_list_callback: Callable = None,
        issue_idx: int = 1,
        total_issues: int = 1,
        reusable_drivers=None,
        article_stubs_override: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Tek bir issue sayfasını işle: makale listesi al ve her makaleyi scrape et.

        Full Text filtresi uygulanır: yalnızca full text linki olan makaleler işlenir.

        Returns:
            dict: {issue_info, articles}
        """
        issue_url = issue['url']
        full_url = (
            f"{self.WILEY_BASE}{issue_url}"
            if issue_url.startswith('/') else issue_url
        )

        logger.section(f"Issue {issue_idx}/{total_issues}: {issue.get('title', issue_url)}")
        logger.info(f"  Issue URL: {full_url}")

        if article_stubs_override is None:
            if not self.navigator.go_to_issue_toc(full_url):
                logger.warning(f"Issue ToC yüklenemedi: {full_url}")
                return {'issue_info': issue, 'articles': []}

            self._close_modals()
            self._check_cloudflare_and_handle()

            # Makale listesini parse et
            article_stubs = JournalParser.parse_article_list_from_toc(self.selenium_driver.page_source)
        else:
            # Article-based akışta daha önce filtrelenmiş stub listesi kullanılır
            article_stubs = article_stubs_override

        # Full Text filtresi
        full_text_stubs = [a for a in article_stubs if a.get('has_full_text')]
        logger.info(f"  {len(article_stubs)} makale, {len(full_text_stubs)} Full Text")

        if not full_text_stubs:
            logger.warning("  Full Text makale bulunamadı, issue atlanıyor")
            return {'issue_info': issue, 'articles': []}

        if max_articles and len(full_text_stubs) > max_articles:
            full_text_stubs = full_text_stubs[:max_articles]
            logger.info(f"  max_articles={max_articles} ile kırpıldı")

        if article_list_callback:
            try:
                article_list_callback([a.get('title', '') for a in full_text_stubs])
            except Exception:
                pass

        # Her makaleyi scrape et
        if max_tabs > 1:
            articles, retry_queue = self._process_issue_articles_parallel(
                full_text_stubs=full_text_stubs,
                max_tabs=max_tabs,
                article_progress_callback=article_progress_callback,
                reusable_drivers=reusable_drivers,
            )
        else:
            articles = []
            retry_queue = []
            consecutive_failures = 0

            for idx, stub in enumerate(full_text_stubs, 1):
                self.check_stop_flag()

                if article_progress_callback:
                    try:
                        article_progress_callback(idx, len(full_text_stubs), None)
                    except Exception:
                        pass

                doi_url = stub.get('doi_url', '') or stub.get('doi', '')
                if doi_url.startswith('/doi'):
                    article_url = f"{self.WILEY_BASE}{doi_url}"
                elif doi_url.startswith('http'):
                    article_url = doi_url
                else:
                    article_url = f"{self.WILEY_BASE}/doi/full/{doi_url}"

                stub_title = stub.get('title', '')
                logger.info(f"[{idx}/{len(full_text_stubs)}] Makale detayı alınıyor: {stub_title[:60] if stub_title else article_url}")

                article_data = None
                success = False

                for attempt in range(2):
                    if attempt > 0:
                        self._interruptible_sleep(3)

                    if not self.selenium_driver.get(article_url, wait_after=4):
                        continue

                    self._close_modals()
                    self._check_cloudflare_and_handle()
                    wait_for_page_load(self.selenium_driver)

                    article_data = ArticleParser.parse_article_detail(
                        self.selenium_driver.page_source, article_url
                    )
                    if article_data and article_data.get('title'):
                        success = True
                        break

                if success and article_data:
                    # Stub'dan eksik alanları tamamla
                    if not article_data.get('authors') and stub.get('authors'):
                        article_data['authors'] = [{'name': a} for a in stub['authors']]
                    if not article_data.get('pub_date') and stub.get('pub_date'):
                        article_data['pub_date'] = stub['pub_date']
                    articles.append(article_data)
                    logger.success(f"Makale eklendi: {article_data['title'][:50]}...")
                    consecutive_failures = 0
                    self.rate_limiter.record_success()
                else:
                    retry_queue.append(article_url)
                    consecutive_failures += 1
                    self.rate_limiter.record_failure()
                    logger.warning(f"  ✗ Makale alınamadı, retry kuyruğuna eklendi")

                if article_progress_callback:
                    try:
                        article_progress_callback(
                            idx, len(full_text_stubs),
                            article_data.get('title') if (success and article_data) else None
                        )
                    except Exception:
                        pass

                # Art arda 3 hata → browser restart
                if consecutive_failures >= 3:
                    logger.error("Üst üste 3 hata! Tarayıcı yeniden başlatılıyor...")
                    self.selenium_driver.restart()
                    self._interruptible_sleep(30)
                    consecutive_failures = 0

                self._random_wait()

        # Retry kuyruğu
        if retry_queue:
            logger.info(f"{len(retry_queue)} makale yüklenemedi, yeniden deneniyor...")
            logger.info(f"Retry başlıyor ({len(retry_queue)} makale)...")
            for retry_idx, r_url in enumerate(retry_queue, 1):
                self.check_stop_flag()
                try:
                    logger.info(f"[Retry {retry_idx}/{len(retry_queue)}] {r_url}")
                    if not self.selenium_driver.get(r_url, wait_after=4):
                        logger.warning(f"Retry başarısız, makale atlanıyor: {r_url}")
                        continue
                    self._close_modals()
                    wait_for_page_load(self.selenium_driver)
                    article_data = ArticleParser.parse_article_detail(
                        self.selenium_driver.page_source, r_url
                    )
                    if article_data and article_data.get('title'):
                        articles.append(article_data)
                        logger.success(f"Retry başarılı: {article_data['title'][:50]}...")
                    else:
                        logger.warning(f"Retry: makale detayları alınamadı ({r_url})")
                    self._random_wait()
                except (ScraperStoppedException, CloudflareBlockedException):
                    raise
                except Exception as e:
                    logger.warning(f"Retry hatası ({r_url}): {e}")

        logger.found(len(articles), f"makale (issue {issue_idx})")
        return {'issue_info': issue, 'articles': articles}

    def _process_issue_articles_parallel(
        self,
        full_text_stubs: List[Dict[str, Any]],
        max_tabs: int,
        article_progress_callback: Callable = None,
        reusable_drivers=None,
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Issue içindeki makaleleri worker havuzu ile paralel işler."""
        total = len(full_text_stubs)
        # Adaptif eşzamanlılık: yavaş/dengesiz hatta worker havuzunu kısıtla
        adaptive_tabs = concurrency_controller.effective_max_tabs('wiley', max_tabs)
        worker_count = max(1, min(adaptive_tabs, total))
        jobs: queue.Queue[tuple[int, Dict[str, Any]]] = queue.Queue()
        for idx, stub in enumerate(full_text_stubs, 1):
            jobs.put((idx, stub))

        results_by_index: Dict[int, Dict[str, Any]] = {}
        retry_urls: List[str] = []
        lock = threading.Lock()
        processed_count = 0

        def _to_article_url(stub: Dict[str, Any]) -> str:
            doi_url = stub.get('doi_url', '') or stub.get('doi', '')
            if doi_url.startswith('/doi'):
                return f"{self.WILEY_BASE}{doi_url}"
            if doi_url.startswith('http'):
                return doi_url
            return f"{self.WILEY_BASE}/doi/full/{doi_url}"

        # Build worker slots: (worker_id, driver, owns_driver, pool_index)
        # If reusable_drivers provided, use them (don't close on exit).
        # Otherwise create new drivers (close on exit).
        worker_slots = []
        if reusable_drivers:
            for pool_index, driver in enumerate(reusable_drivers[:worker_count]):
                worker_id = pool_index + 1
                worker_slots.append((worker_id, driver, False, pool_index))
        else:
            for worker_id in range(1, worker_count + 1):
                local_driver = SeleniumDriver(self.proxy_config, headless=self.headless)
                if local_driver.start():
                    worker_slots.append((worker_id, local_driver, True, -1))
                else:
                    logger.warning(f"Worker-{worker_id}: local driver başlatılamadı")
                    # Jobs for this worker will be handled by remaining workers or retry

        if not worker_slots:
            logger.warning("Parallel mod için kullanılabilir worker yok, retry kuyruğuna alınıyor")
            while not jobs.empty():
                try:
                    _, stub = jobs.get_nowait()
                    retry_urls.append(_to_article_url(stub))
                except queue.Empty:
                    break
            return [], retry_urls

        def _worker(worker_id: int, local_driver, owns_driver: bool, pool_index: int):
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
                        idx, stub = jobs.get_nowait()
                    except queue.Empty:
                        return

                    article_url = _to_article_url(stub)
                    article_data = None

                    for attempt in range(2):
                        if attempt > 0:
                            time.sleep(1)
                        try:
                            if not local_driver.get(article_url, wait_after=4):
                                continue
                            detail = ArticleParser.parse_article_detail(local_driver.page_source, article_url)
                            if detail and detail.get('title'):
                                if not detail.get('authors') and stub.get('authors'):
                                    detail['authors'] = [{'name': a} for a in stub['authors']]
                                if not detail.get('pub_date') and stub.get('pub_date'):
                                    detail['pub_date'] = stub['pub_date']
                                article_data = detail
                                break
                        except RateLimitException as e:
                            logger.warning(f"Worker-{worker_id}: rate limit hatası")
                            if pool_index >= 0:
                                self._restart_single_worker(worker_id, pool_index, "rate_limit_error")
                            else:
                                local_driver.restart()
                            jobs.put((idx, stub))  # retry kuyruğuna geri koy
                            break  # attempt döngüsünden çık
                        except CloudflareBlockedException as e:
                            logger.warning(f"Worker-{worker_id}: Cloudflare bloklama hatası")
                            if pool_index >= 0:
                                self._restart_single_worker(worker_id, pool_index, "cloudflare_blocked")
                            else:
                                local_driver.restart()
                            jobs.put((idx, stub))  # retry kuyruğuna geri koy
                            break  # attempt döngüsünden çık
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
                            retry_urls.append(article_url)

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
                        'wiley',
                        ok=article_ok,
                        duration_s=getattr(_fetch, 'duration_s', 0.0) if _fetch else 0.0,
                        recovered=getattr(_fetch, 'recovered', False) if _fetch else False,
                    )
            finally:
                if owns_driver:
                    local_driver.close()

        threads = [
            threading.Thread(target=_worker, args=(wid, drv, owns, pool_idx), daemon=True)
            for wid, drv, owns, pool_idx in worker_slots
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
            failed=len(retry_urls),
            effective_tabs=worker_count,
        )
        return ordered_articles, retry_urls

    # ------------------------------------------------------------------ #
    #  Article-based journal
    # ------------------------------------------------------------------ #

    def _scrape_article_based_journal(
        self,
        journal_id: str,
        max_articles: int = None,
        max_tabs: int = 1,
        article_progress_callback: Callable = None,
        article_list_callback: Callable = None,
        issue_start_callback: Callable = None,
        issue_complete_callback: Callable = None,
        existing_article_dois: set = None,
        reusable_drivers=None,
    ) -> List[Dict[str, Any]]:
        """
        Article-based journal'ı işle: /index/{journal_id} sayfasından tüm makaleleri topla.

        Tüm makaleler tek bir "sanal issue" olarak döner.
        Existing DOI'ler filtrelenerek tekrar scrape edilmez.

        Returns:
            list: [{issue_info, articles}]
        """
        existing_article_dois = existing_article_dois or set()
        index_url = f"{self.WILEY_BASE}/index/{journal_id}"
        all_stubs = []
        filtered_candidates = []
        seen_article_keys = set()
        page = 0
        max_pages = 100

        logger.info(f"Article-based journal: {index_url}")

        while page < max_pages:
            self.check_stop_flag()

            url = index_url if page == 0 else f"{index_url}?startPage={page}"
            if not self.selenium_driver.get(url, wait_after=4):
                logger.warning(f"Index sayfa {page} yüklenemedi")
                break

            self._close_modals()
            stubs = JournalParser.parse_article_list_from_index(self.selenium_driver.page_source)

            if not stubs:
                break

            all_stubs.extend(stubs)
            page_new_count = 0
            for stub in stubs:
                if not stub.get('has_full_text'):
                    continue

                doi = (stub.get('doi') or '').strip()
                doi_url = (stub.get('doi_url') or '').strip()
                title = (stub.get('title') or '').strip().lower()
                key = doi or doi_url or title
                if not key:
                    continue

                if doi and doi in existing_article_dois:
                    continue
                if key in seen_article_keys:
                    continue

                seen_article_keys.add(key)
                filtered_candidates.append(stub)
                page_new_count += 1

            pagination = JournalParser.parse_pagination(self.selenium_driver.page_source)
            total_pages = pagination.get('total_pages', 1)

            logger.info(
                f"Index sayfa {page}: {len(stubs)} makale | "
                f"Yeni aday: +{page_new_count} | Toplam yeni aday: {len(filtered_candidates)}"
            )

            if max_articles and len(filtered_candidates) >= max_articles:
                logger.info(f"max_articles={max_articles} doldu, pagination erken durduruldu")
                break

            if page >= total_pages - 1:
                break

            page += 1
            self._random_wait()

        # Full Text filtresi ve mevcut DOI filtresi
        filtered = filtered_candidates

        logger.info(f"Yeni Full Text makale: {len(filtered)}")

        if max_articles:
            filtered = filtered[:max_articles]

        if not filtered:
            return []

        if article_list_callback:
            try:
                article_list_callback([a.get('title', '') for a in filtered])
            except Exception:
                pass

        virtual_issue = {
            'url': index_url,
            'title': 'All Articles',
            'volume': '',
            'year': '',
        }

        if issue_start_callback:
            try:
                issue_start_callback(1, 1, 'All Articles', [])
            except Exception:
                pass

        # Tüm makaleleri scrape et (aynı logic)
        result = self._process_single_issue(
            issue=virtual_issue,
            max_articles=max_articles,
            max_tabs=max_tabs,
            article_progress_callback=article_progress_callback,
            article_list_callback=None,  # zaten yukarıda çağrıldı
            issue_idx=1,
            total_issues=1,
            reusable_drivers=reusable_drivers,
            article_stubs_override=filtered,
        )

        if issue_complete_callback:
            try:
                issue_complete_callback(
                    1,
                    len(result['articles']),
                    [a.get('title', '') for a in result['articles']]
                )
            except Exception:
                pass

        return [result]

    # ------------------------------------------------------------------ #
    #  Main entry point
    # ------------------------------------------------------------------ #

    def scrape_journal_articles(
        self,
        journal: Dict[str, Any],
        depth: int = 1,
        max_articles: int = None,
        max_tabs: int = 1,
        article_progress_callback: Callable = None,
        article_list_callback: Callable = None,
        journal_name_callback: Callable = None,
        existing_issue_urls: set = None,
        existing_article_dois: set = None,
        issue_start_callback: Callable = None,
        issue_complete_callback: Callable = None,
        issues_order: str = "newest_first",
    ) -> List[Dict[str, Any]]:
        """
        Bir Wiley journal'ının tüm makalelerini scrape eder.

        Akış:
        1. Eğer resolve_name_from_url ise: Journal adını sayfadan çözümle
        2. Aims & Scope al
        3. Journal tipini tespit et (issue-based / article-based)
        4a. Issue-based: /loi/ → issue listesi → her issue'yu işle
        4b. Article-based: /index/ → makale listesi → her makaleyi işle

        Args:
            journal: {name, url, journal_id, open_access, ...}
            depth: Kaç yeni issue işlenecek (None=tümü, issue-based için)
            max_articles: Issue/journal başına maks makale
            existing_issue_urls: DB'de zaten var olan issue URL'leri (set)
            existing_article_dois: DB'de zaten var olan DOI'ler (article-based için)
            issues_order: "newest_first" | "oldest_first"

        Returns:
            list: [{issue_info, articles}, ...]
        """
        if max_articles is None:
            max_articles = self.config.max_articles

        existing_issue_urls = existing_issue_urls or set()
        existing_article_dois = existing_article_dois or set()

        journal_id = journal.get('journal_id', '')
        journal_name = journal.get('name', 'Unknown')

        if not journal_id:
            # URL'den çıkarmayı dene
            journal_id = extract_journal_id_from_url(journal.get('url', ''))
            if journal_id:
                journal['journal_id'] = journal_id

        if not journal_id:
            logger.warning(f"{journal_name}: journal_id bulunamadı, atlanıyor")
            return []

        logger.header(f"JOURNAL TARANMAYA BAŞLANIYOR: {journal_name}")

        # ── 0. Resolve name from URL ──────────────────────────────────────────
        if journal.get('resolve_name_from_url'):
            try:
                journal_url = f"{self.WILEY_BASE}/journal/{journal_id}"
                if self.selenium_driver.get(journal_url, wait_after=3):
                    self._close_modals()
                    resolved = ArticleParser.extract_journal_name_from_article(
                        self.selenium_driver.page_source
                    )
                    if resolved:
                        journal['name'] = resolved
                        journal_name = resolved
                        if journal_name_callback:
                            try:
                                journal_name_callback(resolved)
                            except Exception:
                                pass
                        logger.success(f"Journal adı çözümlendi: {resolved}")
            except Exception as e:
                logger.warning(f"Journal adı çözümleme hatası: {e}")

        # Journal-level worker pool (sadece issue-based akışta oluşturulur)
        parallel_drivers: List[SeleniumDriver] = []

        try:
            self.check_stop_flag()

            # ── 1. Aims & Scope ───────────────────────────────────────────────
            aims = self.extract_aims_and_scope(journal_id)
            journal['aims_and_scope'] = aims

            self.check_stop_flag()

            # ── 2. Journal tipi tespiti ───────────────────────────────────────
            journal_url = f"{self.WILEY_BASE}/journal/{journal_id}"
            if not self.selenium_driver.get(journal_url, wait_after=4):
                logger.warning(f"{journal_name}: journal sayfası yüklenemedi")
                return []

            self._close_modals()
            journal_type = JournalParser.detect_journal_type(self.selenium_driver.page_source)
            logger.info(f"Journal tipi: {journal_type}")

            # ── 3a. Issue-based ───────────────────────────────────────────────
            if journal_type != 'article_based':
                # Oturum worker havuzu (bir kez açılır, tüm journal/issue'larda
                # yeniden kullanılır; burada KAPATILMAZ)
                parallel_drivers = self._ensure_worker_pool(max_tabs)

                all_issues = self._extract_all_issues(
                    journal_id,
                    depth=depth,
                    existing_urls=existing_issue_urls,
                    issues_order=issues_order,
                )

                if not all_issues:
                    logger.warning(f"{journal_name}: Issue bulunamadı")
                    # Fallback: article-based dene
                    if journal_type == 'unknown':
                        logger.info("Fallback: article-based deneniyor...")
                        parallel_drivers = self._ensure_worker_pool(max_tabs)
                        return self._scrape_article_based_journal(
                            journal_id, max_articles, max_tabs, article_progress_callback,
                            article_list_callback, issue_start_callback,
                            issue_complete_callback, existing_article_dois,
                            reusable_drivers=parallel_drivers,
                        )
                    return []

                # Yeni issue'ları filtrele
                new_issues = [i for i in all_issues if i['url'] not in existing_issue_urls]
                skipped = len(all_issues) - len(new_issues)
                if skipped:
                    logger.info(f"{skipped} issue daha önce işlenmiş, atlanıyor. Yeni: {len(new_issues)}")

                if issues_order == "oldest_first":
                    logger.info("[Wiley] Issue sırası: eskiden yeniye (oldest_first)")
                else:
                    logger.info("[Wiley] Issue sırası: yeniden eskiye (newest_first)")

                issues_to_process = new_issues[:depth] if depth else new_issues
                logger.info(
                    f"Toplam {len(all_issues)} issue, {len(issues_to_process)} tanesi işlenecek "
                    f"(depth={depth})"
                )

                def _display_issue_title(issue_obj: Dict[str, Any], fallback_index: int) -> str:
                    title = clean_text(issue_obj.get('title', ''))
                    if title:
                        return title
                    # LOI sayfasında bazı link metinleri boş gelebiliyor; kullanıcıya görünen bir fallback üret.
                    year = clean_text(str(issue_obj.get('year', '') or ''))
                    volume = clean_text(str(issue_obj.get('volume', '') or ''))
                    if year and volume:
                        return f"Volume {volume} ({year})"
                    if year:
                        return f"Issue {year}"
                    if volume:
                        return f"Volume {volume}"
                    return f"Issue {fallback_index}"

                issue_results = []
                for idx, issue in enumerate(issues_to_process, 1):
                    self.check_stop_flag()

                    if issue_start_callback:
                        try:
                            pending = [
                                _display_issue_title(s, i)
                                for i, s in enumerate(issues_to_process[idx:], idx + 1)
                            ]
                            issue_start_callback(
                                idx,
                                len(issues_to_process),
                                _display_issue_title(issue, idx),
                                pending,
                            )
                        except Exception:
                            pass

                    result = self._process_single_issue(
                        issue=issue,
                        max_articles=max_articles,
                        max_tabs=max_tabs if parallel_drivers else 1,
                        article_progress_callback=article_progress_callback,
                        article_list_callback=article_list_callback,
                        issue_idx=idx,
                        total_issues=len(issues_to_process),
                        reusable_drivers=parallel_drivers,
                    )

                    for art in result['articles']:
                        art['journal_name'] = journal_name

                    issue_results.append(result)

                    if issue_complete_callback:
                        try:
                            issue_complete_callback(
                                idx,
                                len(result['articles']),
                                [a.get('title', '') for a in result['articles']]
                            )
                        except Exception:
                            pass

                    self._random_wait()

                logger.found(
                    sum(len(r['articles']) for r in issue_results),
                    f"makale ({journal_name})"
                )
                return issue_results

            # ── 3b. Article-based ─────────────────────────────────────────────
            else:
                parallel_drivers = self._ensure_worker_pool(max_tabs)
                return self._scrape_article_based_journal(
                    journal_id, max_articles, max_tabs, article_progress_callback,
                    article_list_callback, issue_start_callback,
                    issue_complete_callback, existing_article_dois,
                    reusable_drivers=parallel_drivers,
                )

        except ScraperStoppedException:
            logger.warning(f"{journal_name}: Stop sinyali alındı")
            raise
        except CloudflareBlockedException:
            raise
        except Exception as e:
            logger.error(f"{journal_name}: Hata: {e}")
            import traceback
            traceback.print_exc()
            return []
