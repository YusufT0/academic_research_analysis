"""
Database Repositories Package
"""

from .base import BaseRepository
from .journal_repository import JournalRepository
from .issue_repository import IssueRepository
from .article_repository import ArticleRepository
from .embedding_repository import EmbeddingRepository
from .cluster_repository import ClusterRepository
from .analysis_run_repository import AnalysisRunRepository

# Cached repositories lazy import - circular import önlemek için
def get_cached_repositories():
    """Cached repository'leri lazy olarak import et"""
    from .cached_repositories import (
        CachedArticleRepository,
        CachedJournalRepository,
        CachedIssueRepository
    )
    return CachedArticleRepository, CachedJournalRepository, CachedIssueRepository

__all__ = [
    "BaseRepository",
    "JournalRepository",
    "IssueRepository",
    "ArticleRepository",
    # Analysis Repositories
    "EmbeddingRepository",
    "ClusterRepository",
    "AnalysisRunRepository",
    # Cached Repositories (lazy import function)
    "get_cached_repositories",
]
