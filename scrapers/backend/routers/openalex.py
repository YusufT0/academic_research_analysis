from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.openalex.manual_scanner import openalex_manual_scanner

router = APIRouter(prefix="/openalex", tags=["OpenAlex"])

@router.get("/status", summary="OpenAlex tarama durumu")
async def get_openalex_status():
    """Mevcut manuel OpenAlex tarama durumunu getir"""
    return openalex_manual_scanner.get_status()

@router.post("/start", summary="OpenAlex taramasını başlat")
async def start_openalex_scan():
    """
    Veritabanındaki OpenAlex verisi eksik makale ve dergiler için 
    arka planda tarama işlemini başlatır.
    """
    success = openalex_manual_scanner.start_scan()
    if not success:
        raise HTTPException(status_code=400, detail="OpenAlex taraması zaten çalışıyor.")
    
    return {
        "success": True,
        "message": "OpenAlex taraması başlatıldı.",
        "status": openalex_manual_scanner.get_status()
    }

@router.post("/stop", summary="OpenAlex taramasını durdur")
async def stop_openalex_scan():
    """Çalışmakta olan OpenAlex taramasını durdurur"""
    success = openalex_manual_scanner.stop_scan()
    if not success:
        raise HTTPException(status_code=400, detail="OpenAlex taraması zaten çalışmıyor.")
    
    return {
        "success": True,
        "message": "OpenAlex taraması durduruluyor.",
        "status": openalex_manual_scanner.get_status()
    }
