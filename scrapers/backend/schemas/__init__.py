"""
Pydantic Schemas for API
"""

from .common import PaginationParams, PaginatedResponse, SortOrder
from .journal import JournalResponse, JournalListResponse, JournalFilter
from .issue import IssueResponse, IssueListResponse, IssueFilter
from .article import ArticleResponse, ArticleListResponse, ArticleFilter, ArticleSearchParams
from .scraper import (
    ScraperStatus,
    ScraperType,
    ScraperStateResponse,
    ScraperProgressResponse,
    ScraperControlRequest,
    ScraperStatsResponse,
)

__all__ = [
    # Common
    "PaginationParams",
    "PaginatedResponse", 
    "SortOrder",
    # Journal
    "JournalResponse",
    "JournalListResponse",
    "JournalFilter",
    # Issue
    "IssueResponse",
    "IssueListResponse",
    "IssueFilter",
    # Article
    "ArticleResponse",
    "ArticleListResponse",
    "ArticleFilter",
    "ArticleSearchParams",
    # Scraper
    "ScraperStatus",
    "ScraperType",
    "ScraperStateResponse",
    "ScraperProgressResponse",
    "ScraperControlRequest",
    "ScraperStatsResponse",
]
