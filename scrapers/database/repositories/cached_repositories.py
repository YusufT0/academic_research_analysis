"""
Cached Repository Wrappers
Repository metodları için cache katmanı
"""

from typing import Optional, List, Dict, Any
from beanie import PydanticObjectId

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.repositories import ArticleRepository, JournalRepository, IssueRepository
from database.models import Article, Journal, Issue
from utils.logger import get_logger

logger = get_logger('cached_repo')


# Lazy imports to avoid circular dependency
def _get_cache_service():
    from backend.services.cache_service import cache_service
    return cache_service

def _get_settings():
    from backend.core.config import settings
    return settings


class CachedArticleRepository:
    """
    Article Repository with caching layer
    
    Cache-aside pattern ile çalışır:
    1. Önce cache'e bak
    2. Yoksa DB'den al
    3. DB'den aldığını cache'le
    """
    
    def __init__(self):
        self._repo = ArticleRepository()
    
    async def get_by_id(self, article_id: PydanticObjectId) -> Optional[Article]:
        """ID ile makale getir (cached)"""
        cache_key = _get_cache_service()._make_key("article", str(article_id))
        
        # Cache'den dene
        cached = await _get_cache_service().get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: article {article_id}")
            return Article(**cached) if isinstance(cached, dict) else cached
        
        # DB'den al
        article = await self._repo.get_by_id(article_id)
        
        # Cache'le
        if article:
            await _get_cache_service().set(
                cache_key, 
                article.model_dump(mode='json'),
                _get_settings().cache_ttl_article
            )
            
            # Prefetch: Aynı issue'daki makaleleri background'da cache'le
            if _get_settings().prefetch_enabled and article.issue_id:
                _get_cache_service()._schedule_prefetch(
                    self._prefetch_issue_articles(str(article.issue_id))
                )
        
        return article
    
    async def find_by_doi(self, doi: str) -> Optional[Article]:
        """DOI ile makale bul (cached)"""
        safe_doi = doi.replace("/", "_")
        cache_key = _get_cache_service()._make_key("article", "doi", safe_doi)
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return Article(**cached) if isinstance(cached, dict) else cached
        
        article = await self._repo.find_by_doi(doi)
        
        if article:
            await _get_cache_service().set(
                cache_key,
                article.model_dump(mode='json'),
                _get_settings().cache_ttl_article
            )
            # Ana ID cache'ini de güncelle
            await _get_cache_service().set_article(
                str(article.id),
                article.model_dump(mode='json')
            )
        
        return article
    
    async def find_by_issue(
        self, 
        issue_id: PydanticObjectId,
        use_cache: bool = True
    ) -> List[Article]:
        """Issue'daki makaleleri getir (cached)"""
        if use_cache:
            cached = await _get_cache_service().get_issue_articles(str(issue_id))
            if cached:
                logger.debug(f"Cache HIT: issue {issue_id} articles")
                return [Article(**a) if isinstance(a, dict) else a for a in cached]
        
        articles = await self._repo.find_by_issue(issue_id)
        
        if articles:
            await _get_cache_service().set_issue_articles(
                str(issue_id),
                [a.model_dump(mode='json') for a in articles]
            )
        
        return articles
    
    async def find_by_journal(
        self, 
        journal_id: PydanticObjectId,
        limit: int = 100
    ) -> List[Article]:
        """Journal'daki makaleleri getir"""
        # Journal makaleleri çok fazla olabilir, limitli cache
        cache_key = _get_cache_service()._make_key("journal", str(journal_id), "articles", str(limit))
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return [Article(**a) if isinstance(a, dict) else a for a in cached]
        
        articles = await self._repo.find_by_journal(journal_id)
        articles = articles[:limit]
        
        if articles:
            await _get_cache_service().set(
                cache_key,
                [a.model_dump(mode='json') for a in articles],
                _get_settings().cache_ttl_article
            )
        
        return articles
    
    async def search_by_keyword(self, keyword: str, limit: int = 100) -> List[Article]:
        """Keyword ile ara (kısa TTL cache)"""
        cache_key = _get_cache_service()._make_key("search", "keyword", keyword, str(limit))
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return [Article(**a) if isinstance(a, dict) else a for a in cached]
        
        articles = await self._repo.search_by_keyword(keyword, limit)
        
        if articles:
            await _get_cache_service().set(
                cache_key,
                [a.model_dump(mode='json') for a in articles],
                _get_settings().cache_ttl_search  # Kısa TTL
            )
        
        return articles
    
    async def search_by_title(self, search_term: str, limit: int = 100) -> List[Article]:
        """Title'da ara (kısa TTL cache)"""
        cache_key = _get_cache_service()._make_key("search", "title", search_term[:50], str(limit))
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return [Article(**a) if isinstance(a, dict) else a for a in cached]
        
        articles = await self._repo.search_by_title(search_term, limit)
        
        if articles:
            await _get_cache_service().set(
                cache_key,
                [a.model_dump(mode='json') for a in articles],
                _get_settings().cache_ttl_search
            )
        
        return articles
    
    async def get_statistics_by_source(self) -> List[dict]:
        """İstatistikler (cached)"""
        cache_key = _get_cache_service()._make_key("stats", "articles", "by_source")
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return cached
        
        stats = await self._repo.get_statistics_by_source()
        
        await _get_cache_service().set(cache_key, stats, _get_settings().cache_ttl_stats)
        
        return stats
    
    async def _prefetch_issue_articles(self, issue_id: str):
        """Background prefetch for issue articles"""
        try:
            cache_key = _get_cache_service()._make_key("issue", issue_id, "articles")
            if await _get_cache_service().exists(cache_key):
                return
            
            articles = await self._repo.find_by_issue(PydanticObjectId(issue_id))
            articles = articles[:_get_settings().prefetch_articles_per_issue]
            
            if articles:
                await _get_cache_service().set_issue_articles(
                    issue_id,
                    [a.model_dump(mode='json') for a in articles]
                )
                logger.debug(f"Prefetched {len(articles)} articles for issue {issue_id}")
        except Exception as e:
            logger.error(f"Prefetch error: {e}")
    
    # Delegate non-cached methods
    async def count(self) -> int:
        return await self._repo.count()
    
    async def find_or_create(self, *args, **kwargs):
        result = await self._repo.find_or_create(*args, **kwargs)
        # Yeni makale oluşturulduysa stats cache'ini invalidate et
        if result[1]:  # created = True
            await _get_cache_service().invalidate_stats()
        return result
    
    async def get_all(self, limit: int = 100, skip: int = 0):
        return await self._repo.get_all(limit, skip)


class CachedJournalRepository:
    """Journal Repository with caching"""
    
    def __init__(self):
        self._repo = JournalRepository()
    
    async def get_by_id(self, journal_id: PydanticObjectId) -> Optional[Journal]:
        """ID ile journal getir (cached)"""
        cache_key = _get_cache_service()._make_key("journal", str(journal_id))
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return Journal(**cached) if isinstance(cached, dict) else cached
        
        journal = await self._repo.get_by_id(journal_id)
        
        if journal:
            await _get_cache_service().set(
                cache_key,
                journal.model_dump(mode='json'),
                _get_settings().cache_ttl_journal
            )
            
            # Prefetch: Journal'ın issue'larını background'da cache'le
            if _get_settings().prefetch_enabled:
                _get_cache_service()._schedule_prefetch(
                    self._prefetch_journal_issues(str(journal_id))
                )
        
        return journal
    
    async def find_by_name(self, name: str, source_website: str) -> Optional[Journal]:
        """İsim ve kaynak ile bul"""
        cache_key = _get_cache_service()._make_key("journal", "name", name[:50], source_website)
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return Journal(**cached) if isinstance(cached, dict) else cached
        
        journal = await self._repo.find_by_name(name, source_website)
        
        if journal:
            await _get_cache_service().set(
                cache_key,
                journal.model_dump(mode='json'),
                _get_settings().cache_ttl_journal
            )
        
        return journal
    
    async def find_by_source(self, source_website: str) -> List[Journal]:
        """Kaynak siteye göre bul (cached)"""
        cache_key = _get_cache_service()._make_key("journal", "source", source_website)
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return [Journal(**j) if isinstance(j, dict) else j for j in cached]
        
        journals = await self._repo.find_by_source(source_website)
        
        if journals:
            await _get_cache_service().set(
                cache_key,
                [j.model_dump(mode='json') for j in journals],
                _get_settings().cache_ttl_journal
            )
        
        return journals
    
    async def get_statistics_by_source(self) -> List[dict]:
        """İstatistikler (cached)"""
        cache_key = _get_cache_service()._make_key("stats", "journals", "by_source")
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return cached
        
        stats = await self._repo.get_statistics_by_source()
        await _get_cache_service().set(cache_key, stats, _get_settings().cache_ttl_stats)
        
        return stats
    
    async def _prefetch_journal_issues(self, journal_id: str):
        """Background prefetch for journal issues"""
        try:
            cache_key = _get_cache_service()._make_key("journal", journal_id, "issues")
            if await _get_cache_service().exists(cache_key):
                return
            
            from database.repositories import IssueRepository
            issue_repo = IssueRepository()
            issues = await issue_repo.find_by_journal(PydanticObjectId(journal_id))
            issues = issues[:_get_settings().prefetch_issues_per_journal]
            
            if issues:
                await _get_cache_service().set_journal_issues(
                    journal_id,
                    [i.model_dump(mode='json') for i in issues]
                )
                logger.debug(f"Prefetched {len(issues)} issues for journal {journal_id}")
        except Exception as e:
            logger.error(f"Prefetch error: {e}")
    
    # Delegate non-cached methods
    async def count(self) -> int:
        return await self._repo.count()
    
    async def find_or_create(self, *args, **kwargs):
        result = await self._repo.find_or_create(*args, **kwargs)
        if result[1]:
            await _get_cache_service().invalidate_stats()
        return result
    
    async def get_all(self, limit: int = 100, skip: int = 0):
        return await self._repo.get_all(limit, skip)
    
    async def search_by_name(self, search_term: str, limit: int = 50):
        return await self._repo.search_by_name(search_term, limit)


class CachedIssueRepository:
    """Issue Repository with caching"""
    
    def __init__(self):
        self._repo = IssueRepository()
    
    async def get_by_id(self, issue_id: PydanticObjectId) -> Optional[Issue]:
        """ID ile issue getir (cached)"""
        cache_key = _get_cache_service()._make_key("issue", str(issue_id))
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return Issue(**cached) if isinstance(cached, dict) else cached
        
        issue = await self._repo.get_by_id(issue_id)
        
        if issue:
            await _get_cache_service().set(
                cache_key,
                issue.model_dump(mode='json'),
                _get_settings().cache_ttl_issue
            )
            
            # Prefetch: Issue'nun makalelerini background'da cache'le
            if _get_settings().prefetch_enabled:
                _get_cache_service()._schedule_prefetch(
                    self._prefetch_issue_articles(str(issue_id))
                )
        
        return issue
    
    async def find_by_journal(self, journal_id: PydanticObjectId) -> List[Issue]:
        """Journal'ın issue'larını getir (cached)"""
        cached = await _get_cache_service().get_journal_issues(str(journal_id))
        if cached:
            return [Issue(**i) if isinstance(i, dict) else i for i in cached]
        
        issues = await self._repo.find_by_journal(journal_id)
        
        if issues:
            await _get_cache_service().set_journal_issues(
                str(journal_id),
                [i.model_dump(mode='json') for i in issues]
            )
        
        return issues
    
    async def find_latest_by_journal(self, journal_id: PydanticObjectId) -> Optional[Issue]:
        """En son issue (cached)"""
        cache_key = _get_cache_service()._make_key("issue", "latest", str(journal_id))
        
        cached = await _get_cache_service().get(cache_key)
        if cached:
            return Issue(**cached) if isinstance(cached, dict) else cached
        
        issue = await self._repo.find_latest_by_journal(journal_id)
        
        if issue:
            await _get_cache_service().set(
                cache_key,
                issue.model_dump(mode='json'),
                _get_settings().cache_ttl_issue
            )
        
        return issue
    
    async def _prefetch_issue_articles(self, issue_id: str):
        """Background prefetch for issue articles"""
        try:
            cache_key = _get_cache_service()._make_key("issue", issue_id, "articles")
            if await _get_cache_service().exists(cache_key):
                return
            
            article_repo = ArticleRepository()
            articles = await article_repo.find_by_issue(PydanticObjectId(issue_id))
            articles = articles[:_get_settings().prefetch_articles_per_issue]
            
            if articles:
                await _get_cache_service().set_issue_articles(
                    issue_id,
                    [a.model_dump(mode='json') for a in articles]
                )
                logger.debug(f"Prefetched {len(articles)} articles for issue {issue_id}")
        except Exception as e:
            logger.error(f"Prefetch error: {e}")
    
    # Delegate non-cached methods
    async def count(self) -> int:
        return await self._repo.count()
    
    async def find_or_create(self, *args, **kwargs):
        result = await self._repo.find_or_create(*args, **kwargs)
        if result[1]:
            await _get_cache_service().invalidate_stats()
        return result
    
    async def get_all(self, limit: int = 100, skip: int = 0):
        return await self._repo.get_all(limit, skip)
    
    async def get_count_by_journal(self, journal_id: PydanticObjectId) -> int:
        return await self._repo.get_count_by_journal(journal_id)
