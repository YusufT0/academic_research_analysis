"""
ACM Scraper Package
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from .config import ProxyConfig, ACMConfig
from .driver import SeleniumDriver
from .utils import handle_cookie_consent, handle_open_access_modal, wait_for_page_load
from .parsers import JournalParser, ArticleParser, ArticleDetailParser
from .navigation import PageNavigator
from .scraper import ACMScraper, ScraperStoppedException

__all__ = [
    'ProxyConfig',
    'ACMConfig',
    'SeleniumDriver',
    'handle_cookie_consent',
    'handle_open_access_modal',
    'wait_for_page_load',
    'JournalParser',
    'ArticleParser',
    'ArticleDetailParser',
    'PageNavigator',
    'ACMScraper',
    'ScraperStoppedException',
]
