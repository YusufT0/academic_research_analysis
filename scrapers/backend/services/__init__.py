"""
Services module
"""

from .scraper_manager import ScraperManager
from .nlp_service import NLPService, nlp_service

__all__ = ["ScraperManager", "NLPService", "nlp_service"]
