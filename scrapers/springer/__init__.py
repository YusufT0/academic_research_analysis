"""
Springer Online Library Scraper - Modular OOP Implementation

This package provides a modular web scraping solution for Springer Online Library.
Structure follows the same pattern as ieee_xplore, science_direct and acm modules.
"""

from .config import ProxyConfig, SpringerConfig
from .driver import SeleniumDriver
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser
from .utils import handle_cookie_consent, wait_for_page_load
from .scraper import SpringerScraper, ScraperStoppedException
from .rate_limiter import SpringerRateLimiter, RateLimitException

__all__ = [
    'ProxyConfig',
    'SpringerConfig',
    'SeleniumDriver',
    'PageNavigator',
    'JournalParser',
    'ArticleParser',
    'handle_cookie_consent',
    'wait_for_page_load',
    'SpringerScraper',
    'ScraperStoppedException',
    'SpringerRateLimiter',
    'RateLimitException',
]

__version__ = '1.0.0'
