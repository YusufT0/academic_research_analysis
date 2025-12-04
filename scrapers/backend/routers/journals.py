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

router = APIRouter(prefix="/journals", tags=["Journals"])


def get_journal_repo() -> JournalRepository:
    return JournalRepository()


@router.get("/", summary="Tüm dergileri listele")
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
    # Sorting
    sort_by: str = Query("name", description="Sıralama alanı: name, article_count, issue_count"),
    sort_order: str = Query("asc", description="Sıralama yönü: asc, desc"),
    repo: JournalRepository = Depends(get_journal_repo),
):
    """
    Dergileri listele.
    
    Filtreleme, sıralama ve sayfalama destekler.
    """
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
    
    return {
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


@router.get("/{journal_id}", summary="Dergi detayı")
async def get_journal(journal_id: str):
    """Belirli bir derginin detaylarını getir"""
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
        "created_at": journal.created_at,
        "updated_at": journal.updated_at,
    }


@router.get("/{journal_id}/issues", summary="Derginin sayıları")
async def get_journal_issues(
    journal_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Belirli bir derginin tüm sayılarını getir"""
    from database.models import Issue
    
    try:
        obj_id = PydanticObjectId(journal_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid journal ID")
    
    # Check journal exists
    journal = await Journal.get(obj_id)
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    
    query = {"journal_id": obj_id}
    total = await Issue.find(query).count()
    
    skip = (page - 1) * page_size
    items = await Issue.find(query).sort([("year", -1), ("month", -1)]).skip(skip).limit(page_size).to_list()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "journal": {"id": str(journal.id), "name": journal.name},
        "items": [
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
        ],
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
