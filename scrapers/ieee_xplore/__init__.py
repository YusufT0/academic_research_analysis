"""
IEEE Xplore Scraper - Modular OOP Implementation

This package provides a modular web scraping solution for IEEE Xplore.
Structure follows the same pattern as science_direct module.
"""

from .config import ProxyConfig, IEEEXploreConfig
from .driver import SeleniumDriver
from .navigation import PageNavigator
from .parsers import JournalParser, ArticleParser
from .utils import handle_cookie_consent, wait_for_page_load
from .scraper import IEEEXploreScraper

__all__ = [
    'ProxyConfig',
    'IEEEXploreConfig',
    'SeleniumDriver',
    'PageNavigator',
    'JournalParser',
    'ArticleParser',
    'handle_cookie_consent',
    'wait_for_page_load',
    'IEEEXploreScraper',
]

__version__ = '1.0.0'
