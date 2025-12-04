"""
API Routers
"""

from .journals import router as journals_router
from .issues import router as issues_router
from .articles import router as articles_router
from .scrapers import router as scrapers_router
from .stats import router as stats_router

__all__ = [
    "journals_router",
    "issues_router", 
    "articles_router",
    "scrapers_router",
    "stats_router",
]
