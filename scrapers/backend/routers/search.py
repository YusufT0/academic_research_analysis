"""
Search Router

Elasticsearch full-text arama endpoint'leri.
"""

from typing import Optional
from fastapi import APIRouter, Query

from ..services.elasticsearch_service import elasticsearch_service
from ..services.cache_service import cache_service
from utils.logger import get_logger

logger = get_logger('search_router')

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("/sync", summary="MongoDB → Elasticsearch senkronizasyon")
async def sync_to_elasticsearch():
    """
    MongoDB'deki tüm makaleleri Elasticsearch'e bulk index'ler.
    İlk kurulumda veya veri düzeltme sonrası çağrılır.
    """
    if not elasticsearch_service.is_connected:
        return {"status": "error", "message": "Elasticsearch bağlantısı yok"}
    
    try:
        from database.models import Article
        
        # Tüm makaleleri MongoDB'den çek
        articles = await Article.find_all().to_list()
        
        if not articles:
            return {"status": "ok", "indexed": 0, "message": "Veritabanında makale yok"}
        
        # Beanie document → dict
        article_dicts = []
        for a in articles:
            d = a.model_dump()
            d["id"] = str(a.id)
            if a.journal_id:
                d["journal_id"] = str(a.journal_id)
            if a.issue_id:
                d["issue_id"] = str(a.issue_id)
            article_dicts.append(d)
        
        # Batch index (500'er)
        total_indexed = 0
        batch_size = 500
        for i in range(0, len(article_dicts), batch_size):
            batch = article_dicts[i:i + batch_size]
            count = await elasticsearch_service.bulk_index(batch)
            total_indexed += count
        
        return {
            "status": "ok",
            "total_articles": len(articles),
            "indexed": total_indexed,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("", summary="Full-text makale arama")
@router.get("/", summary="Full-text makale arama")
async def search_articles(
    q: str = Query(..., min_length=2, description="Arama sorgusu"),
    source_website: Optional[str] = Query(None, description="Kaynak site filtresi"),
    publication_year: Optional[int] = Query(None, description="Yayın yılı filtresi"),
    journal_name: Optional[str] = Query(None, description="Dergi filtresi"),
    open_access: Optional[bool] = Query(None, description="Açık erişim filtresi"),
    page: int = Query(1, ge=1, description="Sayfa"),
    page_size: int = Query(20, ge=1, le=100, description="Sayfa boyutu"),
):
    """
    Elasticsearch ile full-text makale arama.
    
    - Başlık, abstract, keyword ve author üzerinde arama
    - Fuzzy matching (yazım hataları tolere)
    - Faceted filtreler (kaynak, yıl, dergi)
    - Highlight (eşleşen kelimelerin vurgulanması)
    """
    filters = {}
    if source_website:
        filters["source_website"] = source_website
    if publication_year:
        filters["publication_year"] = publication_year
    if journal_name:
        filters["journal_name"] = journal_name
    if open_access is not None:
        filters["open_access"] = open_access
    
    # Cache Check
    cache_params = {
        "filters": filters,
        "page": page,
        "page_size": page_size
    }
    
    cached_result = await cache_service.get_search_results(f"es_search_{q}", cache_params)
    if cached_result:
        logger.info(f"Cache HIT: ES search ({q}) page {page}")
        return cached_result
    
    result = await elasticsearch_service.search(
        query=q,
        filters=filters if filters else None,
        page=page,
        page_size=page_size,
    )
    
    await cache_service.set_search_results(f"es_search_{q}", cache_params, result)
    logger.info(f"Cache MISS: ES search ({q}) page {page} - cached")
    return result


@router.get("/suggest", summary="Autocomplete önerileri")
async def search_suggest(
    q: str = Query(..., min_length=1, description="Arama prefix'i"),
    limit: int = Query(10, ge=1, le=50, description="Öneri sayısı"),
):
    """Title ve keyword'lere göre autocomplete önerileri"""
    suggestions = await elasticsearch_service.suggest(prefix=q, limit=limit)
    return {"query": q, "suggestions": [s["text"] for s in suggestions], "items": suggestions}


@router.get("/suggest/journals", summary="Dergi adı autocomplete önerileri")
async def suggest_journals(
    q: str = Query(..., min_length=1, description="Arama prefix'i"),
    limit: int = Query(15, ge=1, le=50, description="Öneri sayısı"),
):
    """
    Elasticsearch üzerinden dergi adı autocomplete.

    Wildcard + aggregation kullanarak veritabanındaki gerçek dergi
    adlarını (journal_name) prefix eşleşmesine göre döner.
    """
    suggestions = await elasticsearch_service.suggest_journals(prefix=q, limit=limit)
    return {"query": q, "suggestions": suggestions}


@router.get("/facets", summary="Arama filtreleri")
async def search_facets():
    """
    Aggregation bazlı filtre seçenekleri.
    
    Kaynaklar, yıllar, dergiler, makale tipleri, top keywords, top authors.
    """
    facets = await elasticsearch_service.get_facets()
    return {"facets": facets}
