"""
API Routers
"""

from .journals import router as journals_router
from .issues import router as issues_router
from .articles import router as articles_router
from .scrapers import router as scrapers_router
from .stats import router as stats_router
from .nlp import router as nlp_router
from .websocket import router as websocket_router
from .search import router as search_router

__all__ = [
    "journals_router",
    "issues_router", 
    "articles_router",
    "scrapers_router",
    "stats_router",
    "nlp_router",
    "websocket_router",
    "search_router",
]

