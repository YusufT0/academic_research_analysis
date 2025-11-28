"""
Science Direct Scraper Module
A modular, OOP-based web scraper for Science Direct with proxy support and Cloudflare bypass
"""

from config import ProxyConfig, ScienceDirectConfig
from driver import SeleniumDriver
from navigation import PageNavigator
from parsers import JournalParser, ArticleParser
from rate_limiter import RateLimiter
from scraper import ScienceDirectScraper
from utils import handle_cookie_consent, print_article_summary

__all__ = [
    'ProxyConfig',
    'ScienceDirectConfig',
    'SeleniumDriver',
    'PageNavigator',
    'JournalParser',
    'ArticleParser',
    'RateLimiter',
    'ScienceDirectScraper',
    'handle_cookie_consent',
    'print_article_summary',
]

__version__ = '1.0.0'
__author__ = 'Science Direct Scraper Team'
