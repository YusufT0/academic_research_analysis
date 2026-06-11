"""
Retry Decorators — tenacity

Database, scraper ve HTTP operasyonları için standart retry pattern.

Kullanım:
    @db_retry
    async def save_article(data): ...
    
    @scraper_retry
    def scrape_page(url): ...
"""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

logger = logging.getLogger("retry")


# Database operasyonları: 3 deneme, exponential backoff (1s, 2s, 4s)
db_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# Scraper operasyonları: 5 deneme, exponential + jitter
scraper_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1, max=30),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# HTTP istekleri: 3 deneme, sabit bekleme
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# Selenium operasyonları: yavaş timeout'larda artan backoff ile tekrar dener.
# selenium importu try/except ile sarılır ki backend selenium yokken de
# import edilebilsin (ör. sadece API/analiz çalıştırılırken).
try:
    from selenium.common.exceptions import TimeoutException as _SeleniumTimeout

    def make_selenium_retry(
        max_attempts: int = 3,
        backoff_base: float = 1.5,
        backoff_cap: float = 30.0,
    ):
        """Settings'ten parametrelerle Selenium-aware retry dekoratörü üretir."""
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_random_exponential(multiplier=backoff_base, max=backoff_cap),
            retry=retry_if_exception_type((_SeleniumTimeout,)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    # Varsayılan parametrelerle hazır dekoratör
    selenium_retry = make_selenium_retry()
    SELENIUM_RETRY_AVAILABLE = True
except ImportError:  # selenium kurulu değil — backend yine de import edilebilsin
    SELENIUM_RETRY_AVAILABLE = False

    def make_selenium_retry(*args, **kwargs):  # type: ignore[misc]
        """selenium yokken no-op passthrough dekoratör."""
        def _identity(fn):
            return fn
        return _identity

    selenium_retry = make_selenium_retry()
