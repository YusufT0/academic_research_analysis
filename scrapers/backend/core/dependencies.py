"""
FastAPI Dependencies
"""

from typing import Optional
from functools import lru_cache

from database import DatabaseService, get_database_service

# Scraper manager singleton
_scraper_manager: Optional["ScraperManager"] = None


def get_db_service() -> DatabaseService:
    """Database service dependency"""
    return get_database_service()


def get_scraper_manager() -> "ScraperManager":
    """Scraper manager dependency"""
    global _scraper_manager
    if _scraper_manager is None:
        from ..services.scraper_manager import ScraperManager
        _scraper_manager = ScraperManager()
    return _scraper_manager


def set_scraper_manager(manager: "ScraperManager"):
    """Scraper manager'ı set et (startup'ta kullanılır)"""
    global _scraper_manager
    _scraper_manager = manager
