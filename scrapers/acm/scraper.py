"""
Main scraper class for ACM Digital Library
"""

import os
import sys
import time
import random
import queue
import threading
from typing import Optional, List, Dict, Any
from pathlib import Path

# Parent directory'yi path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
logger = get_logger('acm')

from .config import ProxyConfig, ACMConfig
from .driver import SeleniumDriver
from utils.adaptive_concurrency import controller as concurrency_controller
from .utils import handle_cookie_consent, handle_open_access_modal, wait_for_page_load
from .parsers import JournalParser, ArticleParser, ArticleDetailParser, IssueListParser
from .navigation import PageNavigator


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass

class RateLimitException(Exception):
    """Rate limit hatası olduğunda fırlatılır"""
    pass

class CloudflareBlockedException(Exception):
    """Cloudflare engeli aşılamadığında fırlatılır"""
    pass


class ACMScraper:
    """ACM Digital Library scraper ana sınıfı"""
    
    ACM_BASE = "https://dl.acm.org"
    
    def __init__(self, use_proxy: bool = None, headless: bool = False, stop_flag=None, pause_flag=None):
        """
        ACM scraper'ı başlatır

        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            stop_flag: threading.Event - durdurma sinyali için
            pause_flag: threading.Event - duraklatma sinyali için
        """
        self.stop_flag = stop_flag
        self.pause_flag = pause_flag
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
                logger.success("Proxy yapılandırması yüklendi:")
                logger.info(f"  - Host: {self.proxy_config.host}")
                logger.info(f"  - Port: {self.proxy_config.port}")
                logger.info(f"  - User: {self.proxy_config.user}")
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

        # Oturum boyunca yaşayan paralel worker driver havuzu.
        # Bir kez açılır; tüm journal/issue'larda yeniden kullanılır,
        # geçişlerde KAPATILMAZ. Yalnızca close() ile kapanır.
        self._worker_pool: List[SeleniumDriver] = []

        # Journal listesi
        self.all_journals = []
        
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
        logger.header("ACM Scraper Başlatılıyor...")
        
        if not self.selenium_driver.start():
            raise Exception("WebDriver başlatılamadı!")

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

    def _close_modals(self):
        """Cookie ve Open Access modallarını kapat"""
        handle_cookie_consent(self.selenium_driver, timeout=5)
        handle_open_access_modal(self.selenium_driver, timeout=5)
    
    def _random_wait(self):
        """Rate limiting için rastgele bekleme"""
        wait = random.uniform(self.config.min_wait, self.config.max_wait)
        logger.info(f"Rate limiting: {wait:.2f} saniye bekleniyor...")
        self._interruptible_sleep(wait)
    
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
                    self._interruptible_sleep(5)  # Yüklenmesi için bekle

                    # Modallar tekrar çıkabilir
                    if scroll_count % 5 == 0:
                        self._close_modals()

                    new_height = self.selenium_driver.execute_script("return document.body.scrollHeight")

                    if new_height == last_height:
                        logger.info("Sayfa sonuna ulaşıldı, kontrol için tekrar bekleniyor...")
                        self._interruptible_sleep(5)
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
    
    def extract_aims_and_scope(self, journal_code: str):
        """
        /journal/CODE sayfasından aims & scope bilgisini çıkarır.

        Sayfa yüklendikten sonra (More) butonu varsa JS ile tıklar,
        tam içerik DOM'a yazıldıktan sonra parse eder.

        Returns:
            str: HTML içeriği veya None
        """
        url = f"{self.ACM_BASE}/journal/{journal_code}"
        try:
            logger.info(f"Aims & scope için gidiliyor: {url}")
            if not self.selenium_driver.get(url, wait_after=3):
                return None
            self._close_modals()
            self.check_stop_flag()

            # (More) butonu varsa tıkla — kısa içeriklerde bu buton olmaz
            try:
                js_click_more = (
                    "(function() {"
                    " var btn = document.querySelector("
                    "'.item-meta__info .truncate-text .read-more');"
                    " if (btn) { btn.click(); return true; }"
                    " return false;"
                    "})()"
                )
                clicked = self.selenium_driver.execute_script(js_click_more)
                if clicked:
                    logger.info("(More) butonuna tıklandı, içerik genişletiliyor...")
                    self._interruptible_sleep(1.0)
            except Exception as e:
                logger.warning(f"(More) butonuna tıklama hatası: {e}")

            aims = JournalParser.extract_aims_and_scope(self.selenium_driver.page_source)
            if aims:
                logger.success(f"Aims & scope alındı ({len(aims)} karakter)")
                return aims

        except ScraperStoppedException:
            raise
        except CloudflareBlockedException:
            raise
        except Exception as e:
            logger.warning(f"Aims & scope alınamadı ({url}): {e}")

        logger.warning(f"{journal_code}: Aims & scope bulunamadı")
        return None

    def _extract_all_issues(
        self,
        journal_code: str,
        depth: int = None,
        existing_urls: set = None,
        issues_order: str = "newest_first",
    ) -> list:
        """
        LOI (Archive) sayfasından issue listesini toplar.

        Akış:
        1. /loi/CODE sayfasına git
        2. Decade sekmeleri varsa sırayla işle (gerekirse tıkla)
        3. Her decade içindeki year panel'larını işle:
           - DOM'da yüklü olanlar → parse et
           - Boş olanlar → JS ile year tab'a tıkla, AJAX yüklensin, parse et
        4. depth kadar YENİ issue toplandığında dur

        Returns:
            list: [{'url': '/toc/CODE/YEAR/VOL/ISSUE', 'title': str}, ...] (en yeniden eskiye)
        """
        existing_urls = existing_urls or set()
        all_issues = []
        seen_urls = set()

        def count_new():
            return sum(1 for i in all_issues if i['url'] not in existing_urls)

        def add_issues(issues):
            for i in issues:
                if i['url'] not in seen_urls:
                    seen_urls.add(i['url'])
                    all_issues.append(i)

        # 1. LOI sayfasına git
        loi_url = f"{self.ACM_BASE}/loi/{journal_code}"
        logger.info(f"LOI sayfasına gidiliyor: {loi_url}")
        if not self.selenium_driver.get(loi_url, wait_after=3):
            logger.warning("LOI sayfası yüklenemedi")
            return []

        self._close_modals()
        # Modal CDP click'leri sonrası sayfanın JS tab'larını render etmesini bekle
        wait_for_page_load(self.selenium_driver)
        self.check_stop_flag()

        # 2. Decade sekmeleri — JS render gecikebilir, birkaç kez dene
        decade_tabs = []
        for _attempt in range(5):
            decade_tabs = IssueListParser.extract_decade_tabs(self.selenium_driver.page_source)
            if decade_tabs:
                break
            # Tab'lar henüz DOM'da değil — kısa bekle
            time.sleep(1.0)
            self.check_stop_flag()

        logger.info(
            f"Decade sekmeleri: {[d['text'] for d in decade_tabs]}"
            if decade_tabs else "Decade sekmesi yok, tüm issue'lar sayfada"
        )

        if not decade_tabs:
            issues = IssueListParser.extract_all_issues_from_page(self.selenium_driver.page_source)
            add_issues(issues)
            logger.success(f"Toplam {len(all_issues)} issue ({count_new()} yeni)")
            return all_issues

        # 3. Her decade'i işle — issues_order'a göre yön belirle
        ordered_decades = decade_tabs if issues_order == "oldest_first" else list(reversed(decade_tabs))
        for decade_idx, decade in enumerate(ordered_decades):
            self.check_stop_flag()

            if depth and count_new() >= depth:
                break

            # En güncel decade ilk işlenir; eğer sayfa yüklenirken bu decade zaten
            # active değilse (eski bir decade active ise) tıklamak gerekir.
            need_click = not decade.get('is_active') or decade_idx > 0
            if need_click:
                logger.info(f"Decade sekmesine tıklanıyor: {decade['text']}")
                try:
                    js = (
                        f"var el = document.querySelector("
                        f"\"a.decade-item[data-url='{decade['data_url']}']\");"
                        f" if(el) el.click();"
                    )
                    self.selenium_driver.execute_script(js)
                    self._interruptible_sleep(2)
                    wait_for_page_load(self.selenium_driver)
                except Exception as e:
                    logger.warning(f"Decade tıklanamadı ({decade['text']}): {e}")
                    continue

            # 4. Bu decade'e ait year panellerini işle — en güncel yıldan başla (reversed)
            year_info = IssueListParser.extract_year_panel_info(
                self.selenium_driver.page_source,
                decade_panel_id=decade.get('panel_id'),
            )
            logger.info(f"Decade {decade['text']}: {len(year_info)} year sekmesi")

            ordered_years = year_info if issues_order == "oldest_first" else list(reversed(year_info))
            for year in ordered_years:
                self.check_stop_flag()

                if depth and count_new() >= depth:
                    break

                if year['has_issues']:
                    # Zaten DOM'da yüklü
                    issues = IssueListParser.extract_issues_from_panel(
                        self.selenium_driver.page_source, year['panel_id']
                    )
                    add_issues(issues)
                    logger.info(f"  Year {year['text']}: {len(issues)} issue (DOM'dan)")
                else:
                    # AJAX ile yükle: year tab'a tıkla
                    logger.info(f"  Year {year['text']}: AJAX ile yükleniyor...")
                    try:
                        panel_id = year['panel_id']
                        js = (
                            f"var el = document.querySelector("
                            f"\"a.year-item[aria-controls='{panel_id}']\");"
                            f" if(el) el.click();"
                        )

                        loaded = False
                        max_year_attempts = 3
                        for year_attempt in range(max_year_attempts):
                            if year_attempt > 0:
                                logger.info(
                                    f"  Year {year['text']}: yeniden yükleniyor "
                                    f"({year_attempt}/{max_year_attempts - 1})..."
                                )
                                # LOI sayfasını yeniden yükle, decade/year state sıfırlanır
                                if not self.selenium_driver.get(loi_url, wait_after=3):
                                    logger.warning(f"  Year {year['text']}: LOI sayfası yeniden yüklenemedi")
                                    break
                                self._close_modals()
                                # Decade tab'ına tekrar tıkla (eğer gerekiyorsa)
                                if need_click:
                                    try:
                                        js_decade = (
                                            f"var el = document.querySelector("
                                            f"\"a.decade-item[data-url='{decade['data_url']}']\");"
                                            f" if(el) el.click();"
                                        )
                                        self.selenium_driver.execute_script(js_decade)
                                        self._interruptible_sleep(2)
                                        wait_for_page_load(self.selenium_driver)
                                    except Exception:
                                        pass

                            self.selenium_driver.execute_script(js)

                            # Panel'de issue'ların belirmesini bekle (max 10 sn)
                            for _ in range(20):
                                self.check_stop_flag()
                                time.sleep(0.5)
                                if IssueListParser.extract_issues_from_panel(
                                    self.selenium_driver.page_source, panel_id
                                ):
                                    loaded = True
                                    break

                            if loaded:
                                break

                            logger.warning(
                                f"  Year {year['text']}: timeout "
                                f"(deneme {year_attempt + 1}/{max_year_attempts})"
                            )

                        issues = IssueListParser.extract_issues_from_panel(
                            self.selenium_driver.page_source, panel_id
                        )
                        add_issues(issues)
                        logger.info(
                            f"  Year {year['text']}: {len(issues)} issue "
                            f"({'yüklendi' if loaded else 'tüm denemeler başarısız'})"
                        )
                    except Exception as e:
                        logger.warning(f"  Year {year['text']} tıklanamadı: {e}")

            if depth and count_new() >= depth:
                break

        logger.success(f"Toplam {len(all_issues)} issue bulundu ({count_new()} yeni)")
        return all_issues

    def _process_single_issue(
        self,
        issue_stub: dict,
        max_articles: int = None,
        max_tabs: int = 1,
        article_progress_callback=None,
        article_list_callback=None,
        issue_idx: int = 1,
        total_issues: int = 1,
        reusable_drivers=None,
    ) -> dict:
        """
        Tek bir ACM issue sayfasına gidip makale detaylarını toplar.

        Args:
            issue_stub: {'url': '/toc/CODE/YEAR/VOL/ISSUE', 'title': str}
            max_articles: Bu issue için maksimum makale sayısı
            issue_idx / total_issues: Loglama için konum bilgisi

        Returns:
            dict: {'issue_info': {...}, 'articles': [...]}
        """
        issue_url = issue_stub['url']
        full_issue_url = (
            f"{self.ACM_BASE}{issue_url}" if issue_url.startswith('/') else issue_url
        )

        logger.section(f"Issue {issue_idx}/{total_issues}: {issue_stub.get('title', issue_url)}")
        logger.info(f"  Issue URL: {full_issue_url}")

        if not self.selenium_driver.get(full_issue_url, wait_after=5):
            logger.warning(f"Issue sayfası yüklenemedi: {full_issue_url}")
            return {'issue_info': self._extract_issue_info_from_url(full_issue_url), 'articles': []}

        self._close_modals()

        # Cloudflare kontrolü
        title = self.selenium_driver.execute_script("return document.title") or ""
        if "just a moment" in title.lower() or "cloudflare" in title.lower():
            raise CloudflareBlockedException("Cloudflare engeli algılandı (issue sayfası)")

        current_url = self.selenium_driver.current_url
        issue_info = self._extract_issue_info_from_url(current_url)

        stub_title = issue_stub.get('title', '').strip()
        if stub_title:
            issue_info['issue_number'] = stub_title

        logger.success(f"  Issue: {issue_info.get('issue_number')} | {issue_info.get('date')}")

        # Makale URL'lerini al
        page_source = self.selenium_driver.page_source
        article_list = ArticleParser.extract_article_urls(page_source)

        if not article_list:
            logger.warning(f"  Makale bulunamadı: {issue_stub.get('title')}")
            return {'issue_info': issue_info, 'articles': []}

        if max_articles and len(article_list) > max_articles:
            logger.info(f"  Makale sayısı {len(article_list)} -> {max_articles} ile sınırlandı")
            article_list = article_list[:max_articles]

        logger.info(f"  {len(article_list)} makale toplanacak...")

        if article_list_callback:
            try:
                article_list_callback([a.get('title', '') for a in article_list])
            except Exception:
                pass

        if max_tabs > 1:
            articles, retry_queue = self._process_issue_articles_parallel(
                article_list=article_list,
                max_tabs=max_tabs,
                article_progress_callback=article_progress_callback,
                reusable_drivers=reusable_drivers,
            )
            consecutive_failures = 0
        else:
            articles = []
            retry_queue = []
            consecutive_failures = 0

            for idx, article_stub in enumerate(article_list, 1):
                self.check_stop_flag()

                if article_progress_callback:
                    try:
                        article_progress_callback(idx, len(article_list), None)
                    except Exception:
                        pass

                article_url = article_stub.get('url', '')
                full_url = f"{self.ACM_BASE}{article_url}" if article_url.startswith('/') else article_url
                stub_title = article_stub.get('title', '')
                logger.info(f"[{idx}/{len(article_list)}] Makale detayı alınıyor: {stub_title[:60] if stub_title else full_url}")

                article_data = None
                success = False

                for attempt in range(2):
                    if attempt > 0:
                        self._interruptible_sleep(2)

                    if not self.selenium_driver.get(full_url, wait_after=3):
                        continue

                    self._close_modals()
                    # Modal etkileşimleri sonrası sayfa settle olana kadar bekle
                    wait_for_page_load(self.selenium_driver)

                    article_data = ArticleDetailParser.extract_article_details(
                        self.selenium_driver.page_source, full_url
                    )

                    if article_data and article_data.get('title'):
                        success = True
                        break

                if success and article_data:
                    articles.append(article_data)
                    logger.success(f"Makale eklendi: {article_data['title'][:50]}...")
                    consecutive_failures = 0
                else:
                    retry_queue.append(full_url)
                    consecutive_failures += 1

                if article_progress_callback:
                    try:
                        article_progress_callback(
                            idx, len(article_list),
                            article_data.get('title') if (success and article_data) else None
                        )
                    except Exception:
                        pass

                if consecutive_failures >= 3:
                    logger.error("Üst üste 3 makale hatası! Tarayıcı yeniden başlatılıyor...")
                    self.selenium_driver.restart()
                    self._interruptible_sleep(60)
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
                    if not self.selenium_driver.get(r_url, wait_after=3):
                        logger.warning(f"Retry başarısız, makale atlanıyor: {r_url}")
                        continue
                    self._close_modals()
                    wait_for_page_load(self.selenium_driver)

                    article_data = ArticleDetailParser.extract_article_details(
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
        return {'issue_info': issue_info, 'articles': articles}

    def _process_issue_articles_parallel(
        self,
        article_list: List[Dict[str, Any]],
        max_tabs: int,
        article_progress_callback=None,
        reusable_drivers=None,
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Issue içindeki makaleleri worker havuzu ile paralel işler."""
        total = len(article_list)
        # Adaptif eşzamanlılık: yavaş/dengesiz hatta worker havuzunu kısıtla
        adaptive_tabs = concurrency_controller.effective_max_tabs('acm', max_tabs)
        worker_count = max(1, min(adaptive_tabs, total))
        jobs: queue.Queue[tuple[int, Dict[str, Any]]] = queue.Queue()
        for idx, stub in enumerate(article_list, 1):
            jobs.put((idx, stub))

        results_by_index: Dict[int, Dict[str, Any]] = {}
        retry_urls: List[str] = []
        lock = threading.Lock()
        processed_count = 0

        # Build worker slots: (worker_id, driver, owns_driver, pool_index)
        # pool_index: eğer reusable_drivers'dan geliyorsa pool'daki index, yoksa -1
        worker_slots = []
        if reusable_drivers:
            for pool_idx, driver in enumerate(reusable_drivers[:worker_count]):
                worker_id = pool_idx + 1
                worker_slots.append((worker_id, driver, False, pool_idx))
        else:
            for worker_id in range(1, worker_count + 1):
                local_driver = SeleniumDriver(self.proxy_config, headless=self.headless)
                if local_driver.start():
                    worker_slots.append((worker_id, local_driver, True, -1))
                else:
                    logger.warning(f"Worker-{worker_id}: local driver başlatılamadı")

        if not worker_slots:
            logger.warning("Parallel mod için kullanılabilir worker yok, retry kuyruğuna alınıyor")
            while not jobs.empty():
                try:
                    _, stub = jobs.get_nowait()
                    article_url = stub.get('url', '')
                    full_url = f"{self.ACM_BASE}{article_url}" if article_url.startswith('/') else article_url
                    retry_urls.append(full_url)
                except queue.Empty:
                    break
            return [], retry_urls

        def _worker(worker_id: int, local_driver, owns_driver: bool, pool_index: int = -1):
            """
            Worker thread: article'ları paralel işler.
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
                    full_url = f"{self.ACM_BASE}{article_url}" if article_url.startswith('/') else article_url
                    article_data = None

                    for attempt in range(2):
                        if attempt > 0:
                            time.sleep(1)
                        try:
                            if not local_driver.get(full_url, wait_after=3):
                                continue
                            page_source = local_driver.page_source
                            article_data = ArticleDetailParser.extract_article_details(page_source, full_url)
                            if article_data and article_data.get('title'):
                                break
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
                            retry_urls.append(full_url)

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
                        'acm',
                        ok=article_ok,
                        duration_s=getattr(_fetch, 'duration_s', 0.0) if _fetch else 0.0,
                        recovered=getattr(_fetch, 'recovered', False) if _fetch else False,
                    )
            finally:
                if owns_driver:
                    local_driver.close()

        threads = [
            threading.Thread(target=_worker, args=(wid, drv, owns, pidx), daemon=True)
            for wid, drv, owns, pidx in worker_slots
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
        depth: int = 1,
        max_articles: int = None,
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
        Bir journal'ın aims & scope bilgisini alır ve issue'larını + makalelerini toplar.

        Akış:
        1. /journal/CODE → Aims & scope çıkar
        2. /loi/CODE     → Issue listesi al (depth kadar yeni issue)
        3. Her issue için /toc/CODE/YEAR/VOL/ISSUE → Makale detayları topla

        Args:
            journal: Journal bilgileri dict'i (code, name, url, ...)
            depth: Kaç YENİ issue işlenecek (1 = sadece en yeni, None = tümü)
            max_articles: Her issue için maksimum makale sayısı (None ise config'den)
            article_progress_callback: İlerleme callback'i
            article_list_callback: Makale listesi callback'i
            existing_issue_urls: DB'de zaten var olan issue URL'leri.
                                  Bu URL'ler depth sayımına dahil edilmez.

        Returns:
            list[dict]: [{'issue_info': {...}, 'articles': [...]}, ...]
        """
        if max_articles is None:
            max_articles = self.config.max_articles

        existing_issue_urls = existing_issue_urls or set()
        journal_code = journal.get('code', '')
        journal_name = journal.get('name', 'Unknown')

        if not journal_code:
            logger.warning(f"{journal_name}: Journal kodu bulunamadı")
            return []

        # Tekil URL analizi akışında gerçek journal adını sayfadan çözümle
        if journal.get('resolve_name_from_url'):
            journal_page_url = f"{self.ACM_BASE}/journal/{journal_code}"
            try:
                if self.selenium_driver.get(journal_page_url, wait_after=3):
                    self._close_modals()
                    wait_for_page_load(self.selenium_driver)
                    resolved_name = JournalParser.extract_journal_name_from_journal_page(
                        self.selenium_driver.page_source
                    )
                    if resolved_name:
                        journal['name'] = resolved_name
                        journal_name = resolved_name
                        if journal_name_callback:
                            try:
                                journal_name_callback(resolved_name)
                            except Exception:
                                pass
                        logger.success(f"ACM journal adı çözümlendi: {resolved_name}")
                    else:
                        logger.warning("ACM journal adı çözümlenemedi, mevcut isim kullanılacak")
            except Exception as e:
                logger.warning(f"ACM journal adı çözümleme hatası: {e}")

        logger.header(f"JOURNAL TARANMAYA BAŞLANIYOR: {journal_name} ({journal_code})")

        try:
            self.check_stop_flag()

            # 1) Aims & scope
            aims_and_scope = self.extract_aims_and_scope(journal_code)
            journal['aims_and_scope'] = aims_and_scope

            self.check_stop_flag()

            # 2) Issue listesi
            all_issues = self._extract_all_issues(
                journal_code,
                depth=depth,
                existing_urls=existing_issue_urls,
                issues_order=issues_order,
            )

            if not all_issues:
                logger.warning(f"{journal_name}: Issue bulunamadı")
                return []

            # 3) Yeni issue'ları filtrele, depth kadar al
            new_issues = [i for i in all_issues if i['url'] not in existing_issue_urls]
            skipped = len(all_issues) - len(new_issues)
            if skipped:
                logger.info(f"{skipped} issue zaten var, atlanıyor. Yeni: {len(new_issues)}")

            # Issue sırası toplama aşamasında uygulandı
            if issues_order == "oldest_first":
                logger.info("[ACM] Issue sırası: eskiden yeniye (oldest_first)")
            else:
                logger.info("[ACM] Issue sırası: yeniden eskiye (newest_first)")

            issues_to_process = new_issues[:depth] if depth else new_issues
            logger.info(
                f"Toplam {len(all_issues)} issue, {len(issues_to_process)} tanesi işlenecek "
                f"(depth={depth})"
            )

            # 4) Oturum worker havuzu (bir kez açılır, tüm journal/issue'larda
            #    yeniden kullanılır; burada KAPATILMAZ)
            parallel_drivers = self._ensure_worker_pool(max_tabs)

            # 5) Her issue'yu işle
            issue_results = []
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

                result = self._process_single_issue(
                    issue_stub=issue_stub,
                    max_articles=max_articles,
                    max_tabs=max_tabs if parallel_drivers else 1,
                    article_progress_callback=article_progress_callback,
                    article_list_callback=article_list_callback,
                    issue_idx=issue_idx,
                    total_issues=len(issues_to_process),
                    reusable_drivers=parallel_drivers,
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

        except (ScraperStoppedException, CloudflareBlockedException):
            raise
        except Exception as e:
            logger.error(f"{journal_name}: Hata: {e}")
            import traceback
            traceback.print_exc()
            return []

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
            
            # Modalları kapat
            self._close_modals()
            wait_for_page_load(self.selenium_driver)
            
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
                
                # Journal'ın issue'larındaki makaleleri al
                issue_results = self.scrape_journal_articles(
                    journal,
                    max_articles=max_articles_per_journal
                )

                # Sonuçlara ekle (issue_results: [{issue_info, articles}, ...])
                for res in issue_results:
                    result['articles'].extend(res.get('articles', []))
                
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
