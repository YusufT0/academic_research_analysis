"""
Cache Decorators
Repository ve endpoint metodları için cache dekoratörleri
"""

import asyncio
from functools import wraps
from typing import Optional, Callable, Any, List, TypeVar, Union
from beanie import PydanticObjectId

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.cache_service import cache_service
from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger('cache')

T = TypeVar('T')


def cached(
    key_prefix: str,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable[..., str]] = None
):
    """
    Cache decorator - Metod sonucunu cache'le
    
    Args:
        key_prefix: Cache key prefix'i (örn: "article", "journal")
        ttl: Cache TTL (saniye), None ise prefix'e göre otomatik
        key_builder: Özel key oluşturucu fonksiyon
    
    Usage:
        @cached("article", ttl=3600)
        async def get_by_id(self, id: str) -> Article:
            ...
        
        @cached("article", key_builder=lambda doi: f"doi:{doi}")
        async def find_by_doi(self, doi: str) -> Article:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Cache kapalıysa direkt çalıştır
            if not settings.redis_enabled or not cache_service.is_connected:
                return await func(*args, **kwargs)
            
            # Cache key oluştur
            if key_builder:
                # İlk arg self olabilir, onu atla
                func_args = args[1:] if args and hasattr(args[0], '__class__') else args
                key_suffix = key_builder(*func_args, **kwargs)
            else:
                # Varsayılan: tüm argümanları key'e ekle
                func_args = args[1:] if args and hasattr(args[0], '__class__') else args
                parts = [str(a) for a in func_args]
                parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key_suffix = ":".join(parts) if parts else "default"
            
            cache_key = cache_service._make_key(key_prefix, key_suffix)
            
            # Cache'den oku
            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Cache'de yok, fonksiyonu çalıştır
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Sonucu cache'le
            if result is not None:
                # TTL belirle
                actual_ttl = ttl
                if actual_ttl is None:
                    ttl_map = {
                        "article": settings.cache_ttl_article,
                        "journal": settings.cache_ttl_journal,
                        "issue": settings.cache_ttl_issue,
                        "cluster": settings.cache_ttl_cluster,
                        "search": settings.cache_ttl_search,
                        "stats": settings.cache_ttl_stats,
                    }
                    actual_ttl = ttl_map.get(key_prefix, 3600)
                
                # Beanie Document ise dict'e çevir
                if hasattr(result, 'model_dump'):
                    cache_data = result.model_dump(mode='json')
                elif hasattr(result, 'dict'):
                    cache_data = result.dict()
                else:
                    cache_data = result
                
                await cache_service.set(cache_key, cache_data, actual_ttl)
            
            return result
        
        return wrapper
    return decorator


def cached_list(
    key_prefix: str,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable[..., str]] = None
):
    """
    Liste sonuçları için cache decorator
    
    Beanie Document listelerini otomatik serialize eder
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> List[Any]:
            if not settings.redis_enabled or not cache_service.is_connected:
                return await func(*args, **kwargs)
            
            # Cache key oluştur
            if key_builder:
                func_args = args[1:] if args and hasattr(args[0], '__class__') else args
                key_suffix = key_builder(*func_args, **kwargs)
            else:
                func_args = args[1:] if args and hasattr(args[0], '__class__') else args
                parts = [str(a) for a in func_args]
                parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key_suffix = ":".join(parts) if parts else "all"
            
            cache_key = cache_service._make_key(key_prefix, "list", key_suffix)
            
            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT (list): {cache_key}")
                return cached_value
            
            logger.debug(f"Cache MISS (list): {cache_key}")
            result = await func(*args, **kwargs)
            
            if result:
                # Liste içindeki Beanie Document'ları serialize et
                cache_data = []
                for item in result:
                    if hasattr(item, 'model_dump'):
                        cache_data.append(item.model_dump(mode='json'))
                    elif hasattr(item, 'dict'):
                        cache_data.append(item.dict())
                    else:
                        cache_data.append(item)
                
                actual_ttl = ttl or settings.cache_ttl_article
                await cache_service.set(cache_key, cache_data, actual_ttl)
            
            return result
        
        return wrapper
    return decorator


def cache_invalidate(
    key_prefix: str,
    key_builder: Optional[Callable[..., str]] = None,
    invalidate_patterns: Optional[List[str]] = None
):
    """
    Cache invalidation decorator
    
    Write operasyonlarında ilgili cache'leri temizler
    
    Args:
        key_prefix: Silinecek key prefix'i
        key_builder: Silinecek key'i oluşturan fonksiyon
        invalidate_patterns: Ek pattern'ler (glob style)
    
    Usage:
        @cache_invalidate("article", invalidate_patterns=["article:list:*"])
        async def update(self, article: Article):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            result = await func(*args, **kwargs)
            
            if not settings.redis_enabled or not cache_service.is_connected:
                return result
            
            try:
                # Ana key'i sil
                if key_builder:
                    func_args = args[1:] if args and hasattr(args[0], '__class__') else args
                    key_suffix = key_builder(*func_args, **kwargs)
                    cache_key = cache_service._make_key(key_prefix, key_suffix)
                    await cache_service.delete(cache_key)
                
                # Pattern'leri temizle
                if invalidate_patterns:
                    for pattern in invalidate_patterns:
                        full_pattern = f"{cache_service.prefix}:{pattern}"
                        await cache_service.delete_pattern(full_pattern)
                
                # Stats'ı da invalidate et (veri değişti)
                await cache_service.invalidate_stats()
                
                logger.debug(f"Cache invalidated: {key_prefix}")
                
            except Exception as e:
                logger.error(f"Cache invalidation error: {e}")
            
            return result
        
        return wrapper
    return decorator


def prefetch_related(
    relation_type: str,
    id_extractor: Callable[..., Optional[str]] = None
):
    """
    İlişkili verileri background'da prefetch et
    
    Args:
        relation_type: "issue_articles", "journal_issues", "cluster_articles"
        id_extractor: Sonuçtan ID çıkaran fonksiyon
    
    Usage:
        @prefetch_related("issue_articles", lambda result: str(result.issue_id))
        async def get_by_id(self, id: str) -> Article:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            result = await func(*args, **kwargs)
            
            if not settings.prefetch_enabled or not result:
                return result
            
            if not cache_service.is_connected:
                return result
            
            try:
                # ID'yi çıkar
                related_id = None
                if id_extractor:
                    related_id = id_extractor(result)
                
                if not related_id:
                    return result
                
                # İlişki tipine göre prefetch planla
                if relation_type == "issue_articles":
                    # self'i bul (repository instance)
                    repo = args[0] if args else None
                    if repo and hasattr(repo, 'find_by_issue'):
                        async def fetch():
                            articles = await repo.find_by_issue(PydanticObjectId(related_id))
                            return [a.model_dump(mode='json') for a in articles[:settings.prefetch_articles_per_issue]]
                        
                        cache_service._schedule_prefetch(
                            cache_service.prefetch_issue_articles(related_id, fetch)
                        )
                
                elif relation_type == "journal_issues":
                    repo = args[0] if args else None
                    if repo and hasattr(repo, 'find_by_journal'):
                        async def fetch():
                            # Issue repository'den journal'ın issue'larını al
                            from database.repositories import IssueRepository
                            issue_repo = IssueRepository()
                            issues = await issue_repo.find_by_journal(PydanticObjectId(related_id))
                            return [i.model_dump(mode='json') for i in issues[:settings.prefetch_issues_per_journal]]
                        
                        cache_service._schedule_prefetch(
                            cache_service.prefetch_journal_issues(related_id, fetch)
                        )
                
            except Exception as e:
                logger.error(f"Prefetch scheduling error: {e}")
            
            return result
        
        return wrapper
    return decorator


async def warmup_cache():
    """
    Uygulama başlangıcında sık kullanılan verileri cache'le
    """
    if not settings.redis_enabled:
        return
    
    if not await cache_service.connect():
        return
    
    logger.info("Cache warmup başlatılıyor...")
    
    try:
        # Global stats'ı cache'le
        from database.repositories import ArticleRepository, JournalRepository, IssueRepository
        
        article_repo = ArticleRepository()
        journal_repo = JournalRepository()
        issue_repo = IssueRepository()
        
        stats = {
            "total_articles": await article_repo.count(),
            "total_journals": await journal_repo.count(),
            "total_issues": await issue_repo.count(),
            "warmed_at": str(asyncio.get_event_loop().time())
        }
        
        await cache_service.set_stats(stats)
        logger.success(f"Cache warmup tamamlandı: {stats}")
        
    except Exception as e:
        logger.error(f"Cache warmup hatası: {e}")
