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
    """Belirli bir sayının detaylarını getir"""
    try:
        obj_id = PydanticObjectId(issue_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid issue ID")
    
    issue = await Issue.get(obj_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    return {
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


@router.get("/{issue_id}/articles", summary="Sayının makaleleri")
async def get_issue_articles(
    issue_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Belirli bir sayının tüm makalelerini getir"""
    try:
        obj_id = PydanticObjectId(issue_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid issue ID")
    
    # Check issue exists
    issue = await Issue.get(obj_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    query = {"issue_id": obj_id}
    total = await Article.find(query).count()
    
    skip = (page - 1) * page_size
    items = await Article.find(query).skip(skip).limit(page_size).to_list()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "issue": {
            "id": str(issue.id),
            "journal_name": issue.journal_name,
            "issue_number": issue.issue_number,
        },
        "items": [
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
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
