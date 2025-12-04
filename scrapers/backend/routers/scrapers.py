"""
Scrapers Router

Scraper yönetimi için endpointler.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..core.dependencies import get_scraper_manager

router = APIRouter(prefix="/scrapers", tags=["Scrapers"])


class ScraperControlRequest(BaseModel):
    """Scraper kontrol request"""
    headless: bool = Field(default=True, description="Headless mod")
    max_articles: Optional[int] = Field(None, description="Maksimum makale sayısı")


# ==================== Status Endpoints ====================

@router.get("/status", summary="Tüm scraper'ların durumu")
async def get_all_status():
    """Tüm scraper'ların mevcut durumunu getir"""
    manager = get_scraper_manager()
    return manager.get_all_status()


@router.get("/status/ieee", summary="IEEE scraper durumu")
async def get_ieee_status():
    """IEEE scraper'ın mevcut durumunu getir"""
    manager = get_scraper_manager()
    return manager.get_ieee_status()


@router.get("/status/sciencedirect", summary="ScienceDirect scraper durumu")
async def get_sciencedirect_status():
    """ScienceDirect scraper'ın mevcut durumunu getir"""
    manager = get_scraper_manager()
    return manager.get_sciencedirect_status()


# ==================== IEEE Control ====================

@router.post("/ieee/start", summary="IEEE scraper'ı başlat")
async def start_ieee(request: ScraperControlRequest = None):
    """
    IEEE scraper'ı başlat.
    
    - **headless**: Browser'ı görünmez modda çalıştır (default: True)
    - **max_articles**: Her journal'dan maksimum kaç makale çekilecek
    """
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    max_articles = request.max_articles if request and request.max_articles else 10
    
    success = await manager.start_ieee(headless=headless, max_articles=max_articles)
    
    if not success:
        raise HTTPException(status_code=400, detail="IEEE scraper already running")
    
    return {
        "success": True,
        "message": "IEEE scraper started",
        "status": manager.get_ieee_status()
    }


@router.post("/ieee/stop", summary="IEEE scraper'ı durdur")
async def stop_ieee():
    """IEEE scraper'ı durdur"""
    manager = get_scraper_manager()
    success = await manager.stop_ieee()
    
    if not success:
        raise HTTPException(status_code=400, detail="IEEE scraper is not running")
    
    return {
        "success": True,
        "message": "IEEE scraper stopping",
        "status": manager.get_ieee_status()
    }


@router.post("/ieee/pause", summary="IEEE scraper'ı duraklat")
async def pause_ieee():
    """IEEE scraper'ı duraklat"""
    manager = get_scraper_manager()
    success = await manager.pause_ieee()
    
    if not success:
        raise HTTPException(status_code=400, detail="IEEE scraper is not running")
    
    return {
        "success": True,
        "message": "IEEE scraper paused",
        "status": manager.get_ieee_status()
    }


@router.post("/ieee/resume", summary="IEEE scraper'ı devam ettir")
async def resume_ieee():
    """Duraklatılmış IEEE scraper'ı devam ettir"""
    manager = get_scraper_manager()
    success = await manager.resume_ieee()
    
    if not success:
        raise HTTPException(status_code=400, detail="IEEE scraper is not paused")
    
    return {
        "success": True,
        "message": "IEEE scraper resumed",
        "status": manager.get_ieee_status()
    }


# ==================== ScienceDirect Control ====================

@router.post("/sciencedirect/start", summary="ScienceDirect scraper'ı başlat")
async def start_sciencedirect(request: ScraperControlRequest = None):
    """
    ScienceDirect scraper'ı başlat.
    
    - **headless**: Browser'ı görünmez modda çalıştır (default: True)
    - **max_articles**: Her journal'dan maksimum kaç makale çekilecek
    """
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    max_articles = request.max_articles if request and request.max_articles else 5
    
    success = await manager.start_sciencedirect(headless=headless, max_articles=max_articles)
    
    if not success:
        raise HTTPException(status_code=400, detail="ScienceDirect scraper already running")
    
    return {
        "success": True,
        "message": "ScienceDirect scraper started",
        "status": manager.get_sciencedirect_status()
    }


@router.post("/sciencedirect/stop", summary="ScienceDirect scraper'ı durdur")
async def stop_sciencedirect():
    """ScienceDirect scraper'ı durdur"""
    manager = get_scraper_manager()
    success = await manager.stop_sciencedirect()
    
    if not success:
        raise HTTPException(status_code=400, detail="ScienceDirect scraper is not running")
    
    return {
        "success": True,
        "message": "ScienceDirect scraper stopping",
        "status": manager.get_sciencedirect_status()
    }


@router.post("/sciencedirect/pause", summary="ScienceDirect scraper'ı duraklat")
async def pause_sciencedirect():
    """ScienceDirect scraper'ı duraklat"""
    manager = get_scraper_manager()
    success = await manager.pause_sciencedirect()
    
    if not success:
        raise HTTPException(status_code=400, detail="ScienceDirect scraper is not running")
    
    return {
        "success": True,
        "message": "ScienceDirect scraper paused",
        "status": manager.get_sciencedirect_status()
    }


@router.post("/sciencedirect/resume", summary="ScienceDirect scraper'ı devam ettir")
async def resume_sciencedirect():
    """Duraklatılmış ScienceDirect scraper'ı devam ettir"""
    manager = get_scraper_manager()
    success = await manager.resume_sciencedirect()
    
    if not success:
        raise HTTPException(status_code=400, detail="ScienceDirect scraper is not paused")
    
    return {
        "success": True,
        "message": "ScienceDirect scraper resumed",
        "status": manager.get_sciencedirect_status()
    }


# ==================== All Scrapers ====================

@router.post("/start-all", summary="Tüm scraper'ları başlat")
async def start_all(request: ScraperControlRequest = None):
    """Tüm scraper'ları başlat"""
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    
    results = await manager.start_all(headless=headless)
    
    return {
        "success": True,
        "message": "All scrapers started",
        "results": results,
        "status": manager.get_all_status()
    }


@router.post("/stop-all", summary="Tüm scraper'ları durdur")
async def stop_all():
    """Tüm scraper'ları durdur"""
    manager = get_scraper_manager()
    results = await manager.stop_all()
    
    return {
        "success": True,
        "message": "All scrapers stopped",
        "results": results,
        "status": manager.get_all_status()
    }


# ==================== Logs ====================

@router.get("/logs", summary="Scraper logları")
async def get_logs(
    scraper_type: str = Query("all", description="Scraper tipi: all, ieee, sciencedirect"),
    limit: int = Query(50, ge=1, le=200, description="Maksimum log sayısı"),
):
    """Scraper loglarını getir"""
    manager = get_scraper_manager()
    logs = manager.get_logs(scraper_type=scraper_type, limit=limit)
    
    return {
        "scraper_type": scraper_type,
        "count": len(logs),
        "logs": logs
    }
