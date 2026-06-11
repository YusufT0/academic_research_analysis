"""
Page navigation logic for Wiley Online Library scraper.

Handles:
- Journal list pagination (startPage parameter)
- Journal type detection (issue-based vs article-based)
- Issue list extraction from /loi/ pages
- Article list extraction from /toc/ and /index/ pages
"""

import sys
import time

sys.path.insert(0, str(__file__).rsplit('wiley', 1)[0])
from utils.logger import get_logger
logger = get_logger('wiley')


class PageNavigator:
    """
    Wiley sayfaları arasında gezinme işlemlerini yönetir.

    URL patterns:
    - Journal list: /action/showPublications?...&startPage=N&pageSize=20
    - Journal detail: /journal/{journal_id}
    - Aims & Scope: /hub/journal/{journal_id}/overview
    - Issue list: /loi/{journal_id}
    - Issue ToC: /toc/{journal_id}/{year}/{volume}/{issue}
    - Article index: /index/{journal_id}
    - Article detail: /doi/full/{doi}
    """

    def __init__(self, selenium_driver, domain: str):
        """
        Args:
            selenium_driver: SeleniumDriver instance
            domain: Wiley base domain (e.g. https://onlinelibrary.wiley.com)
        """
        self.driver = selenium_driver
        self.domain = domain

    def go_to_journal_list_page(self, base_url: str, page: int = 0, page_size: int = 20) -> bool:
        """
        Journal listesi sayfasına git.

        Wiley, startPage=0,1,2,... parametresiyle sayfalama yapar.
        Her sayfada ~20 journal bulunur.

        Args:
            base_url: WILEY_BASE_URL (.env'den)
            page: Sayfa numarası (0'dan başlar)
            page_size: Sayfa başına journal sayısı

        Returns:
            bool: Başarılıysa True
        """
        import re
        # \d* — startPage= boş olsa da (rakamsız) eşleşir
        if 'startPage=' in base_url:
            url = re.sub(r'startPage=\d*', f'startPage={page}', base_url)
        else:
            sep = '&' if '?' in base_url else '?'
            url = f"{base_url}{sep}startPage={page}"

        if 'pageSize=' in url:
            url = re.sub(r'pageSize=\d*', f'pageSize={page_size}', url)
        else:
            url = f"{url}&pageSize={page_size}"

        logger.info(f"Journal listesi sayfasına gidiliyor: sayfa {page}")
        ok = self.driver.get(url, wait_after=3)
        if ok:
            # Lazy-load / sonsuz scroll varsa liste sonunu tetikle
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                self.driver.execute_script("window.scrollTo(0, 0);")
            except Exception:
                pass
        return ok

    def go_to_journal_page(self, journal_id: str) -> bool:
        """
        Journal detay sayfasına git: /journal/{journal_id}

        Args:
            journal_id: Wiley journal ID (örn. "15213773")

        Returns:
            bool: Başarılıysa True
        """
        url = f"{self.domain}/journal/{journal_id}"
        logger.info(f"Journal sayfasına gidiliyor: {url}")
        return self.driver.get(url, wait_after=4)

    def go_to_aims_and_scope(self, journal_id: str) -> bool:
        """
        Aims & Scope sayfasına git: /hub/journal/{journal_id}/overview

        Args:
            journal_id: Wiley journal ID

        Returns:
            bool: Başarılıysa True
        """
        url = f"{self.domain}/hub/journal/{journal_id}/overview"
        logger.info(f"Aims & Scope sayfasına gidiliyor: {url}")
        return self.driver.get(url, wait_after=4)

    def go_to_issue_list(self, journal_id: str) -> bool:
        """
        Issue listesi sayfasına git: /loi/{journal_id}

        Args:
            journal_id: Wiley journal ID

        Returns:
            bool: Başarılıysa True
        """
        url = f"{self.domain}/loi/{journal_id}"
        logger.info(f"Issue listesine gidiliyor: {url}")
        return self.driver.get(url, wait_after=5)

    def go_to_article_index(self, journal_id: str) -> bool:
        """
        Article-based journal index sayfasına git: /index/{journal_id}

        Args:
            journal_id: Wiley journal ID

        Returns:
            bool: Başarılıysa True
        """
        url = f"{self.domain}/index/{journal_id}"
        logger.info(f"Article index sayfasına gidiliyor: {url}")
        return self.driver.get(url, wait_after=5)

    def go_to_issue_toc(self, toc_url: str) -> bool:
        """
        Issue Table of Contents sayfasına git.

        Args:
            toc_url: /toc/{journal_id}/{year}/{volume}/{issue} formatında URL
                     (absolute veya relative olabilir)

        Returns:
            bool: Başarılıysa True
        """
        if toc_url.startswith('/'):
            url = f"{self.domain}{toc_url}"
        elif not toc_url.startswith('http'):
            url = f"{self.domain}/{toc_url}"
        else:
            url = toc_url

        logger.info(f"Issue ToC sayfasına gidiliyor: {url}")
        return self.driver.get(url, wait_after=5)

    def go_to_article(self, doi_or_url: str) -> bool:
        """
        Makale detay sayfasına git.

        Args:
            doi_or_url: DOI string ("10.1002/...") veya tam URL

        Returns:
            bool: Başarılıysa True
        """
        if doi_or_url.startswith('http'):
            url = doi_or_url
        elif doi_or_url.startswith('/doi'):
            url = f"{self.domain}{doi_or_url}"
        else:
            # Ham DOI
            import urllib.parse
            encoded_doi = urllib.parse.quote(doi_or_url, safe='')
            url = f"{self.domain}/doi/full/{doi_or_url}"

        logger.info(f"Makale sayfasına gidiliyor: {url}")
        return self.driver.get(url, wait_after=4)

    def expand_decade_section(self, decade_link_selector: str) -> bool:
        """
        LOI sayfasındaki decade/yıl bölümünü genişlet (tıkla).

        Wiley'nin LOI sayfasında bazı decade grupları kapalı gelir;
        JavaScript ile tıklanarak içerikleri yüklenir.

        Args:
            decade_link_selector: CSS seçici veya href attribute değeri

        Returns:
            bool: Tıklama başarılıysa True
        """
        try:
            js = f"""
            (function() {{
                var el = document.querySelector("{decade_link_selector}");
                if (el) {{ el.click(); return true; }}
                return false;
            }})()
            """
            result = self.driver.execute_script(js)
            if result:
                logger.info(f"Decade bölümü genişletildi: {decade_link_selector}")
                time.sleep(1.5)
                return True
            return False
        except Exception as e:
            logger.warning(f"Decade genişletme hatası: {e}")
            return False

    def wait_for_element(self, css_selector: str, timeout: int = 10) -> bool:
        """
        Belirli bir elementin sayfada görünmesini bekle.

        Args:
            css_selector: CSS seçici
            timeout: Maksimum bekleme süresi (saniye)

        Returns:
            bool: Element bulunduysa True
        """
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                js = f"""
                return document.querySelector("{css_selector}") !== null;
                """
                result = self.driver.execute_script(js)
                if result:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def scroll_to_load_content(self, pause: float = 1.0) -> None:
        """
        Lazy-loaded içeriğin yüklenmesi için sayfayı scroll et.
        Wiley genellikle pagination kullanır ama bazı sayfalar scroll gerektirebilir.
        """
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause)
        except Exception as e:
            logger.warning(f"Scroll hatası: {e}")
