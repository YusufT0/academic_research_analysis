"""Main scraper class for Springer."""

import random
import sys
import time
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

from .config import ProxyConfig, SpringerConfig
from .driver import SeleniumDriver
from utils.adaptive_concurrency import controller as concurrency_controller
from .navigation import PageNavigator
from .parsers import ArticleDetailParser, ArticleListParser, JournalDetailParser, JournalListParser, VolumesAndIssuesParser
from .rate_limiter import SpringerRateLimiter
from .utils import extract_journal_id_from_url, handle_cookie_consent, wait_for_page_load

logger = get_logger("springer")


class ScraperStoppedException(Exception):
    pass

class RateLimitException(Exception):
    """Rate limit hatası olduğunda fırlatılır"""
    pass

class CloudflareBlockedException(Exception):
    """Cloudflare engeli aşılamadığında fırlatılır"""
    pass


class SpringerScraper:
    BASE_URL = "https://link.springer.com"

    def __init__(self, use_proxy: bool = None, headless: bool = False, stop_flag=None, pause_flag=None):
        self.stop_flag = stop_flag
        self.pause_flag = pause_flag

        self.config = SpringerConfig()
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
        self.navigator = None
        self.rate_limiter = SpringerRateLimiter(
            self.selenium_driver,
            min_wait=self.config.min_wait,
            max_wait=self.config.max_wait,
        )
        self.headless = headless
        self._cookie_handled = False
        self._cookie_attempts = 0
        self._max_cookie_attempts = 3

        # Oturum boyunca yaşayan paralel worker driver havuzu.
        # Bir kez açılır; tüm journal/issue'larda yeniden kullanılır,
        # geçişlerde KAPATILMAZ. Yalnızca close() ile kapanır.
        self._worker_pool: List[SeleniumDriver] = []

    def initialize(self):
        logger.header("Springer Scraper Baslatiliyor")
        logger.info(f"Headless: {self.headless}")
        logger.info(f"Proxy aktif: {self.proxy_config.use_proxy}")
        if not self.selenium_driver.start():
            raise Exception("WebDriver baslatilamadi")
        self.navigator = PageNavigator(self.selenium_driver, self.BASE_URL)
        logger.success("Springer scraper initialize tamamlandi")

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
            wd = SeleniumDriver(
                self.proxy_config,
                headless=self.headless,
                page_load_timeout=self.config.page_load_timeout,
            )
            if wd.start():
                self._worker_pool.append(wd)
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
        for wd in self._worker_pool:
            try:
                wd.close()
            except Exception as close_err:
                logger.warning(f"Worker driver kapatma hatası: {close_err}")
        self._worker_pool = []
        self.selenium_driver.close()
        logger.info("Springer Scraper kapatildi")

    def check_stop_flag(self):
        if self.stop_flag and self.stop_flag.is_set():
            logger.warning("Stop sinyali alındı, scraper durduruluyor...")
            raise ScraperStoppedException("Scraper durduruldu")

    def _interruptible_sleep(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end:
            self.check_stop_flag()
            if self.pause_flag and self.pause_flag.is_set():
                while self.pause_flag.is_set():
                    self.check_stop_flag()
                    time.sleep(0.2)
            time.sleep(0.2)

    def _random_wait(self):
        wait = random.uniform(self.config.min_wait, self.config.max_wait)
        logger.info(f"Rate limiting bekleme: {wait:.1f}s")
        self._interruptible_sleep(wait)

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
            new_driver = SeleniumDriver(
                self.proxy_config,
                headless=self.headless,
                page_load_timeout=self.config.page_load_timeout,
            )
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

    def _close_modals(self):
        if self._cookie_handled:
            return
        if self._cookie_attempts >= self._max_cookie_attempts:
            return

        self._cookie_attempts += 1
        handled = handle_cookie_consent(self.selenium_driver, timeout=4)
        if handled:
            self._cookie_handled = True
            logger.success("Cookie banner kapatildi ve bir daha denenmeyecek")
        else:
            logger.info(
                f"Cookie banner gorunmedi (deneme {self._cookie_attempts}/{self._max_cookie_attempts})"
            )

    def navigate_to_journals(self) -> bool:
        logger.info("Journal listesi aciliyor (ilk sayfa)")
        ok = self.navigator.go_to_journal_list_page(self.config.base_url, page=1)
        if ok:
            logger.success("Journal listesi sayfasi acildi")
        else:
            logger.error("Journal listesi sayfasi acilamadi")
        return ok

    def scrape_all_journals(self) -> List[Dict[str, Any]]:
        logger.header("SPRINGER JOURNAL LISTESI TOPLAMA BASLADI")
        journals: List[Dict[str, Any]] = []
        seen = set()
        page = 1
        max_pages = 200
        logger.section(f"TOPLAM EN COK {max_pages} SAYFA TARANACAK")

        while page <= max_pages:
            self.check_stop_flag()
            logger.subsection(f"Sayfa {page} taraniyor")
            if not self.navigator.go_to_journal_list_page(self.config.base_url, page=page):
                logger.warning(f"Journal sayfasi yuklenemedi, duruluyor: page={page}")
                break
            self._close_modals()

            page_html = self.selenium_driver.page_source
            parsed = JournalListParser.parse_journals(page_html)
            for journal in parsed:
                jid = journal.get("journal_id")
                if jid and jid not in seen:
                    seen.add(jid)
                    journals.append(journal)

            pagination = JournalListParser.parse_pagination(page_html)
            logger.found(len(parsed), f"journal (Sayfa {page})")
            logger.info(f"Toplam: {len(journals)} journal")
            if not pagination.get("has_next"):
                logger.success("Journal pagination tamamlandi")
                break
            page += 1

        logger.success(f"Journal toplama tamamlandi: toplam={len(journals)}")
        return journals

    def _scrape_journal_detail(self, journal_url: str) -> Dict[str, Any]:
        logger.info(f"Journal detay aliniyor: {journal_url}")
        if not self.navigator.go_to_journal_page(journal_url):
            logger.warning("Journal detay sayfasi acilamadi")
            return {}
        self._close_modals()
        data = JournalDetailParser.parse_issn(self.selenium_driver.page_source)
        logger.info(
            f"Journal ISSN bilgisi alindi: issn={bool(data.get('issn'))}, eissn={bool(data.get('eissn'))}"
        )
        return data

    def _scrape_aims_and_scope(self, journal_url: str) -> str:
        logger.info(f"Aims and scope aliniyor: {journal_url}")
        if not self.navigator.go_to_aims_and_scope(journal_url):
            logger.warning("Aims and scope sayfasi acilamadi")
            return ""
        self._close_modals()
        from .parsers import AimsAndScopeParser

        text = AimsAndScopeParser.parse_text(self.selenium_driver.page_source)
        logger.info(f"Aims and scope uzunlugu: {len(text)}")
        return text

    def _scrape_volumes_and_issues(self, journal_url: str) -> List[Dict[str, Any]]:
        logger.info(f"Volumes & issues aliniyor: {journal_url}")
        if not self.navigator.go_to_issue_list(journal_url):
            logger.warning("Volumes & issues sayfasi acilamadi")
            return []
        self._close_modals()
        issues = VolumesAndIssuesParser.parse_issues(self.selenium_driver.page_source)
        logger.info(f"Issue sayisi: {len(issues)}")
        return issues

    def _scrape_issue_articles(self, issue_url: str, max_articles: Optional[int] = None) -> List[Dict[str, Any]]:
        logger.info(f"Issue article taramasi basladi: {issue_url}")
        all_articles: List[Dict[str, Any]] = []
        next_url = issue_url
        page_count = 0

        while next_url:
            self.check_stop_flag()
            page_count += 1
            logger.info(f"Issue pagination sayfasi: {page_count} -> {next_url}")
            if not self.navigator.go_to_issue_toc(next_url):
                logger.warning("Issue ToC sayfasi acilamadi")
                break
            self._close_modals()
            wait_for_page_load(self.selenium_driver)

            page_html = self.selenium_driver.page_source
            page_articles = ArticleListParser.parse_articles(page_html)
            all_articles.extend(page_articles)
            logger.info(f"Issue page {page_count}: makale={len(page_articles)}, biriken={len(all_articles)}")

            if max_articles and len(all_articles) >= max_articles:
                logger.info(f"Max article limitine ulasildi: {max_articles}")
                return all_articles[:max_articles]

            pagination = ArticleListParser.parse_pagination(page_html)
            next_url = pagination.get("next_page_url") if pagination.get("has_next") else None
            if next_url:
                self._random_wait()

        logger.success(f"Issue article taramasi tamamlandi: toplam={len(all_articles)}")
        return all_articles

    def _scrape_article_detail(self, article_url: str) -> Dict[str, Any]:
        logger.info(f"Makale detay aliniyor: {article_url}")
        if not self.navigator.go_to_article(article_url):
            logger.warning("Makale detay sayfasi acilamadi")
            return {}
        self._close_modals()
        wait_for_page_load(self.selenium_driver)
        detail = ArticleDetailParser.parse_article_detail(self.selenium_driver.page_source, article_url)
        if detail.get("title"):
            logger.success(f"Makale detay alindi: {detail['title'][:60]}...")
            logger.info(f"  doi={detail.get('doi', '-')}, authors={len(detail.get('authors', []))}")
        else:
            logger.warning(f"Makale detay parse edilemedi: {article_url}")
        return detail

    def _scrape_issue_articles_parallel(
        self,
        stubs: List[Dict[str, Any]],
        journal_name: str,
        max_tabs: int,
        article_progress_callback: Callable = None,
        existing_article_dois: set = None,
        reusable_drivers=None,
    ) -> List[Dict[str, Any]]:
        """Issue icindeki makale detaylarini worker havuzu ile paralel toplar."""
        existing_article_dois = existing_article_dois or set()
        candidates = [s for s in stubs if not (s.get("doi", "") and s.get("doi", "") in existing_article_dois)]
        skipped = len(stubs) - len(candidates)
        if skipped:
            logger.info(f"Parallel mod: {skipped} makale mevcut DOI nedeniyle atlandi")

        if not candidates:
            return []

        total = len(candidates)
        # Adaptif eşzamanlılık: yavaş/dengesiz hatta worker havuzunu kısıtla
        adaptive_tabs = concurrency_controller.effective_max_tabs('springer', max_tabs)
        worker_count = max(1, min(adaptive_tabs, total))
        jobs: queue.Queue[tuple[int, Dict[str, Any]]] = queue.Queue()
        for idx, stub in enumerate(candidates, start=1):
            jobs.put((idx, stub))

        results_by_index: Dict[int, Dict[str, Any]] = {}
        lock = threading.Lock()
        processed_count = 0

        # Build worker slots: (worker_id, driver, owns_driver, pool_index)
        worker_slots = []
        if reusable_drivers:
            for pool_index, driver in enumerate(reusable_drivers[:worker_count]):
                worker_id = pool_index + 1
                worker_slots.append((worker_id, driver, False, pool_index))
        else:
            for worker_id in range(1, worker_count + 1):
                local_driver = SeleniumDriver(
                    self.proxy_config,
                    headless=self.headless,
                    page_load_timeout=self.config.page_load_timeout,
                )
                if local_driver.start():
                    worker_slots.append((worker_id, local_driver, True, -1))
                else:
                    logger.warning(f"Worker-{worker_id}: local driver baslatilamadi")

        if not worker_slots:
            logger.warning("Parallel mod için kullanılabilir worker yok, boş liste dönülüyor")
            return []

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

                    detail_data: Dict[str, Any] = {}
                    article_url = stub.get("url", "")
                    try:
                        if article_url and local_driver.get(article_url, wait_after=4):
                            handle_cookie_consent(local_driver)
                            wait_for_page_load(local_driver)
                            detail_data = ArticleDetailParser.parse_article_detail(local_driver.page_source, article_url)
                    except RateLimitException as e:
                        logger.warning(f"Worker-{worker_id}: rate limit hatası")
                        if pool_index >= 0:
                            self._restart_single_worker(worker_id, pool_index, "rate_limit_error")
                        else:
                            local_driver.restart()
                        jobs.put((idx, stub))  # retry kuyruğuna geri koy
                        continue
                    except CloudflareBlockedException as e:
                        logger.warning(f"Worker-{worker_id}: Cloudflare bloklama hatası")
                        if pool_index >= 0:
                            self._restart_single_worker(worker_id, pool_index, "cloudflare_blocked")
                        else:
                            local_driver.restart()
                        jobs.put((idx, stub))  # retry kuyruğuna geri koy
                        continue
                    except Exception:
                        detail_data = {}

                    merged = {**stub, **detail_data}
                    merged["journal_name"] = journal_name
                    # Gerçek makale detayı alındıysa başarı say (sadece stub değil)
                    article_ok = bool(detail_data and detail_data.get("title"))
                    callback_payload = None

                    with lock:
                        nonlocal processed_count
                        processed_count += 1
                        results_by_index[idx] = merged

                        if article_progress_callback:
                            callback_payload = (
                                processed_count,
                                total,
                                merged.get("title") or stub.get("title"),
                            )

                    if callback_payload:
                        try:
                            article_progress_callback(*callback_payload)
                        except Exception:
                            pass

                    # Adaptif eşzamanlılık geri beslemesi (lock dışında — kendi lock'lı)
                    _fetch = getattr(local_driver, 'last_fetch', None)
                    concurrency_controller.record(
                        'springer',
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

        ordered = [results_by_index[i] for i in sorted(results_by_index.keys())]
        logger.info(
            "issue_fetch_summary",
            total=total,
            ok=len(ordered),
            effective_tabs=worker_count,
        )
        return ordered

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
        logger.header("SPRINGER JOURNAL ARTICLE AKISI BASLADI")
        existing_issue_urls = existing_issue_urls or set()
        existing_article_dois = existing_article_dois or set()
        max_articles = max_articles or self.config.max_articles

        journal_url = journal.get("url", "")
        if not journal_url:
            jid = journal.get("journal_id") or extract_journal_id_from_url(journal.get("url", ""))
            if not jid:
                logger.warning("Journal URL veya ID bulunamadi, atlandi")
                return []
            journal_url = f"{self.BASE_URL}/journal/{jid}"

        logger.info(
            f"Journal isleniyor: name={journal.get('name', 'unknown')}, depth={depth}, "
            f"max_articles={max_articles}, order={issues_order}"
        )

        if journal_name_callback and journal.get("name"):
            try:
                journal_name_callback(journal.get("name"))
            except Exception:
                pass

        detail = self._scrape_journal_detail(journal_url)
        if detail:
            journal.update(detail)

        journal["aims_and_scope"] = self._scrape_aims_and_scope(journal_url)

        all_issues = self._scrape_volumes_and_issues(journal_url)
        if issues_order == "oldest_first":
            all_issues = list(reversed(all_issues))

        new_issues = [i for i in all_issues if i.get("url") and i.get("url") not in existing_issue_urls]
        skipped = len(all_issues) - len(new_issues)
        if skipped:
            logger.info(f"{skipped} issue daha önce işlenmiş, atlanıyor. Yeni: {len(new_issues)}")

        if issues_order == "oldest_first":
            logger.info("[Springer] Issue sırası: eskiden yeniye (oldest_first)")
        else:
            logger.info("[Springer] Issue sırası: yeniden eskiye (newest_first)")

        issues_to_process = new_issues[:depth] if depth else new_issues
        logger.info(
            f"Toplam {len(all_issues)} issue, {len(issues_to_process)} tanesi işlenecek (depth={depth})"
        )

        issue_results: List[Dict[str, Any]] = []
        parallel_drivers: List[SeleniumDriver] = []

        try:
            # Oturum worker havuzu (bir kez açılır, tüm journal/issue'larda
            # yeniden kullanılır; burada KAPATILMAZ)
            parallel_drivers = self._ensure_worker_pool(max_tabs)

            for idx, issue in enumerate(issues_to_process, start=1):
                self.check_stop_flag()
                logger.info(f"Issue basladi ({idx}/{len(issues_to_process)}): {issue.get('title', '')}")

                if issue_start_callback:
                    pending = [x.get("title", "") for x in issues_to_process[idx:]]
                    try:
                        issue_start_callback(idx, len(issues_to_process), issue.get("title", f"Issue {idx}"), pending)
                    except Exception:
                        pass

                stubs = self._scrape_issue_articles(issue.get("url", ""), max_articles=max_articles)
                logger.info(f"Issue stub makale sayisi: {len(stubs)}")
                if article_list_callback:
                    try:
                        article_list_callback([a.get("title", "") for a in stubs])
                    except Exception:
                        pass

                if max_tabs > 1:
                    issue_articles = self._scrape_issue_articles_parallel(
                        stubs=stubs,
                        journal_name=journal.get("name", ""),
                        max_tabs=max_tabs if parallel_drivers else 1,
                        article_progress_callback=article_progress_callback,
                        existing_article_dois=existing_article_dois,
                        reusable_drivers=parallel_drivers,
                    )
                else:
                    issue_articles = []
                    for art_idx, stub in enumerate(stubs, start=1):
                        self.check_stop_flag()
                        logger.info(f"Makale isleniyor ({art_idx}/{len(stubs)}): {stub.get('title', '')}")

                        if article_progress_callback:
                            try:
                                article_progress_callback(art_idx, len(stubs), stub.get("title"))
                            except Exception:
                                pass

                        doi = stub.get("doi", "")
                        if doi and doi in existing_article_dois:
                            logger.info(f"Mevcut DOI atlandi: {doi}")
                            continue

                        detail_data = self._scrape_article_detail(stub.get("url", "")) if stub.get("url") else {}
                        merged = {**stub, **detail_data}
                        merged["journal_name"] = journal.get("name", "")
                        issue_articles.append(merged)
                        logger.success(f"Makale eklendi: {merged.get('title', '')[:50]}...")

                        if max_articles and len(issue_articles) >= max_articles:
                            logger.info(f"Issue max article limitine ulasildi: {max_articles}")
                            break

                        self._random_wait()

                issue_results.append({"issue_info": issue, "articles": issue_articles})
                logger.success(
                    f"Issue tamamlandi ({idx}/{len(issues_to_process)}): "
                    f"article_count={len(issue_articles)}"
                )

                if issue_complete_callback:
                    try:
                        issue_complete_callback(idx, len(issue_articles), [a.get("title", "") for a in issue_articles])
                    except Exception:
                        pass

        except ScraperStoppedException:
            logger.warning(f"{journal.get('name', 'Unknown')}: Stop sinyali alındı")
            raise
        except Exception as e:
            logger.error(f"{journal.get('name', 'Unknown')}: Hata: {e}")
            import traceback
            traceback.print_exc()
            return issue_results

        total_articles = sum(len(x.get("articles", [])) for x in issue_results)
        logger.found(total_articles, f"makale ({journal.get('name', 'Unknown')})")
        logger.success(
            f"Journal article akisi tamamlandi: issue_count={len(issue_results)}, total_articles={total_articles}"
        )
        return issue_results
