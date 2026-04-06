"""
Authors Router
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.authors import authors_service

router = APIRouter(prefix="/authors", tags=["Authors"])

@router.get("/", summary="Yazarları Listele")
async def get_authors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("article_count_desc", description="Sıralama: article_count_desc, article_count_asc, name_asc, name_desc"),
    search: Optional[str] = Query(None, min_length=2, description="Yazar adı ile arama"),
    min_articles: Optional[int] = Query(None, ge=1, description="En az makale sayısı filtresi")
):
    """
    Sistemdeki yazarları makale sayıları vb. özelliklere göre listeleyip döndürür.
    Redis'te cachelenir. Arama ve filtreleme yapılabilir.
    """
    return await authors_service.get_authors_list(
        page=page, 
        page_size=page_size, 
        sort_by=sort_by,
        search=search,
        min_articles=min_articles
    )

@router.get("/{name}", summary="Yazar Detayları Getir")
async def get_author_by_name(name: str):
    """
    Belirli bir yazarın metriklerini ve makalelerini (DB + OpenAlex harmanlanmış şekilde) döndürür.
    Uzun süreli Redis cache'ine kaydedilir.
    """
    profile = await authors_service.get_author_profile(name)
    if not profile:
        raise HTTPException(status_code=404, detail="Yazar sistemde bulunamadı")
    return profile

@router.get("/{name}/articles", summary="Yazar Makalelerini Getir")
async def get_author_articles_paginated(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100)
):
    """
    Yazarın kaleme aldığı makaleleri veritabanından paginated (sayfalı) olarak döndürür.
    """
    return await authors_service.get_author_articles(name, page, page_size)
