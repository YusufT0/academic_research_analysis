"""
Issues Router
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from beanie import PydanticObjectId

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.models import Issue, Article
from backend.services.cache_service import cache_service
from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger('issues_router')

router = APIRouter(prefix="/issues", tags=["Issues"])


@router.get("/", summary="Tüm sayıları listele")
async def list_issues(
    # Pagination
    page: int = Query(1, ge=1, description="Sayfa numarası"),
    page_size: int = Query(20, ge=1, le=100, description="Sayfa başına kayıt"),
    # Filters
    journal_id: Optional[str] = Query(None, description="Dergi ID'si"),
    source_website: Optional[str] = Query(None, description="Kaynak site"),
    year: Optional[int] = Query(None, description="Yayın yılı"),
    status: Optional[str] = Query(None, description="Durum"),
    # Sorting
    sort_by: str = Query("year", description="Sıralama alanı: year, article_count, journal_name"),
    sort_order: str = Query("desc", description="Sıralama yönü"),
):
    """
    Sayıları listele.
    
    Filtreleme, sıralama ve sayfalama destekler.
    """
    # Build query
    query = {}
    
    if journal_id:
        try:
            query["journal_id"] = PydanticObjectId(journal_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid journal ID")
    
    if source_website:
        query["source_website"] = source_website
    if year:
        query["year"] = year
    if status:
        query["status"] = status
    
    # Sort direction
    sort_dir = 1 if sort_order == "asc" else -1
    
    # Get total count
    total = await Issue.find(query).count()
    
    # Get items with pagination
    skip = (page - 1) * page_size
    
    items = await Issue.find(query).sort(
        [(sort_by, sort_dir)]
    ).skip(skip).limit(page_size).to_list()
    
    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "items": [
            {
                "id": str(i.id),
                "journal_id": str(i.journal_id),
                "journal_name": i.journal_name,
                "source_website": i.source_website,
                "issue_number": i.issue_number,
                "volume": i.volume,
                "number": i.number,
                "date": i.date,
                "year": i.year,
                "month": i.month,
                "url": i.url,
                "status": i.status,
                "article_count": i.article_count,
                "pages": i.pages,
                "created_at": i.created_at,
                "updated_at": i.updated_at,
            }
            for i in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


@router.get("/{issue_id}", summary="Sayı detayı")
async def get_issue(issue_id: str):
    """Belirli bir sayının detaylarını getir (cached)"""
    try:
        obj_id = PydanticObjectId(issue_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid issue ID")
    
    # Cache'den dene
    cached = await cache_service.get_issue(issue_id)
    if cached:
        logger.info(f"Cache HIT: issue {issue_id}")
        return cached
    
    issue = await Issue.get(obj_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    result = {
        "id": str(issue.id),
        "journal_id": str(issue.journal_id),
        "journal_name": issue.journal_name,
        "source_website": issue.source_website,
        "issue_number": issue.issue_number,
        "volume": issue.volume,
        "number": issue.number,
        "date": issue.date,
        "year": issue.year,
        "month": issue.month,
        "url": issue.url,
        "status": issue.status,
        "article_count": issue.article_count,
        "pages": issue.pages,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }
    
    # Cache'e yaz
    await cache_service.set_issue(issue_id, result)
    logger.info(f"Cache MISS: issue {issue_id} - cached")
    
    # Prefetch: Issue'nun makalelerini background'da cache'le (eğer yoksa)
    if settings.prefetch_enabled:
        async def prefetch_articles():
            try:
                # Önce cache'de var mı kontrol et
                if await cache_service.get_issue_articles(issue_id):
                    logger.info(f"Prefetch skipped: issue {issue_id} articles already cached")
                    return
                
                logger.info(f"Prefetch starting: issue {issue_id} articles")
                articles = await Article.find({"issue_id": obj_id}).limit(settings.prefetch_articles_per_issue).to_list()
                if articles:
                    # Endpoint ile aynı formatta cache'le
                    articles_data = [
                        {
                            "id": str(a.id),
                            "title": a.title,
                            "url": a.url,
                            "doi": a.doi,
                            "authors": a.authors,
                            "abstract": a.abstract[:300] + "..." if a.abstract and len(a.abstract) > 300 else a.abstract,
                            "keywords": a.keywords,
                            "publication_date": a.publication_date,
                            "article_type": a.article_type,
                            "open_access": a.open_access,
                            "pdf_url": a.pdf_url,
                        }
                        for a in articles
                    ]
                    await cache_service.set_issue_articles(issue_id, articles_data)
                    logger.info(f"Prefetch completed: {len(articles)} articles for issue {issue_id}")
                else:
                    logger.info(f"Prefetch: no articles found for issue {issue_id}")
            except Exception as e:
                logger.error(f"Prefetch error (issue articles): {e}")
        cache_service._schedule_prefetch(prefetch_articles())
        
        # Prefetch: Aynı journal'daki komşu issue'ları cache'le
        async def prefetch_neighbor_issues():
            try:
                # Aynı journal'daki issue'ları year/month sırasına göre al
                all_issues = await Issue.find({"journal_id": issue.journal_id}).sort([("year", -1), ("month", -1)]).to_list()
                
                if len(all_issues) <= 1:
                    return
                
                # Mevcut issue'nun index'ini bul
                current_idx = None
                for idx, iss in enumerate(all_issues):
                    if str(iss.id) == issue_id:
                        current_idx = idx
                        break
                
                if current_idx is None:
                    return
                
                # Önceki ve sonraki issue'ları al (ayardan)
                n = settings.prefetch_neighbor_issues
                neighbor_indices = [current_idx + i for i in range(-n, n+1) if i != 0]
                neighbor_indices = [i for i in neighbor_indices if 0 <= i < len(all_issues)]
                
                prefetched = 0
                for idx in neighbor_indices:
                    neighbor_issue = all_issues[idx]
                    neighbor_id = str(neighbor_issue.id)
                    
                    # Zaten cache'de mi?
                    if await cache_service.get_issue(neighbor_id):
                        continue
                    
                    neighbor_data = {
                        "id": neighbor_id,
                        "journal_id": str(neighbor_issue.journal_id),
                        "journal_name": neighbor_issue.journal_name,
                        "source_website": neighbor_issue.source_website,
                        "issue_number": neighbor_issue.issue_number,
                        "volume": neighbor_issue.volume,
                        "number": neighbor_issue.number,
                        "date": neighbor_issue.date,
                        "year": neighbor_issue.year,
                        "month": neighbor_issue.month,
                        "url": neighbor_issue.url,
                        "status": neighbor_issue.status,
                        "article_count": neighbor_issue.article_count,
                        "pages": neighbor_issue.pages,
                        "created_at": neighbor_issue.created_at,
                        "updated_at": neighbor_issue.updated_at,
                    }
                    await cache_service.set_issue(neighbor_id, neighbor_data)
                    prefetched += 1
                
                if prefetched > 0:
                    logger.info(f"Prefetch completed: {prefetched} neighbor issues for issue {issue_id}")
            except Exception as e:
                logger.error(f"Neighbor issue prefetch error: {e}")
        
        cache_service._schedule_prefetch(prefetch_neighbor_issues())
    
    return result


@router.get("/{issue_id}/articles", summary="Sayının makaleleri")
async def get_issue_articles(
    issue_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Belirli bir sayının tüm makalelerini getir (cached for first page)"""
    try:
        obj_id = PydanticObjectId(issue_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid issue ID")
    
    # İlk sayfa için cache'den dene
    if page == 1 and page_size <= 30:
        cached_articles = await cache_service.get_issue_articles(issue_id)
        if cached_articles:
            logger.info(f"Cache HIT: issue {issue_id} articles")
            # Issue bilgisi de lazım
            issue = await Issue.get(obj_id)
            if issue:
                return {
                    "issue": {
                        "id": str(issue.id),
                        "journal_name": issue.journal_name,
                        "issue_number": issue.issue_number,
                    },
                    "items": cached_articles[:page_size],
                    "total": len(cached_articles),
                    "page": 1,
                    "page_size": page_size,
                    "total_pages": 1,
                    "has_next": len(cached_articles) > page_size,
                    "has_prev": False,
                }
    
    # Check issue exists
    issue = await Issue.get(obj_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    query = {"issue_id": obj_id}
    total = await Article.find(query).count()
    
    skip = (page - 1) * page_size
    items = await Article.find(query).skip(skip).limit(page_size).to_list()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    articles_data = [
        {
            "id": str(a.id),
            "title": a.title,
            "url": a.url,
            "doi": a.doi,
            "authors": a.authors,
            "abstract": a.abstract[:300] + "..." if a.abstract and len(a.abstract) > 300 else a.abstract,
            "keywords": a.keywords,
            "publication_date": a.publication_date,
            "article_type": a.article_type,
            "open_access": a.open_access,
            "pdf_url": a.pdf_url,
        }
        for a in items
    ]
    
    # İlk sayfa ise cache'le
    if page == 1:
        await cache_service.set_issue_articles(issue_id, articles_data)
        logger.info(f"Cache MISS: issue {issue_id} articles - cached")
    
    return {
        "issue": {
            "id": str(issue.id),
            "journal_name": issue.journal_name,
            "issue_number": issue.issue_number,
        },
        "items": articles_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
