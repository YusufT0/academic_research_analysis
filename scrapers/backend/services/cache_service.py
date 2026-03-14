"""
Cache Service
Redis tabanlı akıllı cache yönetimi
"""

import json
import hashlib
import asyncio
from datetime import datetime
from typing import Optional, Any, List, Dict, Callable, TypeVar, Union
from functools import wraps

import redis.asyncio as redis
from pydantic import BaseModel
from beanie import PydanticObjectId

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.logger import get_logger

logger = get_logger('cache_service')

T = TypeVar('T')


def _get_settings():
    """Lazy import to avoid circular dependency"""
    from backend.core.config import settings
    return settings


class CacheStats(BaseModel):
    """Cache istatistikleri"""
    hits: int = 0
    misses: int = 0
    prefetches: int = 0
    invalidations: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0


class CacheService:
    """
    Redis Cache Service
    
    Akıllı cache yönetimi:
    - Otomatik prefetch
    - İlişkisel veri cache'leme
    - TTL stratejileri
    - Write-through invalidation
    """
    
    _instance: Optional["CacheService"] = None
    _client: Optional[redis.Redis] = None
    _connected: bool = False
    _stats: CacheStats = CacheStats()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        settings = _get_settings()
        self.prefix = settings.redis_prefix
        self.enabled = settings.redis_enabled
        self._background_tasks: List[asyncio.Task] = []
    
    async def connect(self) -> bool:
        """Redis'e bağlan"""
        settings = _get_settings()
        if not self.enabled:
            logger.info("Redis cache devre dışı")
            return False
        
        if self._connected and self._client:
            return True
        
        try:
            self._client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            
            # Bağlantı testi
            await self._client.ping()
            self._connected = True
            logger.success(f"Redis bağlantısı kuruldu: {settings.redis_url}")
            return True
            
        except Exception as e:
            logger.error(f"Redis bağlantı hatası: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Redis bağlantısını kapat"""
        if self._client:
            # Background task'ları bekle
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
            
            await self._client.close()
            self._connected = False
            logger.info("Redis bağlantısı kapatıldı")
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None
    
    def _make_key(self, *parts: str) -> str:
        """Cache key oluştur"""
        return f"{self.prefix}:{':'.join(str(p) for p in parts)}"
    
    def _hash_query(self, query: Dict[str, Any]) -> str:
        """Query dict'ini hash'le"""
        sorted_query = json.dumps(query, sort_keys=True, default=str)
        return hashlib.md5(sorted_query.encode()).hexdigest()[:12]
    
    def _serialize(self, value: Any) -> str:
        """Değeri JSON'a serialize et"""
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        elif isinstance(value, (list, dict)):
            return json.dumps(value, default=str)
        elif isinstance(value, PydanticObjectId):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        return json.dumps(value, default=str)
    
    def _deserialize(self, value: str) -> Any:
        """JSON'dan deserialize et"""
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    # ==================== Core Cache Operations ====================
    
    async def get(self, key: str) -> Optional[Any]:
        """Cache'den değer al"""
        if not self.is_connected:
            return None
        
        try:
            value = await self._client.get(key)
            if value:
                self._stats.hits += 1
                return self._deserialize(value)
            self._stats.misses += 1
            return None
        except Exception as e:
            logger.error(f"Cache get error [{key}]: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """Cache'e değer yaz"""
        if not self.is_connected:
            return False
        
        try:
            serialized = self._serialize(value)
            if ttl:
                await self._client.setex(key, ttl, serialized)
            else:
                await self._client.set(key, serialized)
            return True
        except Exception as e:
            logger.error(f"Cache set error [{key}]: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Cache'den sil"""
        if not self.is_connected:
            return False
        
        try:
            await self._client.delete(key)
            self._stats.invalidations += 1
            return True
        except Exception as e:
            logger.error(f"Cache delete error [{key}]: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Pattern'e uyan tüm key'leri sil"""
        if not self.is_connected:
            return 0
        
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                deleted = await self._client.delete(*keys)
                self._stats.invalidations += deleted
                return deleted
            return 0
        except Exception as e:
            logger.error(f"Cache delete_pattern error [{pattern}]: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Key var mı kontrol et"""
        if not self.is_connected:
            return False
        
        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            return False
    
    async def mget(self, keys: List[str]) -> List[Optional[Any]]:
        """Birden fazla key'i al"""
        if not self.is_connected:
            return [None] * len(keys)
        
        try:
            values = await self._client.mget(keys)
            results = []
            for v in values:
                if v:
                    self._stats.hits += 1
                    results.append(self._deserialize(v))
                else:
                    self._stats.misses += 1
                    results.append(None)
            return results
        except Exception as e:
            logger.error(f"Cache mget error: {e}")
            return [None] * len(keys)
    
    async def mset(
        self, 
        mapping: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """Birden fazla key-value yaz"""
        if not self.is_connected or not mapping:
            return False
        
        try:
            serialized = {k: self._serialize(v) for k, v in mapping.items()}
            
            if ttl:
                # TTL ile pipeline kullan
                async with self._client.pipeline() as pipe:
                    for key, value in serialized.items():
                        pipe.setex(key, ttl, value)
                    await pipe.execute()
            else:
                await self._client.mset(serialized)
            return True
        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            return False
    
    # ==================== Entity-Specific Cache ====================
    
    async def get_article(self, article_id: str) -> Optional[Dict]:
        """Makale cache'den al"""
        key = self._make_key("article", article_id)
        return await self.get(key)
    
    async def set_article(self, article_id: str, data: Dict) -> bool:
        """Makale cache'e yaz"""
        key = self._make_key("article", article_id)
        return await self.set(key, data, _get_settings().cache_ttl_article)
    
    async def get_article_by_doi(self, doi: str) -> Optional[Dict]:
        """DOI ile makale cache'den al"""
        key = self._make_key("article", "doi", doi.replace("/", "_"))
        return await self.get(key)
    
    async def set_article_by_doi(self, doi: str, data: Dict) -> bool:
        """DOI ile makale cache'e yaz"""
        key = self._make_key("article", "doi", doi.replace("/", "_"))
        return await self.set(key, data, _get_settings().cache_ttl_article)
    
    async def get_journal(self, journal_id: str) -> Optional[Dict]:
        """Journal cache'den al"""
        key = self._make_key("journal", journal_id)
        return await self.get(key)
    
    async def set_journal(self, journal_id: str, data: Dict) -> bool:
        """Journal cache'e yaz"""
        key = self._make_key("journal", journal_id)
        return await self.set(key, data, _get_settings().cache_ttl_journal)
    
    async def get_issue(self, issue_id: str) -> Optional[Dict]:
        """Issue cache'den al"""
        key = self._make_key("issue", issue_id)
        return await self.get(key)
    
    async def set_issue(self, issue_id: str, data: Dict) -> bool:
        """Issue cache'e yaz"""
        key = self._make_key("issue", issue_id)
        return await self.set(key, data, _get_settings().cache_ttl_issue)
    
    async def get_cluster(self, cluster_id: int, model_version: str) -> Optional[Dict]:
        """Cluster cache'den al"""
        key = self._make_key("cluster", model_version, str(cluster_id))
        return await self.get(key)
    
    async def set_cluster(self, cluster_id: int, model_version: str, data: Dict) -> bool:
        """Cluster cache'e yaz"""
        key = self._make_key("cluster", model_version, str(cluster_id))
        return await self.set(key, data, _get_settings().cache_ttl_cluster)
    
    async def get_search_results(self, query: str, params: Dict) -> Optional[Dict]:
        """Search sonuçları cache'den al"""
        query_hash = self._hash_query({"query": query, **params})
        key = self._make_key("search", query_hash)
        return await self.get(key)
    
    async def set_search_results(self, query: str, params: Dict, data: Dict) -> bool:
        """Search sonuçları cache'e yaz"""
        query_hash = self._hash_query({"query": query, **params})
        key = self._make_key("search", query_hash)
        return await self.set(key, data, _get_settings().cache_ttl_search)
    
    async def get_stats(self) -> Optional[Dict]:
        """İstatistikler cache'den al"""
        key = self._make_key("stats", "global")
        return await self.get(key)
    
    async def set_stats(self, data: Dict) -> bool:
        """İstatistikler cache'e yaz"""
        key = self._make_key("stats", "global")
        return await self.set(key, data, _get_settings().cache_ttl_stats)
    
    # ==================== List Cache ====================
    
    async def get_issue_articles(self, issue_id: str) -> Optional[List[Dict]]:
        """Issue makaleleri cache'den al"""
        key = self._make_key("issue", issue_id, "articles")
        return await self.get(key)
    
    async def set_issue_articles(self, issue_id: str, articles: List[Dict]) -> bool:
        """Issue makaleleri cache'e yaz"""
        key = self._make_key("issue", issue_id, "articles")
        return await self.set(key, articles, _get_settings().cache_ttl_article)
    
    async def get_journal_issues(self, journal_id: str) -> Optional[List[Dict]]:
        """Journal issue'ları cache'den al"""
        key = self._make_key("journal", journal_id, "issues")
        return await self.get(key)
    
    async def set_journal_issues(self, journal_id: str, issues: List[Dict]) -> bool:
        """Journal issue'ları cache'e yaz"""
        key = self._make_key("journal", journal_id, "issues")
        return await self.set(key, issues, _get_settings().cache_ttl_issue)
    
    async def get_cluster_articles(self, cluster_id: int, model_version: str) -> Optional[List[Dict]]:
        """Cluster makaleleri cache'den al"""
        key = self._make_key("cluster", model_version, str(cluster_id), "articles")
        return await self.get(key)
    
    async def set_cluster_articles(
        self, 
        cluster_id: int, 
        model_version: str, 
        articles: List[Dict]
    ) -> bool:
        """Cluster makaleleri cache'e yaz"""
        key = self._make_key("cluster", model_version, str(cluster_id), "articles")
        return await self.set(key, articles, _get_settings().cache_ttl_cluster)
    
    # ==================== Invalidation ====================
    
    async def invalidate_article(self, article_id: str, doi: Optional[str] = None):
        """Makale cache'ini invalidate et"""
        await self.delete(self._make_key("article", article_id))
        if doi:
            await self.delete(self._make_key("article", "doi", doi.replace("/", "_")))
        # İlişkili cache'leri de temizle
        await self.delete_pattern(f"{self.prefix}:*:articles*")
    
    async def invalidate_journal(self, journal_id: str):
        """Journal cache'ini invalidate et"""
        await self.delete(self._make_key("journal", journal_id))
        await self.delete(self._make_key("journal", journal_id, "issues"))
    
    async def invalidate_issue(self, issue_id: str):
        """Issue cache'ini invalidate et"""
        await self.delete(self._make_key("issue", issue_id))
        await self.delete(self._make_key("issue", issue_id, "articles"))
    
    async def invalidate_cluster(self, cluster_id: int, model_version: str):
        """Cluster cache'ini invalidate et"""
        await self.delete(self._make_key("cluster", model_version, str(cluster_id)))
        await self.delete(self._make_key("cluster", model_version, str(cluster_id), "articles"))
    
    async def invalidate_all_clusters(self, model_version: Optional[str] = None):
        """Tüm cluster cache'lerini temizle"""
        if model_version:
            await self.delete_pattern(f"{self.prefix}:cluster:{model_version}:*")
        else:
            await self.delete_pattern(f"{self.prefix}:cluster:*")
            
    async def invalidate_pattern(self, pattern: str) -> int:
        """Prefix ekleyerek pattern'e uyan tüm key'leri sil"""
        full_pattern = f"{self.prefix}:{pattern}"
        return await self.delete_pattern(full_pattern)
    
    async def invalidate_search_cache(self):
        """Tüm search cache'lerini temizle"""
        await self.delete_pattern(f"{self.prefix}:search:*")
    
    async def invalidate_stats(self):
        """Stats cache'ini temizle"""
        await self.delete(self._make_key("stats", "global"))
    
    async def flush_all(self):
        """Tüm cache'i temizle (dikkatli kullan!)"""
        if not self.is_connected:
            return
        await self.delete_pattern(f"{self.prefix}:*")
        logger.warning("Tüm cache temizlendi!")
    
    # ==================== Prefetch (Akıllı Önbellek) ====================
    
    def _schedule_prefetch(self, coro):
        """Background prefetch task'ı planla"""
        if not _get_settings().prefetch_enabled:
            logger.debug("Prefetch disabled, skipping")
            return
        
        def done_callback(task):
            try:
                exc = task.exception()
                if exc:
                    logger.error(f"Prefetch task failed: {exc}")
                else:
                    self._stats.prefetches += 1
            except asyncio.CancelledError:
                pass
        
        task = asyncio.create_task(coro)
        task.add_done_callback(done_callback)
        self._background_tasks.append(task)
        logger.info(f"Prefetch task scheduled (active tasks: {len(self._background_tasks)})")
        
        # Tamamlanan task'ları temizle
        self._background_tasks = [t for t in self._background_tasks if not t.done()]
    
    async def prefetch_issue_articles(
        self, 
        issue_id: str, 
        fetch_func: Callable[[], Any]
    ):
        """
        Issue görüntülendiğinde makalelerini prefetch et
        """
        key = self._make_key("issue", issue_id, "articles")
        
        if await self.exists(key):
            return  # Zaten cache'de
        
        try:
            articles = await fetch_func()
            if articles:
                await self.set_issue_articles(issue_id, articles)
                self._stats.prefetches += 1
                logger.debug(f"Prefetched {len(articles)} articles for issue {issue_id}")
        except Exception as e:
            logger.error(f"Prefetch error (issue articles): {e}")
    
    async def prefetch_journal_issues(
        self, 
        journal_id: str, 
        fetch_func: Callable[[], Any]
    ):
        """
        Journal görüntülendiğinde issue'larını prefetch et
        """
        key = self._make_key("journal", journal_id, "issues")
        
        if await self.exists(key):
            return
        
        try:
            issues = await fetch_func()
            if issues:
                await self.set_journal_issues(journal_id, issues)
                self._stats.prefetches += 1
                logger.debug(f"Prefetched {len(issues)} issues for journal {journal_id}")
        except Exception as e:
            logger.error(f"Prefetch error (journal issues): {e}")
    
    async def prefetch_related_articles(
        self,
        article_ids: List[str],
        fetch_func: Callable[[List[str]], Any]
    ):
        """
        İlişkili makaleleri prefetch et (cluster bazlı)
        """
        # Hangileri cache'de yok?
        keys = [self._make_key("article", aid) for aid in article_ids]
        cached = await self.mget(keys)
        
        missing_ids = [
            article_ids[i] for i, c in enumerate(cached) if c is None
        ]
        
        if not missing_ids:
            return
        
        try:
            articles = await fetch_func(missing_ids)
            if articles:
                mapping = {
                    self._make_key("article", str(a.get("id", a.get("_id")))): a
                    for a in articles
                }
                await self.mset(mapping, _get_settings().cache_ttl_article)
                self._stats.prefetches += len(articles)
                logger.debug(f"Prefetched {len(articles)} related articles")
        except Exception as e:
            logger.error(f"Prefetch error (related articles): {e}")
    
    async def prefetch_cluster_context(
        self,
        cluster_id: int,
        model_version: str,
        fetch_cluster_func: Callable,
        fetch_articles_func: Callable
    ):
        """
        Cluster aramasında ilgili context'i prefetch et
        """
        # Cluster bilgisi
        cluster_key = self._make_key("cluster", model_version, str(cluster_id))
        if not await self.exists(cluster_key):
            try:
                cluster = await fetch_cluster_func()
                if cluster:
                    await self.set_cluster(cluster_id, model_version, cluster)
                    self._stats.prefetches += 1
            except Exception as e:
                logger.error(f"Prefetch error (cluster): {e}")
        
        # Cluster makaleleri
        articles_key = self._make_key("cluster", model_version, str(cluster_id), "articles")
        if not await self.exists(articles_key):
            try:
                articles = await fetch_articles_func()
                if articles:
                    await self.set_cluster_articles(cluster_id, model_version, articles)
                    self._stats.prefetches += len(articles)
            except Exception as e:
                logger.error(f"Prefetch error (cluster articles): {e}")
    
    # ==================== Stats & Monitoring ====================
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Cache istatistiklerini döndür"""
        info = {}
        
        if self.is_connected:
            try:
                redis_info = await self._client.info("memory")
                redis_keys = await self._client.dbsize()
                info["redis_memory_used"] = redis_info.get("used_memory_human", "N/A")
                info["redis_memory_peak"] = redis_info.get("used_memory_peak_human", "N/A")
                info["total_keys"] = redis_keys
            except Exception:
                pass
        
        return {
            "enabled": self.enabled,
            "connected": self.is_connected,
            "stats": {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "hit_rate": f"{self._stats.hit_rate:.2f}%",
                "prefetches": self._stats.prefetches,
                "invalidations": self._stats.invalidations
            },
            **info
        }
    
    def reset_stats(self):
        """İstatistikleri sıfırla"""
        self._stats = CacheStats()


# Lazy singleton instance
_cache_service: Optional[CacheService] = None

def get_cache_service() -> CacheService:
    """Cache service singleton'ı lazy olarak döndür"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service

# Backward compatibility için property-like erişim
class _CacheServiceProxy:
    """Cache service'e proxy erişim - lazy initialization"""
    
    def __getattr__(self, name):
        return getattr(get_cache_service(), name)
    
    def __bool__(self):
        return True

cache_service = _CacheServiceProxy()
