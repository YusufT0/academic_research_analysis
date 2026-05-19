"""
Main scraper class for Science Direct
"""

import os
import sys
import time
import queue
import threading
from typing import Optional, List, Dict, Any
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
from backend.core.config import settings
from utils.network_probe import effective_page_load_timeout
from utils.adaptive_concurrency import controller as concurrency_controller


class ScraperStoppedException(Exception):
    """Scraper durdurulduğunda fırlatılır"""
    pass

class RateLimitException(Exception):
    """Rate limit hatası olduğunda fırlatılır"""
    pass

class CloudflareBlockedException(Exception):
    """Cloudflare engeli aşılamadığında fırlatılır"""
    pass


class ScienceDirectScraper:
    """Science Direct scraper ana sınıfı"""
    
    def __init__(self, use_proxy: bool = None, headless: bool = False,
                 use_undetected: bool = True, stop_flag=None, pause_flag=None):
        """
        Science Direct scraper'ı başlatır

        Args:
            use_proxy: Proxy kullanılsın mı (None ise .env'den okunur)
            headless: Tarayıcı görünmez modda çalışsın mı
            use_undetected: undetected-chromedriver kullan (Cloudflare bypass)
            stop_flag: threading.Event - durdurma sinyali için
            pause_flag: threading.Event - duraklatma sinyali için
        """
        self.stop_flag = stop_flag
        self.pause_flag = pause_flag
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

        # Oturum boyunca yaşayan paralel worker driver havuzu.
        # Bir kez açılır; tüm journal/issue'larda yeniden kullanılır,
        # geçişlerde KAPATILMAZ. Yalnızca close() ile kapanır.
        self._worker_pool: List[SeleniumDriver] = []

    def initialize(self):
        """Scraper'ı başlatır"""
        logger.header("Science Direct Scraper Başlatılıyor...")
        
        self.driver = self.selenium_driver.start()
        self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
        self.rate_limiter = RateLimiter(self.driver, selenium_driver=self.selenium_driver)
        
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
            wd = SeleniumDriver(
                self.proxy_config,
                headless=getattr(self.selenium_driver, 'headless', False),
                use_undetected=getattr(self.selenium_driver, 'use_undetected', True),
            )
            try:
                wd.start()
                self._worker_pool.append(wd)
                logger.info(f"Worker-{worker_id}: oturum havuzuna eklendi")
            except Exception:
                logger.warning(f"Worker-{worker_id}: havuz driver'ı başlatılamadı")
                break
        if self._worker_pool:
            logger.info(
                f"Oturum worker havuzu hazır: {len(self._worker_pool)} driver "
                f"(journal/issue boyunca yeniden kullanılır)"
            )
        return self._worker_pool

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
                headless=getattr(self.selenium_driver, 'headless', False),
                use_undetected=getattr(self.selenium_driver, 'use_undetected', True),
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
                
                # Sayfanın ilk yüklenmesini bekle (sabit sleep yerine)
                logger.loading("Cloudflare kontrolü bekleniyor")
                WebDriverWait(self.driver, self.config.timeout).until(
                    lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
                )
                
                # Cloudflare challenge görünüyorsa kısa, adaptif bekleme yap
                try:
                    challenge_detected = self.driver.execute_script("""
                        const url = (window.location.href || '').toLowerCase();
                        const body = (document.body?.innerText || '').toLowerCase();
                        return url.includes('challenge') || body.includes('captcha') || body.includes('checking your browser');
                    """)
                except Exception:
                    challenge_detected = False
                
                if challenge_detected:
                    logger.warning("Cloudflare challenge algılandı, geçiş bekleniyor...")
                    try:
                        WebDriverWait(self.driver, 8, poll_frequency=0.25).until(
                            lambda d: not d.execute_script("""
                                const url = (window.location.href || '').toLowerCase();
                                const body = (document.body?.innerText || '').toLowerCase();
                                return url.includes('challenge') || body.includes('captcha') || body.includes('checking your browser');
                            """)
                        )
                    except TimeoutException:
                        pass
                
                logger.success("Sayfa başarıyla yüklendi")
                logger.info(f"  - Sayfa başlığı: {self.driver.title}")
                logger.info(f"  - URL: {self.driver.current_url}")

                # Liste/arama alanı için hızlı, birleşik hazır olma kontrolü
                try:
                    WebDriverWait(self.driver, 4, poll_frequency=0.2).until(
                        lambda d: d.execute_script("""
                            return !!(
                                document.querySelector('#publications-list') ||
                                document.querySelector('div.publications-list') ||
                                document.querySelector('ul.publications-list') ||
                                document.querySelector('span.pagination-pages-label')
                            );
                        """)
                    )
                except TimeoutException:
                    # Bloklayıcı bir hata değil; parse aşamasında yeniden kontrol edilecek
                    pass

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
                    self._interruptible_sleep(2)
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
                        self._interruptible_sleep(2)  # Yeniden başlatma sonrası kısa bekleme
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

            # publications-list yüklenene kadar bekle (hızlı/uyarlanabilir)
            logger.loading("Sayfa yükleniyor")
            try:
                WebDriverWait(self.driver, 8, poll_frequency=0.2).until(
                    lambda d: d.execute_script("""
                        return !!(
                            document.querySelector('#publications-list') ||
                            document.querySelector('div.publications-list') ||
                            document.querySelector('ul.publications-list')
                        );
                    """)
                )
            except TimeoutException:
                pass

            # Cookie popup'ını kapat
            handle_cookie_consent(self.driver)

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
    
    def extract_journal_about_info(self, journal_url: str) -> dict:
        """
        Journal sayfasından about bilgilerini (aims & scope) çıkarır.

        Nav'da About sekmesi varsa /about/aims-and-scope sayfasına giderek
        .js-aims-and-scope içeriğini alır; yoksa doğrudan journal sayfasındaki
        .about-content-wrapper > span.spaced içeriğini kullanır.

        Args:
            journal_url: Journal'ın ana sayfası URL'i

        Returns:
            dict: {'aims_and_scope': html_str veya None, 'journal_name': str veya None}
        """
        try:
            full_url = f"https://www.sciencedirect.com{journal_url}" if journal_url.startswith('/') else journal_url
            logger.info(f"Journal about bilgileri alınıyor: {full_url}")
            self.driver.get(full_url)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "main"))
                )
            except Exception:
                pass
            time.sleep(0.5)
            handle_cookie_consent(self.driver)

            page_source = self.driver.page_source
            journal_name = JournalParser.extract_journal_name_from_journal_page(page_source)
            has_about = JournalParser.has_about_nav_item(page_source)

            aims_and_scope = None
            if has_about:
                about_url = full_url.rstrip('/') + '/about/aims-and-scope'
                logger.info(f"About sekmesi bulundu, aims-and-scope sayfasına gidiliyor: {about_url}")
                self.driver.get(about_url)
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "main"))
                    )
                except Exception:
                    pass
                time.sleep(0.5)
                handle_cookie_consent(self.driver)
                aims_and_scope = JournalParser.extract_aims_scope_from_about_page(self.driver.page_source)
            else:
                logger.info("About sekmesi yok, journal ana sayfasından aims & scope alınıyor")
                aims_and_scope = JournalParser.extract_aims_scope_from_journal_page(page_source)

            if aims_and_scope:
                logger.success(f"Aims & scope alındı ({len(aims_and_scope)} karakter)")
            else:
                logger.warning("Aims & scope bulunamadı")

            return {'aims_and_scope': aims_and_scope, 'journal_name': journal_name}

        except Exception as e:
            logger.failed("Journal about info çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return {'aims_and_scope': None, 'journal_name': None}

    def _navigate_to_last_issues_page(self) -> None:
        """Issues sayfasının son sayfasına gider (oldest_first için)."""
        import re
        # Önce "Last page" butonu dene
        try:
            last_btn = self.driver.find_element(
                By.CSS_SELECTOR, "button[aria-label='Last page']:not([disabled])"
            )
            self.driver.execute_script("arguments[0].click();", last_btn)
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#all-issues li.accordion-panel"))
                )
            except Exception:
                pass
            time.sleep(0.5)
            handle_cookie_consent(self.driver)
            logger.info("Son sayfaya gidildi (Last page butonu)")
            return
        except Exception:
            pass

        # "Go to page N" butonlarından en büyük sayıyı bul
        try:
            page_buttons = self.driver.find_elements(
                By.CSS_SELECTOR, "button[aria-label^='Go to page']"
            )
            last_page = max(
                (int(m.group()) for btn in page_buttons
                 if (m := re.search(r'\d+', btn.get_attribute('aria-label') or ''))),
                default=None
            )
            if last_page and last_page > 1:
                base_url = self.driver.current_url.split('?')[0]
                self.driver.get(f"{base_url}?page={last_page}")
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#all-issues li.accordion-panel"))
                    )
                except Exception:
                    pass
                time.sleep(0.5)
                handle_cookie_consent(self.driver)
                logger.info(f"Son sayfaya gidildi: page={last_page}")
                return
        except Exception as e:
            logger.warning(f"Son sayfa navigasyonu hatası: {e}")

        logger.info("Tek sayfa veya son sayfa zaten aktif")

    def extract_all_issues_from_issues_page(
        self,
        journal_url: str,
        depth: int = None,
        existing_urls: set = None,
        issues_order: str = "newest_first",
    ) -> list:
        """
        /issues sayfasına gider ve issue listesini döndürür (en yeni önce).

        Strateji:
        - Sayfada zaten açık olan panelleri parse eder.
        - Depth sayısı kadar YENİ (DB'de olmayan) issue toplandığında durur.
          existing_urls verilmişse, o URL'lere sahip issue'lar depth sayımına
          dahil edilmez; daha eskiye bakılmaya devam edilir.
        - Pagination varsa sonraki sayfaya geçer.
        - depth=None ise tüm sayfalar ve tüm paneller işlenir.

        Args:
            journal_url: Journal'ın ana sayfası URL'i (tam veya relative)
            depth: Hedef YENİ issue sayısı
            existing_urls: DB'de zaten var olan issue URL'leri (relative path kısmı)

        Returns:
            list: [{'url': str, 'title': str, 'status': str}, ...]
        """
        existing_urls = existing_urls or set()

        def _count_new(issues: list) -> int:
            """Verilen listede DB'de olmayan issue sayısını döndür"""
            if not existing_urls:
                return len(issues)
            return sum(1 for i in issues if i['url'] not in existing_urls)

        try:
            base_url = (
                f"https://www.sciencedirect.com{journal_url}"
                if journal_url.startswith('/') else journal_url
            ).rstrip('/')
            issues_url = f"{base_url}/issues"

            logger.info(f"Issues sayfasına gidiliyor: {issues_url}")
            self.driver.get(issues_url)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#all-issues"))
                )
            except Exception:
                pass
            time.sleep(0.5)
            handle_cookie_consent(self.driver)

            # oldest_first: son sayfadan başla, geriye doğru git
            if issues_order == "oldest_first":
                self._navigate_to_last_issues_page()

            all_issues = []

            while True:  # pagination döngüsü
                # 1. Şu an sayfada açık olan panellerdeki issue'ları al
                current_page_issues = JournalParser.parse_issues_from_issues_page(
                    self.driver.page_source
                )

                # 2. Depth dolmadıysa kapalı accordion'ları birer birer aç
                # (depth sayımında yalnızca yeni issue'lar hesaba katılır)
                if depth is None or _count_new(all_issues) + _count_new(current_page_issues) < depth:
                    closed_buttons = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "#all-issues li.accordion-panel button.accordion-panel-title[aria-expanded='false']"
                    )
                    # oldest_first: en alttaki accordion'dan başla (en eski issue'lar)
                    if issues_order == "oldest_first":
                        closed_buttons = list(reversed(closed_buttons))
                    logger.info(f"Bu sayfada {len(closed_buttons)} kapalı accordion var")

                    for btn in closed_buttons:
                        # Açılanları tekrar parse et, yeni issue sayısı yeterliyse dur
                        current_page_issues = JournalParser.parse_issues_from_issues_page(
                            self.driver.page_source
                        )
                        if depth and _count_new(all_issues) + _count_new(current_page_issues) >= depth:
                            break

                        try:
                            panel_id = btn.get_attribute('aria-controls')
                            # Butonu görünür alana kaydır, JS click ile tıkla
                            # (sticky header/overlay nedeniyle normal click çalışmıyor)
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn
                            )
                            time.sleep(0.3)
                            self.driver.execute_script("arguments[0].click();", btn)

                            # Önce butonun aria-expanded=true olmasını bekle (hızlı),
                            # ardından panel içeriğinin yüklenmesini bekle
                            WebDriverWait(self.driver, 10).until(
                                lambda d: btn.get_attribute("aria-expanded") == "true"
                            )
                            if panel_id:
                                WebDriverWait(self.driver, 30).until(
                                    EC.presence_of_element_located((
                                        By.CSS_SELECTOR,
                                        f"[id='{panel_id}'] section.js-issue-list-content"
                                    ))
                                )
                            else:
                                self._interruptible_sleep(2)

                        except TimeoutException:
                            logger.warning(
                                f"Accordion içeriği yüklenemedi: "
                                f"{btn.get_attribute('id') or '?'}, atlanıyor"
                            )
                        except Exception as e:
                            logger.warning(f"Accordion açma hatası: {e}")

                # 3. Bu sayfadaki tüm açık içeriği topla
                current_page_issues = JournalParser.parse_issues_from_issues_page(
                    self.driver.page_source
                )
                all_issues.extend(current_page_issues)
                new_so_far = _count_new(all_issues)
                skipped = len(all_issues) - new_so_far
                logger.info(
                    f"Bu sayfadan {len(current_page_issues)} issue toplandı "
                    f"(toplam: {len(all_issues)}, yeni: {new_so_far}, atlanacak: {skipped})"
                )

                # 4. Yeterli sayıda YENİ issue toplandıysa dur
                if depth and new_so_far >= depth:
                    break

                # 5. Sonraki/önceki sayfa var mı?
                try:
                    if issues_order == "oldest_first":
                        page_btn = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "button[aria-label='Previous page']:not([disabled])"
                        )
                        page_btn.click()
                        try:
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "#all-issues li.accordion-panel"))
                            )
                        except Exception:
                            pass
                        time.sleep(0.5)
                        handle_cookie_consent(self.driver)
                    else:
                        page_btn = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "button[aria-label='Next page']:not([disabled])"
                        )
                        page_btn.click()
                        try:
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "#all-issues li.accordion-panel"))
                            )
                        except Exception:
                            pass
                        time.sleep(0.5)
                        handle_cookie_consent(self.driver)
                except Exception:
                    logger.info("Issues sayfasında ilk/son sayfaya ulaşıldı")
                    break

            logger.success(f"Toplam {len(all_issues)} issue bulundu ({_count_new(all_issues)} yeni)")
            return all_issues

        except Exception as e:
            logger.failed("Issues sayfası çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return []

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
        Tek bir issue sayfasına gider, makale URL'lerini ve issue bilgilerini çıkarır,
        her makaleyi tek tek işler.

        Args:
            issue_stub: {'url': str, 'title': str, 'status': str}
            max_articles: Bu issue için maksimum makale sayısı
            issue_idx / total_issues: Loglama için konum bilgisi

        Returns:
            dict: {'issue_info': {...}, 'articles': [...]}
        """
        issue_url = issue_stub['url']
        full_issue_url = (
            f"https://www.sciencedirect.com{issue_url}"
            if issue_url.startswith('/') else issue_url
        )

        logger.section(f"Issue {issue_idx}/{total_issues}: {issue_stub.get('title', issue_url)}")
        logger.info(f"  Issue URL: {full_issue_url}")

        self.driver.get(full_issue_url)
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )
        except Exception:
            pass
        time.sleep(0.5)
        handle_cookie_consent(self.driver)

        # Issue bilgilerini al
        issue_info = ArticleParser.extract_issue_info(self.driver.page_source)
        issue_info['url'] = self.driver.current_url
        logger.success(f"  Issue: {issue_info.get('issue_number')} | {issue_info.get('date')}")

        # Makale URL'lerini ve başlıklarını al
        article_stubs = ArticleParser.extract_article_urls_from_issue(self.driver.page_source)

        if not article_stubs:
            logger.warning(f"  Issue için makale bulunamadı: {issue_stub.get('title')}")
            return {'issue_info': issue_info, 'articles': []}

        if max_articles:
            article_stubs = article_stubs[:max_articles]
            logger.info(f"  İlk {max_articles} makale işlenecek")

        # Makale listesini (başlıklarıyla birlikte) UI'a bildir
        if article_list_callback:
            try:
                article_list_callback([a.get('title', '') for a in article_stubs])
            except Exception:
                pass

        if max_tabs > 1:
            articles, failed_stubs = self._process_issue_articles_parallel(
                article_stubs=article_stubs,
                max_tabs=max_tabs,
                article_progress_callback=article_progress_callback,
                reusable_drivers=reusable_drivers,
            )

            if failed_stubs:
                logger.info(f"{len(failed_stubs)} makale paralel aşamada alınamadı, tekli retry yapılıyor...")
                for article_stub in failed_stubs:
                    self.check_stop_flag()
                    article_url = article_stub.get('url', '')
                    article_details = self.extract_article_details(article_url, retry_attempt=1)
                    if article_details:
                        article_details['journal_name'] = None
                        article_details['issue_number'] = issue_info.get('issue_number')
                        article_details['issue_date'] = issue_info.get('date')
                        articles.append(article_details)

            if self.rate_limiter.retry_queue:
                retry_results = self._process_retry_queue()
                for r in retry_results:
                    r['issue_number'] = issue_info.get('issue_number')
                    r['issue_date'] = issue_info.get('date')
                articles.extend(retry_results)
        else:
            articles = []
            for idx, article_stub in enumerate(article_stubs, 1):
                article_url = article_stub['url']
                self.check_stop_flag()

                if article_progress_callback:
                    try:
                        article_progress_callback(idx, len(article_stubs), None)
                    except Exception:
                        pass

                stub_title = article_stub.get('title', '')
                logger.info(f"[{idx}/{len(article_stubs)}] Makale detayı alınıyor: {stub_title[:60] if stub_title else article_url}")
                article_details = self.extract_article_details(article_url)

                if article_details:
                    article_details['journal_name'] = None  # caller fills this
                    article_details['issue_number'] = issue_info.get('issue_number')
                    article_details['issue_date'] = issue_info.get('date')
                    articles.append(article_details)
                    self.rate_limiter.reset_consecutive_failures()
                else:
                    logger.warning("  Makale detayları alınamadı")

                if article_progress_callback:
                    try:
                        article_progress_callback(
                            idx, len(article_stubs),
                            article_details.get('title') if article_details else None
                        )
                    except Exception:
                        pass

                if self.rate_limiter.should_wait_for_failures():
                    self.rate_limiter.wait_for_failures()
                    retry_results = self._process_retry_queue()
                    for r in retry_results:
                        r['issue_number'] = issue_info.get('issue_number')
                        r['issue_date'] = issue_info.get('date')
                    articles.extend(retry_results)

                self.rate_limiter.random_wait()

            # Kalan retry queue
            if self.rate_limiter.retry_queue:
                retry_results = self._process_retry_queue()
                for r in retry_results:
                    r['issue_number'] = issue_info.get('issue_number')
                    r['issue_date'] = issue_info.get('date')
                articles.extend(retry_results)

        logger.found(len(articles), f"makale (issue {issue_idx})")
        return {'issue_info': issue_info, 'articles': articles}

    def _process_issue_articles_parallel(
        self,
        article_stubs: List[Dict[str, Any]],
        max_tabs: int,
        article_progress_callback=None,
        reusable_drivers=None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Issue içindeki makaleleri worker havuzu ile paralel işler."""
        total = len(article_stubs)
        # Adaptif eşzamanlılık: yavaş/dengesiz hatta worker havuzunu kısıtla
        adaptive_tabs = concurrency_controller.effective_max_tabs('sciencedirect', max_tabs)
        worker_count = max(1, min(adaptive_tabs, total))
        jobs: queue.Queue[tuple[int, Dict[str, Any]]] = queue.Queue()
        for idx, stub in enumerate(article_stubs, 1):
            jobs.put((idx, stub))

        results_by_index: Dict[int, Dict[str, Any]] = {}
        failed_stubs: List[Dict[str, Any]] = []
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
                    headless=getattr(self.selenium_driver, 'headless', False),
                    use_undetected=getattr(self.selenium_driver, 'use_undetected', True),
                )
                try:
                    local_driver.start()
                    worker_slots.append((worker_id, local_driver, True, -1))
                except Exception:
                    logger.warning(f"Worker-{worker_id}: local driver başlatılamadı")

        if not worker_slots:
            logger.warning("Parallel mod için kullanılabilir worker yok, retry kuyruğuna alınıyor")
            while not jobs.empty():
                try:
                    _, stub = jobs.get_nowait()
                    failed_stubs.append(stub)
                except queue.Empty:
                    break
            return [], failed_stubs

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
                        idx, article_stub = jobs.get_nowait()
                    except queue.Empty:
                        return

                    article_url = article_stub.get('url', '')
                    full_url = (
                        f"https://www.sciencedirect.com{article_url}"
                        if article_url.startswith('/') else article_url
                    )
                    article_data = None

                    try:
                        if local_driver.get(full_url, wait_after=2):
                            try:
                                WebDriverWait(local_driver.driver, 8).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "main, article, #article-content, .article-content"))
                                )
                            except Exception:
                                pass

                            article_data = ArticleParser.extract_article_details(
                                local_driver.driver.page_source,
                                article_url,
                            )
                    except RateLimitException as e:
                        logger.warning(f"Worker-{worker_id}: rate limit hatası")
                        if pool_index >= 0:
                            self._restart_single_worker(worker_id, pool_index, "rate_limit_error")
                        else:
                            local_driver.restart()
                        jobs.put((idx, article_stub))  # retry kuyruğuna geri koy
                        continue
                    except CloudflareBlockedException as e:
                        logger.warning(f"Worker-{worker_id}: Cloudflare bloklama hatası")
                        if pool_index >= 0:
                            self._restart_single_worker(worker_id, pool_index, "cloudflare_blocked")
                        else:
                            local_driver.restart()
                        jobs.put((idx, article_stub))  # retry kuyruğuna geri koy
                        continue
                    except Exception as e:
                        logger.debug(f"Worker-{worker_id}: makale yükleme hatası: {e}")
                        article_data = None

                    article_ok = bool(article_data and article_data.get('title'))

                    with lock:
                        nonlocal processed_count
                        processed_count += 1
                        if article_ok:
                            article_data['journal_name'] = None
                            results_by_index[idx] = article_data
                        else:
                            failed_stubs.append(article_stub)

                        if article_progress_callback:
                            try:
                                article_progress_callback(
                                    processed_count,
                                    total,
                                    article_data.get('title') if article_data else None,
                                )
                            except Exception:
                                pass

                    # Adaptif eşzamanlılık geri beslemesi (lock dışında — kendi lock'lı)
                    _fetch = getattr(local_driver, 'last_fetch', None)
                    concurrency_controller.record(
                        'sciencedirect',
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
            failed=len(failed_stubs),
            effective_tabs=worker_count,
        )
        return ordered_articles, failed_stubs

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
            # Sayfa yükleme zaman aşımı: ağ hızına göre adaptif (hardcoded 10/30 yerine)
            _nc = getattr(self.selenium_driver, 'network_class', 'fast')
            _eff = effective_page_load_timeout(settings.sd_timeout, _nc)
            self.driver.set_page_load_timeout(_eff)
            try:
                self.driver.get(full_url)
            except TimeoutException:
                # Timeout aştıktan sonra DOM içeriği erişilebilir, devam et
                pass
            try:
                WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "main, article, #article-content, .article-content"))
                )
            except Exception:
                pass

            # Content Error kontrolü ("There was a problem providing the content")
            if self.rate_limiter.check_content_error():
                logger.warning("Content error tespit edildi!")
                
                if retry_attempt == 0:
                    # İlk deneme - 30 saniye bekle ve YENİ USER AGENT ile tarayıcıyı yeniden başlat
                    logger.info("İlk content error - Tarayıcı yeni User Agent ile başlatılacak (30 saniye bekleme)...")
                    if self.rate_limiter.handle_content_error(full_url, wait_time=30, force_restart=True):
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
                    # İkinci deneme - Bu sefer sabit 3 dakika bekle
                    logger.info("İkinci content error - Sabit 3 dakika bekleme...")
                    if self.rate_limiter.handle_content_error(full_url, wait_time=180, force_restart=False):
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
    
    def scrape_journal_articles(
        self,
        journal_info: dict,
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
    ) -> list:
        """
        Bir journal'ın issue'larını ve makalelerini tarar.

        Args:
            journal_info: Journal bilgisi (name, url, ...)
            depth: Kaç YENİ issue işlenecek (1 = sadece en yeni, None/0 = tümü)
            max_articles: Her issue için maksimum makale sayısı (None = hepsi)
            article_progress_callback: İlerleme callback'i
            article_list_callback: Makale listesi callback'i
            existing_issue_urls: DB'de zaten var olan issue URL'leri (relative path).
                                  Bu URL'lere sahip issue'lar depth sayımına dahil edilmez.

        Returns:
            list[dict]: Her eleman bir issue'ya ait sonuç:
                        {'issue_info': {...}, 'articles': [...]}
        """
        existing_issue_urls = existing_issue_urls or set()

        try:
            logger.header(f"JOURNAL TARANMAYA BAŞLANIYOR: {journal_info['name']}")

            # 1. Journal about bilgilerini (aims & scope) çıkar
            about_info = self.extract_journal_about_info(journal_info['url'])
            journal_info.update(about_info)
            if journal_info.get('resolve_name_from_url') and about_info.get('journal_name'):
                journal_info['name'] = about_info['journal_name']
                if journal_name_callback:
                    try:
                        journal_name_callback(about_info['journal_name'])
                    except Exception:
                        pass
                logger.success(f"ScienceDirect journal adı çözümlendi: {journal_info['name']}")

            # 2. /issues sayfasından issue listesini al
            # existing_issue_urls geçilir → yalnızca yeni issue'lar depth'e sayılır
            all_issues = self.extract_all_issues_from_issues_page(
                journal_info['url'],
                depth=depth,
                existing_urls=existing_issue_urls,
                issues_order=issues_order,
            )

            if not all_issues:
                logger.warning(f"{journal_info['name']} için issue bulunamadı")
                return []

            # Zaten DB'de olanları atla; kalan yeni issue'lardan depth kadar al
            new_issues = [i for i in all_issues if i['url'] not in existing_issue_urls]
            skipped_count = len(all_issues) - len(new_issues)

            if skipped_count:
                logger.info(
                    f"{skipped_count} issue daha önce işlenmiş, atlanıyor. "
                    f"Yeni issue sayısı: {len(new_issues)}"
                )

            # Issue sırası toplama aşamasında uygulandı
            if issues_order == "oldest_first":
                logger.info("[SD] Issue sırası: eskiden yeniye (oldest_first)")
            else:
                logger.info("[SD] Issue sırası: yeniden eskiye (newest_first)")

            issues_to_process = new_issues if not depth else new_issues[:depth]
            logger.info(
                f"Toplam {len(all_issues)} issue bulundu, "
                f"{len(issues_to_process)} tanesi işlenecek (depth={depth})"
            )

            # 3. Journal-level worker havuzu: tüm issue'lar boyunca yeniden kullanılır
            # Oturum worker havuzu (bir kez açılır, tüm journal/issue'larda
            # yeniden kullanılır; burada KAPATILMAZ)
            parallel_drivers = self._ensure_worker_pool(max_tabs)

            # 4. Her issue'yu işle
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

                # Journal bilgilerini makalelere ekle
                for article in result['articles']:
                    article['journal_name'] = journal_info['name']
                    article['journal_url'] = journal_info['url']
                    print_article_summary(article, len(result['articles']))

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

            # 4. Tüm journal için final failed articles denemesi
            if self.rate_limiter.failed_articles:
                logger.section(
                    f"SON DENEME: Failed articles işleniyor "
                    f"({len(self.rate_limiter.failed_articles)} makale)"
                )
                final_retry = self._process_failed_articles()
                # Failed articles hangi issue'ya ait bilinmiyor; son issue'ya ekle
                if issue_results and final_retry:
                    issue_results[-1]['articles'].extend(final_retry)

            total_articles = sum(len(r['articles']) for r in issue_results)
            logger.header(f"{journal_info['name']} TARAMASI TAMAMLANDI")
            logger.stats({
                'İşlenen Issue': len(issue_results),
                'Toplam Makale': total_articles,
            })
            if self.rate_limiter.failed_articles:
                logger.error(f"{len(self.rate_limiter.failed_articles)} makale kalıcı olarak başarısız")
                for failed_url in self.rate_limiter.failed_articles:
                    logger.info(f"   - {failed_url}")

            return issue_results

        except ScraperStoppedException:
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
        
        last_page_urls = set()
        restart_count = 0
        
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
            
            current_urls = {j['url'] for j in journals if j.get('url')}
            if current_urls and current_urls.issubset(last_page_urls):
                logger.warning("Kopya liste tespit edildi (aynı sayfa tekrar yüklendi/aynı makaleler alındı)!")
                if restart_count < 3:
                    logger.info("Liste komple sıfırlanıyor, sayfa 1'e dönülüyor...")
                    all_journals.clear()
                    page_count = 0
                    restart_count += 1
                    last_page_urls.clear()
                    
                    self.driver.get(self.config.base_url)
                    try:
                        WebDriverWait(self.driver, 15).until(
                            EC.presence_of_element_located((By.ID, "publications-list"))
                        )
                    except Exception:
                        pass
                    time.sleep(0.5)
                    handle_cookie_consent(self.driver)
                    # update navigator info
                    self.navigator = PageNavigator(self.driver, selenium_driver=self.selenium_driver)
                    continue
                else:
                    logger.error("Maksimum sayfa sıfırlama limitine ulaşıldı, geçiliyor.")
                    break
                    
            last_page_urls = current_urls
            
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
            self._interruptible_sleep(2)

        logger.header("Tarama Tamamlandı!")
        logger.stats({
            'Toplam Journal': len(all_journals),
            'Taranan Sayfa': page_count
        })
        
        return all_journals
    
    def close(self):
        """Scraper'ı kapatır (oturum sonu — worker havuzu dahil)"""
        logger.separator()
        for wd in self._worker_pool:
            try:
                wd.close()
            except Exception as close_err:
                logger.warning(f"Worker driver kapatma hatası: {close_err}")
        self._worker_pool = []
        self.selenium_driver.close()
