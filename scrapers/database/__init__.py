"""
Database Package

MongoDB ile async veritabanı işlemleri için modüller.
Beanie ODM kullanır.

Kullanım:
    from database import init_database_service, get_database_service
    
    # Async context içinde
    service = await init_database_service()
    
    # Dergi ekle
    journal, created = await service.add_journal(
        name="IEEE Access",
        source_website="ieeexplore",
        publisher="IEEE"
    )
    
    # Sayı ekle
    issue, created = await service.add_issue(
        journal=journal,
        issue_number="Volume 13",
        date="2025"
    )
    
    # Makale ekle
    article, created = await service.add_article(
        issue=issue,
        title="My Article",
        url="/document/12345/",
        doi="10.1109/ACCESS.2025.12345"
    )
"""

from .config import DatabaseSettings, get_database_settings
from .connection import (
    DatabaseConnection,
    get_database,
    database_context,
    init_database,
    close_database,
)
from .models import Journal, Issue, Article
from .repositories import (
    JournalRepository,
    IssueRepository,
    ArticleRepository,
)
from .service import (
    DatabaseService,
    get_database_service,
    init_database_service,
)

__all__ = [
    # Config
    "DatabaseSettings",
    "get_database_settings",
    
    # Connection
    "DatabaseConnection",
    "get_database",
    "database_context",
    "init_database",
    "close_database",
    
    # Models
    "Journal",
    "Issue",
    "Article",
    
    # Repositories
    "JournalRepository",
    "IssueRepository",
    "ArticleRepository",
    
    # Service
    "DatabaseService",
    "get_database_service",
    "init_database_service",
]
