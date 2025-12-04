"""
Articles Router
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from beanie import PydanticObjectId

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.models import Article

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.get("/", summary="Tüm makaleleri listele")
async def list_articles(
    # Pagination
    page: int = Query(1, ge=1, description="Sayfa numarası"),
    page_size: int = Query(20, ge=1, le=100, description="Sayfa başına kayıt"),
    # Filters
    journal_id: Optional[str] = Query(None, description="Dergi ID'si"),
    issue_id: Optional[str] = Query(None, description="Sayı ID'si"),
    source_website: Optional[str] = Query(None, description="Kaynak site"),
    publication_year: Optional[int] = Query(None, description="Yayın yılı"),
    open_access: Optional[bool] = Query(None, description="Açık erişim"),
    article_type: Optional[str] = Query(None, description="Makale tipi"),
    has_doi: Optional[bool] = Query(None, description="DOI var mı"),
    has_abstract: Optional[bool] = Query(None, description="Abstract var mı"),
    # Sorting
    sort_by: str = Query("publication_year", description="Sıralama alanı"),
    sort_order: str = Query("desc", description="Sıralama yönü"),
):
    """
    Makaleleri listele.
    
    Filtreleme, sıralama ve sayfalama destekler.
    """
    # Build query
    query = {}
    
    if journal_id:
        try:
            query["journal_id"] = PydanticObjectId(journal_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid journal ID")
    
    if issue_id:
        try:
            query["issue_id"] = PydanticObjectId(issue_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid issue ID")
    
    if source_website:
        query["source_website"] = source_website
    if publication_year:
        query["publication_year"] = publication_year
    if open_access is not None:
        query["open_access"] = open_access
    if article_type:
        query["article_type"] = article_type
    if has_doi is not None:
        if has_doi:
            query["doi"] = {"$ne": None}
        else:
            query["doi"] = None
    if has_abstract is not None:
        if has_abstract:
            query["abstract"] = {"$ne": None}
        else:
            query["abstract"] = None
    
    # Sort direction
    sort_dir = 1 if sort_order == "asc" else -1
    
    # Get total count
    total = await Article.find(query).count()
    
    # Get items with pagination
    skip = (page - 1) * page_size
    
    items = await Article.find(query).sort(
        [(sort_by, sort_dir)]
    ).skip(skip).limit(page_size).to_list()
    
    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "items": [
            {
                "id": str(a.id),
                "journal_id": str(a.journal_id),
                "journal_name": a.journal_name,
                "issue_id": str(a.issue_id),
                "issue_number": a.issue_number,
                "source_website": a.source_website,
                "title": a.title,
                "url": a.url,
                "doi": a.doi,
                "abstract": a.abstract[:300] + "..." if a.abstract and len(a.abstract) > 300 else a.abstract,
                "keywords": a.keywords,
                "authors": a.authors,
                "publication_date": a.publication_date,
                "publication_year": a.publication_year,
                "pages": a.pages,
                "publisher": a.publisher,
                "article_type": a.article_type,
                "open_access": a.open_access,
                "pdf_url": a.pdf_url,
                "citation_count": a.citation_count,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
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


@router.get("/search", summary="Makale ara")
async def search_articles(
    q: str = Query(..., min_length=2, description="Arama sorgusu"),
    search_type: str = Query("text", description="Arama tipi: text, title, keyword, author"),
    limit: int = Query(50, ge=1, le=200, description="Maksimum sonuç sayısı"),
):
    """
    Makale ara.
    
    - **text**: Başlık ve abstract'ta full-text arama
    - **title**: Sadece başlıkta arama
    - **keyword**: Anahtar kelimelerde arama
    - **author**: Yazarlarda arama
    """
    if search_type == "text":
        # Full-text search
        items = await Article.find({"$text": {"$search": q}}).limit(limit).to_list()
    elif search_type == "title":
        items = await Article.find({"title": {"$regex": q, "$options": "i"}}).limit(limit).to_list()
    elif search_type == "keyword":
        items = await Article.find({"keywords": {"$in": [q]}}).limit(limit).to_list()
    elif search_type == "author":
        items = await Article.find({"authors": {"$regex": q, "$options": "i"}}).limit(limit).to_list()
    else:
        raise HTTPException(status_code=400, detail="Invalid search type")
    
    return {
        "query": q,
        "search_type": search_type,
        "count": len(items),
        "items": [
            {
                "id": str(a.id),
                "title": a.title,
                "journal_name": a.journal_name,
                "authors": a.authors,
                "publication_year": a.publication_year,
                "doi": a.doi,
                "url": a.url,
                "abstract": a.abstract[:200] + "..." if a.abstract and len(a.abstract) > 200 else a.abstract,
                "keywords": a.keywords,
            }
            for a in items
        ],
    }


@router.get("/{article_id}", summary="Makale detayı")
async def get_article(article_id: str):
    """Belirli bir makalenin tüm detaylarını getir"""
    try:
        obj_id = PydanticObjectId(article_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid article ID")
    
    article = await Article.get(obj_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return {
        "id": str(article.id),
        "journal_id": str(article.journal_id),
        "journal_name": article.journal_name,
        "issue_id": str(article.issue_id),
        "issue_number": article.issue_number,
        "source_website": article.source_website,
        "title": article.title,
        "url": article.url,
        "doi": article.doi,
        "abstract": article.abstract,
        "introduction": article.introduction,
        "keywords": article.keywords,
        "authors": article.authors,
        "publication_date": article.publication_date,
        "publication_year": article.publication_year,
        "pages": article.pages,
        "publisher": article.publisher,
        "article_type": article.article_type,
        "open_access": article.open_access,
        "pdf_url": article.pdf_url,
        "citation_count": article.citation_count,
        "references": article.references,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
    }


@router.get("/by-doi/{doi:path}", summary="DOI ile makale bul")
async def get_article_by_doi(doi: str):
    """DOI numarasına göre makale getir"""
    article = await Article.find_one({"doi": doi})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return {
        "id": str(article.id),
        "title": article.title,
        "journal_name": article.journal_name,
        "authors": article.authors,
        "doi": article.doi,
        "url": article.url,
        "abstract": article.abstract,
        "keywords": article.keywords,
        "publication_year": article.publication_year,
    }
