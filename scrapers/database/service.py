"""
Database Service
Scraperların kullanacağı üst seviye API
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from beanie import PydanticObjectId

from .connection import get_database, init_database, close_database
from .models import Journal, Issue, Article
from .repositories import JournalRepository, IssueRepository, ArticleRepository

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

logger = get_logger('database_service')


def _get_cache():
    """Lazy import to avoid circular dependency"""
    try:
        from backend.services.cache_service import cache_service
        return cache_service
    except Exception:
        return None


def _get_es():
    """Lazy import to avoid circular dependency"""
    try:
        from backend.services.elasticsearch_service import elasticsearch_service
        return elasticsearch_service
    except Exception:
        return None


class DatabaseService:
    """
    Database Service
    
    Scraperların kullanacağı üst seviye API.
    Repository'leri koordine eder ve transaction-like işlemleri yönetir.
    """
    
    def __init__(self):
        self.journal_repo = JournalRepository()
        self.issue_repo = IssueRepository()
        self.article_repo = ArticleRepository()
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Service'i initialize et (database bağlantısı dahil)"""
        if self._initialized:
            return True
        
        success = await init_database()
        if success:
            self._initialized = True
            logger.success("Database service hazır")
        return success
    
    async def close(self):
        """Bağlantıyı kapat"""
        await close_database()
        self._initialized = False
        logger.info("Database service kapatıldı")
    
    # ==================== Journal İşlemleri ====================
    
    async def add_journal(
        self,
        name: str,
        source_website: str,
        url: Optional[str] = None,
        publisher: Optional[str] = None,
        open_access: bool = False,
        letter_group: Optional[str] = None,
        journal_type: str = "Journal",
        **kwargs
    ) -> tuple[Journal, bool]:
        """
        Dergi ekle veya güncelle
        
        Returns:
            tuple: (Journal, created: bool)
        """
        import time
        start_time = time.time()
        
        journal, created = await self.journal_repo.upsert(
            name=name,
            source_website=source_website,
            url=url,
            publisher=publisher,
            open_access=open_access,
            letter_group=letter_group,
            type=journal_type,
            **kwargs
        )
        
        try:
            from backend.core.metrics import DB_OPERATION_DURATION
            DB_OPERATION_DURATION.labels(operation="upsert_journal").observe(time.time() - start_time)
        except ImportError:
            pass
        
        if created:
            logger.success(f"Yeni dergi eklendi: {name}")
            _cache = _get_cache()
            if _cache:
                await _cache.invalidate_pattern("stats:*")
                await _cache.invalidate_pattern("journals_list_*")
        else:
            logger.info(f"Dergi güncellendi: {name}")
        
        return journal, created
    
    async def get_journal(
        self,
        name: str,
        source_website: str
    ) -> Optional[Journal]:
        """Dergi getir"""
        return await self.journal_repo.find_by_name(name, source_website)
    
    async def get_all_journals(
        self,
        source_website: Optional[str] = None
    ) -> List[Journal]:
        """Tüm dergileri getir"""
        if source_website:
            return await self.journal_repo.find_by_source(source_website)
        return await self.journal_repo.get_all(limit=10000)
    
    # ==================== Issue İşlemleri ====================
    
    async def add_issue(
        self,
        journal: Journal,
        issue_number: Optional[str] = None,
        date: Optional[str] = None,
        url: Optional[str] = None,
        status: Optional[str] = None,
        **kwargs
    ) -> tuple[Issue, bool]:
        """
        Sayı ekle veya güncelle
        
        Args:
            journal: Bağlı olduğu dergi
            issue_number: Sayı numarası (Volume 13, Issue 5)
            date: Yayın tarihi string
            url: Issue sayfası URL'si
            status: Durum
        
        Returns:
            tuple: (Issue, created: bool)
        """
        import time
        start_time = time.time()
        
        issue, created = await self.issue_repo.upsert(
            journal_id=journal.id,
            journal_name=journal.name,
            source_website=journal.source_website,
            issue_number=issue_number,
            date=date,
            url=url,
            status=status,
            **kwargs
        )
        
        try:
            from backend.core.metrics import DB_OPERATION_DURATION
            DB_OPERATION_DURATION.labels(operation="upsert_issue").observe(time.time() - start_time)
        except ImportError:
            pass
        
        if created:
            # Dergi sayı sayısını güncelle
            await self.journal_repo.increment_counts(journal.id, issue_increment=1)
            logger.success(f"Yeni sayı eklendi: {journal.name} - {issue_number}")
        else:
            logger.info(f"Sayı güncellendi: {journal.name} - {issue_number}")
        
        return issue, created
    
    async def get_issues_by_journal(
        self,
        journal_id: PydanticObjectId
    ) -> List[Issue]:
        """Derginin tüm sayılarını getir"""
        return await self.issue_repo.find_by_journal(journal_id)
    
    async def get_latest_issue(
        self,
        journal_id: PydanticObjectId
    ) -> Optional[Issue]:
        """Derginin en son sayısını getir"""
        return await self.issue_repo.find_latest_by_journal(journal_id)
    
    # ==================== Article İşlemleri ====================
    
    async def add_article(
        self,
        issue: Issue,
        title: str,
        url: str,
        doi: Optional[str] = None,
        authors: Optional[List[str]] = None,
        abstract: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        publication_date: Optional[str] = None,
        pdf_url: Optional[str] = None,
        article_type: Optional[str] = None,
        **kwargs
    ) -> tuple[Article, bool]:
        """
        Makale ekle veya güncelle
        
        Returns:
            tuple: (Article, created: bool)
        """
        import time
        start_time = time.time()
        
        article, created = await self.article_repo.upsert(
            url=url,
            title=title,
            journal_id=issue.journal_id,
            journal_name=issue.journal_name,
            issue_id=issue.id,
            issue_number=issue.issue_number,
            source_website=issue.source_website,
            doi=doi,
            authors=authors or [],
            abstract=abstract,
            keywords=keywords or [],
            publication_date=publication_date,
            pdf_url=pdf_url,
            article_type=article_type,
            **kwargs
        )
        
        try:
            from backend.core.metrics import DB_OPERATION_DURATION
            DB_OPERATION_DURATION.labels(operation="upsert_article").observe(time.time() - start_time)
        except ImportError:
            pass
        
        if created:
            # Sayı ve dergi makale sayılarını güncelle
            await self.issue_repo.increment_article_count(issue.id)
            await self.journal_repo.increment_counts(issue.journal_id, article_increment=1)
            logger.success(f"Yeni makale eklendi: {title[:50]}...")
            
            _cache = _get_cache()
            if _cache:
                await _cache.invalidate_pattern("stats:*")
                await _cache.invalidate_pattern("articles_search_*")
                await _cache.invalidate_pattern("es_search_*")
                await _cache.invalidate_pattern("search:*")
        else:
            logger.info(f"Makale güncellendi: {title[:50]}...")
        
        # ES indexing
        from backend.core.config import settings
        _es = _get_es()
        if _es and _es.is_connected and settings.elasticsearch_auto_sync:
            doc = article.model_dump()
            doc["id"] = str(article.id)
            if article.journal_id: doc["journal_id"] = str(article.journal_id)
            if article.issue_id: doc["issue_id"] = str(article.issue_id)
            await _es.index_article(doc)
        
        return article, created
    
    async def add_articles_bulk(
        self,
        issue: Issue,
        articles_data: List[Dict[str, Any]]
    ) -> tuple[int, int]:
        """
        Toplu makale ekle
        
        Args:
            issue: Bağlı olduğu sayı
            articles_data: Makale verilerinin listesi
        
        Returns:
            tuple: (created_count, updated_count)
        """
        created_count = 0
        updated_count = 0
        articles = []
        
        for data in articles_data:
            if not data.get('url') or not data.get('title'):
                continue
            
            # Issue bilgilerini ekle
            data['journal_id'] = issue.journal_id
            data['journal_name'] = issue.journal_name
            data['issue_id'] = issue.id
            data['issue_number'] = issue.issue_number
            data['source_website'] = issue.source_website
            
            article, created = await self.article_repo.upsert(**data)
            articles.append(article)
            
            if created:
                created_count += 1
            else:
                updated_count += 1
        
        # Sayıları güncelle
        if created_count > 0:
            await self.issue_repo.increment_article_count(issue.id, created_count)
            await self.journal_repo.increment_counts(issue.journal_id, article_increment=created_count)
            
            _cache = _get_cache()
            if _cache:
                await _cache.invalidate_pattern("stats:*")
                await _cache.invalidate_pattern("articles_search_*")
                await _cache.invalidate_pattern("es_search_*")
                await _cache.invalidate_pattern("search:*")
            
        from backend.core.config import settings
        _es = _get_es()
        if articles and _es and _es.is_connected and settings.elasticsearch_auto_sync:
            es_docs = []
            for a in articles:
                d = a.model_dump()
                d["id"] = str(a.id)
                if a.journal_id: d["journal_id"] = str(a.journal_id)
                if a.issue_id: d["issue_id"] = str(a.issue_id)
                es_docs.append(d)
            await _es.bulk_index(es_docs)
            
        logger.found(created_count, f"yeni makale eklendi, {updated_count} güncellendi")
        
        return created_count, updated_count
    
    async def get_articles_by_issue(
        self,
        issue_id: PydanticObjectId
    ) -> List[Article]:
        """Sayının tüm makalelerini getir"""
        return await self.article_repo.find_by_issue(issue_id)
    
    async def get_articles_by_journal(
        self,
        journal_id: PydanticObjectId
    ) -> List[Article]:
        """Derginin tüm makalelerini getir"""
        return await self.article_repo.find_by_journal(journal_id)
    
    async def search_articles(
        self,
        query: str,
        search_type: str = "text",
        limit: int = 100
    ) -> List[Article]:
        """
        Makale ara
        
        Args:
            query: Arama sorgusu
            search_type: text, title, keyword, author
            limit: Maksimum sonuç sayısı
        """
        if search_type == "text":
            return await self.article_repo.text_search(query, limit)
        elif search_type == "title":
            return await self.article_repo.search_by_title(query, limit)
        elif search_type == "keyword":
            return await self.article_repo.search_by_keyword(query, limit)
        elif search_type == "author":
            return await self.article_repo.search_by_author(query, limit)
        return []
    
    # ==================== Kombine İşlemler ====================
    
    async def add_journal_with_issue_and_articles(
        self,
        journal_data: Dict[str, Any],
        issue_data: Dict[str, Any],
        articles_data: List[Dict[str, Any]],
        source_website: str
    ) -> Dict[str, Any]:
        """
        Dergi, sayı ve makaleleri birlikte ekle
        
        Scraperlar için ana metod.
        
        Returns:
            dict: İstatistikler
        """
        # Dergi ekle
        journal, journal_created = await self.add_journal(
            source_website=source_website,
            **journal_data
        )
        
        # Sayı ekle
        issue, issue_created = await self.add_issue(
            journal=journal,
            **issue_data
        )
        
        # Makaleleri ekle
        created, updated = await self.add_articles_bulk(issue, articles_data)
        
        return {
            "journal": journal,
            "journal_created": journal_created,
            "issue": issue,
            "issue_created": issue_created,
            "articles_created": created,
            "articles_updated": updated
        }
    
    # ==================== İstatistikler ====================
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Genel istatistikleri getir"""
        db = get_database()
        
        journal_stats = await self.journal_repo.get_statistics_by_source()
        article_stats = await self.article_repo.get_statistics_by_source()
        db_stats = await db.get_statistics()
        
        return {
            "database": db_stats,
            "journals_by_source": journal_stats,
            "articles_by_source": article_stats
        }
    
    async def print_statistics(self):
        """İstatistikleri ekrana yazdır"""
        stats = await self.get_statistics()
        
        logger.header("DATABASE İSTATİSTİKLERİ")
        
        # Database stats
        db_stats = stats.get("database", {})
        logger.stats({
            "Journals": db_stats.get("journal_count", 0),
            "Issues": db_stats.get("issue_count", 0),
            "Articles": db_stats.get("article_count", 0),
            "Data Size": f"{db_stats.get('data_size_mb', 0)} MB"
        }, "Genel Bilgiler")
        
        # Source bazlı stats
        for source_stats in stats.get("journals_by_source", []):
            source = source_stats.get("_id", "Unknown")
            logger.subsection(f"{source.upper()}")
            logger.info(f"  Journals: {source_stats.get('total_journals', 0)}")
            logger.info(f"  Issues: {source_stats.get('total_issues', 0)}")
            logger.info(f"  Articles: {source_stats.get('total_articles', 0)}")
    
    async def get_top_keywords(
        self,
        limit: int = 20,
        source_website: Optional[str] = None
    ) -> List[Dict]:
        """En çok kullanılan anahtar kelimeleri getir"""
        return await self.article_repo.get_top_keywords(limit, source_website)
    
    async def get_top_authors(
        self,
        limit: int = 20,
        source_website: Optional[str] = None
    ) -> List[Dict]:
        """En çok makale yazan yazarları getir"""
        return await self.article_repo.get_top_authors(limit, source_website)


# Singleton instance
_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Database service singleton'ı getir"""
    global _service
    if _service is None:
        _service = DatabaseService()
    return _service


async def init_database_service() -> DatabaseService:
    """Database service'i initialize et ve döndür"""
    service = get_database_service()
    await service.initialize()
    return service
