"""
Wiley Online Library Scraper - Modular OOP Implementation

This package provides a modular web scraping solution for Wiley Online Library.
Structure follows the same pattern as ieee_xplore, science_direct and acm modules.
"""

from .config import ProxyConfig, WileyConfig
from .driver import SeleniumDriver
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser
from .utils import handle_cookie_consent, wait_for_page_load
from .scraper import WileyScraper, ScraperStoppedException
from .rate_limiter import WileyRateLimiter, RateLimitException

__all__ = [
    'ProxyConfig',
    'WileyConfig',
    'SeleniumDriver',
    'PageNavigator',
    'JournalParser',
    'ArticleParser',
    'handle_cookie_consent',
    'wait_for_page_load',
    'WileyScraper',
    'ScraperStoppedException',
    'WileyRateLimiter',
    'RateLimitException',
]

__version__ = '1.0.0'
