"""
Core modules - Config, Dependencies, Events
"""

from .config import settings, Settings
from .dependencies import get_db_service, get_scraper_manager

__all__ = [
    "settings",
    "Settings",
    "get_db_service",
    "get_scraper_manager",
]
