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



@router.get("/status/acm", summary="ACM scraper durumu")
async def get_acm_status():
    """ACM scraper'ın mevcut durumunu getir"""
    manager = get_scraper_manager()
    return manager.get_acm_status()

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
    max_articles = request.max_articles if request and request.max_articles else 100
    
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
    max_articles = request.max_articles if request and request.max_articles else 100
    
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



# ==================== ACM Control ====================

@router.post("/acm/start", summary="ACM scraper'ı başlat")
async def start_acm(request: ScraperControlRequest = None):
    """
    ACM scraper'ı başlat.
    
    - **headless**: Browser'ı görünmez modda çalıştır (default: True)
    - **max_articles**: Her journal'dan maksimum kaç makale çekilecek
    """
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    max_articles = request.max_articles if request and request.max_articles else 100
    
    success = await manager.start_acm(headless=headless, max_articles=max_articles)
    
    if not success:
        raise HTTPException(status_code=400, detail="ACM scraper already running")
    
    return {
        "success": True,
        "message": "ACM scraper started",
        "status": manager.get_acm_status()
    }


@router.post("/acm/stop", summary="ACM scraper'ı durdur")
async def stop_acm():
    """ACM scraper'ı durdur"""
    manager = get_scraper_manager()
    success = await manager.stop_acm()
    
    if not success:
        raise HTTPException(status_code=400, detail="ACM scraper is not running")
    
    return {
        "success": True,
        "message": "ACM scraper stopping",
        "status": manager.get_acm_status()
    }


@router.post("/acm/pause", summary="ACM scraper'ı duraklat")
async def pause_acm():
    """ACM scraper'ı duraklat"""
    manager = get_scraper_manager()
    success = await manager.pause_acm()
    
    if not success:
        raise HTTPException(status_code=400, detail="ACM scraper is not running")
    
    return {
        "success": True,
        "message": "ACM scraper paused",
        "status": manager.get_acm_status()
    }


@router.post("/acm/resume", summary="ACM scraper'ı devam ettir")
async def resume_acm():
    """Duraklatılmış ACM scraper'ı devam ettir"""
    manager = get_scraper_manager()
    success = await manager.resume_acm()
    
    if not success:
        raise HTTPException(status_code=400, detail="ACM scraper is not paused")
    
    return {
        "success": True,
        "message": "ACM scraper resumed",
        "status": manager.get_acm_status()
    }

# ==================== All Scrapers ====================

class RoundRobinRequest(BaseModel):
    """Round Robin kontrol request"""
    headless: bool = Field(default=True, description="Headless mod")
    journals_per_switch: int = Field(default=3, ge=1, le=10, description="Kaç journal'da bir site değiştirilecek")


@router.post("/start-all", summary="Tüm scraper'ları başlat (paralel mod)")
async def start_all(request: ScraperControlRequest = None):
    """Tüm scraper'ları paralel modda başlat"""
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    
    results = await manager.start_all(headless=headless)
    
    return {
        "success": True,
        "message": "All scrapers started (parallel mode)",
        "mode": "parallel",
        "results": results,
        "status": manager.get_all_status()
    }


@router.post("/start-all-sequential", summary="Tüm scraper'ları sıralı başlat")
async def start_all_sequential(request: ScraperControlRequest = None):
    """Tüm scraper'ları sıralı modda başlat (IEEE bitince ScienceDirect başlar)"""
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    
    results = await manager.start_all_sequential(headless=headless)
    
    return {
        "success": True,
        "message": "All scrapers started (sequential mode)",
        "mode": "sequential",
        "results": results,
        "status": manager.get_all_status()
    }


@router.post("/start-all-round-robin", summary="Tüm scraper'ları round robin modda başlat")
async def start_all_round_robin(request: RoundRobinRequest = None):
    """
    Tüm scraper'ları round robin modda başlat.
    
    Her X journal'da bir site değiştirilir:
    IEEE → ScienceDirect → IEEE → ...
    
    - **headless**: Browser'ı görünmez modda çalıştır (default: True)
    - **journals_per_switch**: Kaç journal'da bir site değiştirilecek (default: 3)
    """
    manager = get_scraper_manager()
    
    headless = request.headless if request else True
    journals_per_switch = request.journals_per_switch if request else 3
    
    results = await manager.start_all_round_robin(
        headless=headless, 
        journals_per_switch=journals_per_switch
    )
    
    return {
        "success": True,
        "message": f"All scrapers started (round robin mode, switch every {journals_per_switch} journals)",
        "mode": "round_robin",
        "journals_per_switch": journals_per_switch,
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
    scraper_type: str = Query("all", description="Scraper tipi: all, ieee, sciencedirect, acm"),
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
