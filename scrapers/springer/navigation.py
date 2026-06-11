"""Page navigation logic for Springer scraper."""

import sys

sys.path.insert(0, str(__file__).rsplit('springer', 1)[0])
from utils.logger import get_logger

logger = get_logger("springer")


class PageNavigator:
    """Springer sayfaları arasında gezinme işlemlerini yönetir."""

    def __init__(self, selenium_driver, domain: str):
        self.driver = selenium_driver
        self.domain = domain.rstrip("/")

    def go_to_journal_list_page(self, base_url: str, page: int = 1, page_size: int = 20) -> bool:
        _ = page_size
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}page={page}"
        logger.info(f"Journal listesi sayfasina gidiliyor: {url}")
        return self.driver.get(url, wait_after=3)

    def go_to_journal_page(self, journal_url: str) -> bool:
        url = journal_url if journal_url.startswith("http") else f"{self.domain}{journal_url}"
        logger.info(f"Journal sayfasina gidiliyor: {url}")
        return self.driver.get(url, wait_after=4)

    def go_to_aims_and_scope(self, journal_url: str) -> bool:
        url = journal_url.rstrip("/") + "/aims-and-scope"
        logger.info(f"Aims & Scope sayfasina gidiliyor: {url}")
        return self.driver.get(url, wait_after=4)

    def go_to_issue_list(self, journal_url: str) -> bool:
        url = journal_url.rstrip("/") + "/volumes-and-issues"
        logger.info(f"Issue listesine gidiliyor: {url}")
        return self.driver.get(url, wait_after=5)

    def go_to_article_index(self, journal_url: str) -> bool:
        url = journal_url if journal_url.startswith("http") else f"{self.domain}{journal_url}"
        logger.info(f"Issue sayfasina gidiliyor: {url}")
        return self.driver.get(url, wait_after=5)

    def go_to_issue_toc(self, toc_url: str) -> bool:
        if toc_url.startswith('/'):
            url = f"{self.domain}{toc_url}"
        elif not toc_url.startswith('http'):
            url = f"{self.domain}/{toc_url}"
        else:
            url = toc_url
        logger.info(f"Issue ToC sayfasina gidiliyor: {url}")
        return self.driver.get(url, wait_after=5)

    def go_to_article(self, article_url: str) -> bool:
        url = article_url if article_url.startswith("http") else f"{self.domain}{article_url}"
        logger.info(f"Makale sayfasina gidiliyor: {url}")
        return self.driver.get(url, wait_after=4)
