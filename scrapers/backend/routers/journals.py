"""
Journals Router
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from beanie import PydanticObjectId

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.models import Journal
from database.repositories import JournalRepository
from backend.services.cache_service import cache_service
from backend.core.config import settings
from backend.schemas.journal import JournalListResponse, JournalResponse, JournalCitationMetricsResponse
from utils.logger import get_logger

logger = get_logger('journals_router')

router = APIRouter(prefix="/journals", tags=["Journals"])


def get_journal_repo() -> JournalRepository:
    return JournalRepository()


@router.get("/", summary="Tüm dergileri listele", response_model=JournalListResponse)
async def list_journals(
    # Pagination
    page: int = Query(1, ge=1, description="Sayfa numarası"),
    page_size: int = Query(20, ge=1, le=100, description="Sayfa başına kayıt"),
    # Filters
    source_website: Optional[str] = Query(None, description="Kaynak site: ieeexplore, sciencedirect"),
    publisher: Optional[str] = Query(None, description="Yayıncı"),
    open_access: Optional[bool] = Query(None, description="Açık erişim"),
    letter_group: Optional[str] = Query(None, description="Alfabetik grup"),
    search: Optional[str] = Query(None, description="İsim araması"),
    year_min: Optional[int] = Query(None, description="Sayı yılı aralığı - başlangıç"),
    year_max: Optional[int] = Query(None, description="Sayı yılı aralığı - bitiş"),
    # Sorting
    sort_by: str = Query("name", description="Sıralama alanı: name, article_count, issue_count"),
    sort_order: str = Query("asc", description="Sıralama yönü: asc, desc"),
    repo: JournalRepository = Depends(get_journal_repo),
):
    """
    Dergileri listele.
    
    Filtreleme, sıralama ve sayfalama destekler.
    """
    
    # Cache Check
    cache_params = {
        "page": page,
        "page_size": page_size,
        "source_website": source_website,
        "publisher": publisher,
        "open_access": open_access,
        "letter_group": letter_group,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "year_min": year_min,
        "year_max": year_max,
    }
    search_query = search or ""
    
    cached_result = await cache_service.get_search_results(f"journals_list_v2_{search_query}", cache_params)
    if cached_result:
        logger.info(f"Cache HIT: journals list (page {page})")
        return cached_result

    # Build query
    query = {}
    
    if source_website:
        query["source_website"] = source_website
    if publisher:
        query["publisher"] = {"$regex": publisher, "$options": "i"}
    if open_access is not None:
        query["open_access"] = open_access
    if letter_group:
        query["letter_group"] = letter_group
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if year_min is not None or year_max is not None:
        from database.models import Issue
        year_filter: dict = {}
        if year_min is not None:
            year_filter["$gte"] = year_min
        if year_max is not None:
            year_filter["$lte"] = year_max
        pipeline = [
            {"$match": {"year": year_filter}},
            {"$group": {"_id": "$journal_id"}},
        ]
        issue_collection = Issue.get_pymongo_collection()
        matching = await issue_collection.aggregate(pipeline).to_list(length=None)
        matching_ids = [doc["_id"] for doc in matching]
        if matching_ids:
            query["_id"] = {"$in": matching_ids}
        else:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0, "has_next": False, "has_prev": False}

    # Sort direction
    sort_dir = 1 if sort_order == "asc" else -1
    
    # Get total count
    total = await Journal.find(query).count()
    
    # Get items with pagination
    skip = (page - 1) * page_size
    
    items = await Journal.find(query).sort(
        [(sort_by, sort_dir)]
    ).skip(skip).limit(page_size).to_list()
    
    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    result = {
        "items": [
            {
                "id": str(j.id),
                "name": j.name,
                "url": j.url,
                "source_website": j.source_website,
                "type": j.type,
                "open_access": j.open_access,
                "letter_group": j.letter_group,
                "publisher": j.publisher,
                "issue_count": j.issue_count,
                "article_count": j.article_count,
                "issn": j.issn,
                "eissn": j.eissn,
                "impact_factor": j.impact_factor,
                "subjects": j.subjects,
                "openalex_id": getattr(j, "openalex_id", None),
                "h_index": getattr(j, "h_index", None),
                "i10_index": getattr(j, "i10_index", None),
                "total_citation_count": getattr(j, "total_citation_count", 0),
                "average_citation_count": getattr(j, "average_citation_count", None),
                "last_citation_update_date": getattr(j, "last_citation_update_date", None),
                "aims_and_scope": getattr(j, "aims_and_scope", None),
                "created_at": j.created_at,
                "updated_at": j.updated_at,
            }
            for j in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
    
    await cache_service.set_search_results(f"journals_list_v2_{search_query}", cache_params, result)
    logger.info(f"Cache MISS: journals list (page {page}) - cached")
    return result


@router.get("/year-range", summary="Dergi sayı yılı min/max değerlerini getir")
async def get_journal_year_range():
    """Veritabanındaki sayıların (issue) en küçük ve en büyük yılını döndürür."""
    from database.models import Issue
    pipeline = [
        {"$match": {"year": {"$ne": None}}},
        {"$group": {"_id": None, "min_year": {"$min": "$year"}, "max_year": {"$max": "$year"}}},
    ]
    collection = Issue.get_pymongo_collection()
    result = await collection.aggregate(pipeline).to_list(length=1)
    if result:
        return {"min_year": result[0]["min_year"], "max_year": result[0]["max_year"]}
    return {"min_year": 2000, "max_year": 2025}


@router.get("/{journal_id}", summary="Dergi detayı", response_model=JournalResponse)
async def get_journal(journal_id: str):
    """Belirli bir derginin detaylarını getir (cached)"""
    try:
        obj_id = PydanticObjectId(journal_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid journal ID")
    
    # Cache'den dene
    cached = await cache_service.get_journal(journal_id)
    if cached:
        logger.info(f"Cache HIT: journal {journal_id}")
        return cached
    
    journal = await Journal.get(obj_id)
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    
    result = {
        "id": str(journal.id),
        "name": journal.name,
        "url": journal.url,
        "source_website": journal.source_website,
        "type": journal.type,
        "open_access": journal.open_access,
        "letter_group": journal.letter_group,
        "publisher": journal.publisher,
        "issue_count": journal.issue_count,
        "article_count": journal.article_count,
        "issn": journal.issn,
        "eissn": journal.eissn,
        "impact_factor": journal.impact_factor,
        "subjects": journal.subjects,
        "openalex_id": getattr(journal, "openalex_id", None),
        "h_index": getattr(journal, "h_index", None),
        "i10_index": getattr(journal, "i10_index", None),
        "average_citation_count": getattr(journal, "average_citation_count", None),
        "total_citation_count": getattr(journal, "total_citation_count", 0),
        "last_citation_update_date": getattr(journal, "last_citation_update_date", None),
        "aims_and_scope": getattr(journal, "aims_and_scope", None),
        "created_at": journal.created_at,
        "updated_at": journal.updated_at,
    }
    
    # Cache'e yaz
    await cache_service.set_journal(journal_id, result)
    logger.info(f"Cache MISS: journal {journal_id} - cached")
    
    # Prefetch: Derginin issue'larını background'da cache'le (eğer yoksa)
    if settings.prefetch_enabled:
        async def prefetch_issues():
            try:
                # Önce cache'de var mı kontrol et
                if await cache_service.get_journal_issues(journal_id):
                    logger.info(f"Prefetch skipped: journal {journal_id} issues already cached")
                    return
                
                from database.models import Issue
                logger.info(f"Prefetch starting: journal {journal_id} issues")
                issues = await Issue.find({"journal_id": obj_id}).sort([("year", -1), ("month", -1)]).limit(settings.prefetch_issues_per_journal).to_list()
                if issues:
                    # Endpoint ile aynı formatta cache'le
                    issues_data = [
                        {
                            "id": str(i.id),
                            "journal_id": str(i.journal_id),
                            "issue_number": i.issue_number,
                            "volume": i.volume,
                            "number": i.number,
                            "date": i.date,
                            "year": i.year,
                            "month": i.month,
                            "url": i.url,
                            "status": i.status,
                            "article_count": i.article_count,
                        }
                        for i in issues
                    ]
                    await cache_service.set_journal_issues(journal_id, issues_data)
                    logger.info(f"Prefetch completed: {len(issues)} issues for journal {journal_id}")
                else:
                    logger.info(f"Prefetch: no issues found for journal {journal_id}")
            except Exception as e:
                logger.error(f"Prefetch error (journal issues): {e}")
        cache_service._schedule_prefetch(prefetch_issues())
    
    return result


@router.post("/recalculate-counts", summary="Tüm dergilerin sayı ve makale sayılarını yeniden hesapla")
async def recalculate_all_counts():
    """
    Tüm dergilerin issue_count ve article_count alanlarını
    veritabanındaki gerçek verilerden yeniden hesaplar.
    Önbelleği de temizler.
    """
    from database.service import get_database_service

    db_service = get_database_service()
    journals = await Journal.find_all().to_list()

    updated = 0
    for j in journals:
        await db_service.recalculate_journal_counts(j.id)
        # last_scraped_at null ise created_at ile doldur
        if j.last_scraped_at is None:
            j.last_scraped_at = j.created_at
            j.touch()
            await j.save()
        updated += 1

    return {"success": True, "journals_updated": updated}


@router.get("/{journal_id}/citation-metrics", summary="Dergi Atıf Metrikleri", response_model=JournalCitationMetricsResponse)
async def get_journal_citation_metrics(journal_id: str):
    """Belirli bir derginin detaylı atıf istatistiklerini getirir."""
    try:
        obj_id = PydanticObjectId(journal_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid journal ID")
        
    journal = await Journal.get(obj_id)
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
        
    return {
        "id": str(journal.id),
        "name": journal.name,
        "openalex_id": getattr(journal, "openalex_id", None),
        "h_index": getattr(journal, "h_index", None),
        "i10_index": getattr(journal, "i10_index", None),
        "average_citation_count": getattr(journal, "average_citation_count", None),
        "total_citation_count": getattr(journal, "total_citation_count", 0),
        "historical_citation_data": getattr(journal, "historical_citation_data", {}),
        "last_citation_update_date": getattr(journal, "last_citation_update_date", None),
    }

@router.get("/{journal_id}/issues", summary="Derginin sayıları")
async def get_journal_issues(
    journal_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Belirli bir derginin tüm sayılarını getir (cached for first page)"""
    from database.models import Issue
    
    try:
        obj_id = PydanticObjectId(journal_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid journal ID")
    
    # İlk sayfa için cache'den dene (prefetch ile aynı format)
    if page == 1 and page_size <= 20:
        cached_issues = await cache_service.get_journal_issues(journal_id)
        if cached_issues:
            logger.info(f"Cache HIT: journal {journal_id} issues")
            journal = await Journal.get(obj_id)
            if journal:
                return {
                    "journal": {"id": str(journal.id), "name": journal.name},
                    "items": cached_issues[:page_size],
                    "total": len(cached_issues),
                    "page": 1,
                    "page_size": page_size,
                    "total_pages": 1,
                    "has_next": len(cached_issues) > page_size,
                    "has_prev": False,
                }
    
    # Check journal exists
    journal = await Journal.get(obj_id)
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    
    query = {"journal_id": obj_id}
    total = await Issue.find(query).count()
    
    skip = (page - 1) * page_size
    items = await Issue.find(query).sort([("year", -1), ("month", -1)]).skip(skip).limit(page_size).to_list()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    issues_data = [
        {
            "id": str(i.id),
            "journal_id": str(i.journal_id),
            "issue_number": i.issue_number,
            "volume": i.volume,
            "number": i.number,
            "date": i.date,
            "year": i.year,
            "month": i.month,
            "url": i.url,
            "status": i.status,
            "article_count": i.article_count,
        }
        for i in items
    ]
    
    # İlk sayfa ise cache'le
    if page == 1:
        await cache_service.set_journal_issues(journal_id, issues_data)
        logger.info(f"Cache MISS: journal {journal_id} issues - cached")
    
    return {
        "journal": {"id": str(journal.id), "name": journal.name},
        "items": issues_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


@router.get("/{journal_id}/articles", summary="Derginin makaleleri")
async def get_journal_articles(
    journal_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Belirli bir derginin tüm makalelerini getir"""
    from database.models import Article
    
    try:
        obj_id = PydanticObjectId(journal_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid journal ID")
    
    # Check journal exists
    journal = await Journal.get(obj_id)
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    
    query = {"journal_id": obj_id}
    total = await Article.find(query).count()
    
    skip = (page - 1) * page_size
    items = await Article.find(query).sort([("publication_year", -1)]).skip(skip).limit(page_size).to_list()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "journal": {"id": str(journal.id), "name": journal.name},
        "items": [
            {
                "id": str(a.id),
                "title": a.title,
                "url": a.url,
                "doi": a.doi,
                "authors": a.authors,
                "publication_date": a.publication_date,
                "publication_year": a.publication_year,
                "article_type": a.article_type,
                "open_access": a.open_access,
            }
            for a in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
