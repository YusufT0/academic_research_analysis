"""
Journal URL Scraper Router

Belirli bir URL'den tekil journal scraping için endpointler.
URL validasyon, DB kontrol ve tek-journal scraping başlatmayı kapsar.
"""

import re
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..core.dependencies import get_scraper_manager
from utils.logger import get_logger

logger = get_logger("journal_scraper_router")

router = APIRouter(prefix="/scrapers/journal", tags=["Journal Scraper"])

# ==================== URL Validasyon Patterns ====================

# Her platform için kabul edilen URL regex'leri
_IEEE_PATTERNS = [
    re.compile(r"https?://ieeexplore\.ieee\.org/xpl/RecentIssue\.jsp\?punumber=\d+", re.IGNORECASE),
    re.compile(r"https?://ieeexplore\.ieee\.org/servlet/opac\?punumber=\d+", re.IGNORECASE),
    re.compile(r"https?://ieeexplore\.ieee\.org/xpl/aboutJournal\.jsp\?punumber=\d+", re.IGNORECASE),
]

_SCIENCEDIRECT_PATTERNS = [
    re.compile(r"https?://www\.sciencedirect\.com/journal/[a-zA-Z0-9\-]+", re.IGNORECASE),
    re.compile(r"https?://www\.sciencedirect\.com/journal/[a-zA-Z0-9\-]+/issues", re.IGNORECASE),
]

_ACM_PATTERNS = [
    re.compile(r"https?://dl\.acm\.org/journal/[a-zA-Z0-9\-]+", re.IGNORECASE),
    re.compile(r"https?://dl\.acm\.org/loi/[a-zA-Z0-9\-]+", re.IGNORECASE),
]

ScraperType = Literal["ieee", "sciencedirect", "acm"]


def _detect_scraper_type(url: str) -> Optional[ScraperType]:
    """URL'den hangi scraper platformu olduğunu tespit et."""
    for pattern in _IEEE_PATTERNS:
        if pattern.match(url):
            return "ieee"
    for pattern in _SCIENCEDIRECT_PATTERNS:
        if pattern.match(url):
            return "sciencedirect"
    for pattern in _ACM_PATTERNS:
        if pattern.match(url):
            return "acm"
    return None


def _is_valid_url(url: str) -> bool:
    """URL genel format kontrolü."""
    return url.startswith("http://") or url.startswith("https://")


# ==================== Schemas ====================

class ValidateUrlRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_must_be_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("URL boş olamaz")
        return v


class ValidateUrlResponse(BaseModel):
    valid: bool
    scraper_type: Optional[str]
    message: str


class StartSingleJournalRequest(BaseModel):
    url: str
    scraper_type: str
    max_articles: int = 50
    depth: int = 1
    headless: bool = True
    force: bool = False  # DB'de varsa bile zorla çalıştır

    @field_validator("url")
    @classmethod
    def url_must_be_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("URL boş olamaz")
        return v

    @field_validator("scraper_type")
    @classmethod
    def scraper_type_must_be_valid(cls, v: str) -> str:
        allowed = ("ieee", "sciencedirect", "acm")
        if v not in allowed:
            raise ValueError(f"scraper_type şunlardan biri olmalı: {allowed}")
        return v

    @field_validator("max_articles")
    @classmethod
    def max_articles_range(cls, v: int) -> int:
        if not (1 <= v <= 5000):
            raise ValueError("max_articles 1-5000 arasında olmalı")
        return v

    @field_validator("depth")
    @classmethod
    def depth_range(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("depth 1-50 arasında olmalı")
        return v


# ==================== Endpoints ====================

@router.post(
    "/validate",
    summary="Journal URL'sini doğrula",
    response_model=ValidateUrlResponse,
)
async def validate_journal_url(request: ValidateUrlRequest):
    """
    Verilen URL'nin ACM, ScienceDirect veya IEEE Xplore formatına uygun olup
    olmadığını doğrular ve hangi platforma ait olduğunu tespit eder.
    """
    url = request.url.strip()

    if not _is_valid_url(url):
        return ValidateUrlResponse(
            valid=False,
            scraper_type=None,
            message="Geçersiz URL formatı. HTTP veya HTTPS ile başlamalı.",
        )

    scraper_type = _detect_scraper_type(url)
    if scraper_type is None:
        return ValidateUrlResponse(
            valid=False,
            scraper_type=None,
            message=(
                "URL desteklenen bir platforma ait değil. "
                "ACM (dl.acm.org/journal/...), "
                "ScienceDirect (sciencedirect.com/journal/...) veya "
                "IEEE Xplore (ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=...) "
                "URL'si girin."
            ),
        )

    platform_labels = {
        "ieee": "IEEE Xplore",
        "sciencedirect": "ScienceDirect",
        "acm": "ACM Digital Library",
    }
    return ValidateUrlResponse(
        valid=True,
        scraper_type=scraper_type,
        message=f"Geçerli {platform_labels[scraper_type]} URL'si.",
    )


@router.get(
    "/check-exists",
    summary="URL'ye göre DB'de journal var mı?",
)
async def check_journal_exists(url: str = Query(..., description="Kontrol edilecek journal URL'si")):
    """
    Verilen URL'ye (veya normalize edilmiş hâline) göre veritabanında
    journal kaydı bulunup bulunmadığını kontrol eder.
    Bulunursa journal bilgilerini döner.

    Her platform farklı URL formatı kullanır:
      - ACM: DB'de relative path (/journal/tist), kullanıcı full URL girer
      - IEEE: DB'de full URL, punumber üzerinden ayrıca eşleşme denenir
      - ScienceDirect: DB'de full URL veya relative slug
    """
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL boş olamaz")

    try:
        from database.models import Journal

        # Tüm deneme URL'lerini topla
        candidates: list[str] = [url]

        # Trailing slash varyantı
        if url.endswith("/"):
            candidates.append(url.rstrip("/"))
        else:
            candidates.append(url + "/")

        # ── ACM: full URL → relative path dönüşümü ──────────────────────
        # DB: "/journal/tist"  Kullanıcı: "https://dl.acm.org/journal/tist"
        if "dl.acm.org" in url:
            m = re.search(r"dl\.acm\.org(/(?:journal|loi)/[a-zA-Z0-9\-]+)", url, re.IGNORECASE)
            if m:
                candidates.append(m.group(1))          # /journal/tist
                candidates.append(m.group(1) + "/")     # /journal/tist/

            # loi/ ve journal/ interchangeable olabilir
            if "/loi/" in url:
                slug = re.search(r"/loi/([a-zA-Z0-9\-]+)", url, re.IGNORECASE)
                if slug:
                    candidates.append(f"/journal/{slug.group(1)}")
            elif "/journal/" in url:
                slug = re.search(r"/journal/([a-zA-Z0-9\-]+)", url, re.IGNORECASE)
                if slug:
                    candidates.append(f"/loi/{slug.group(1)}")

        # ── IEEE: punumber bazlı regex eşleşmesi ────────────────────────
        ieee_punumber: str | None = None
        if "punumber=" in url.lower():
            m = re.search(r"punumber=(\d+)", url, re.IGNORECASE)
            if m:
                ieee_punumber = m.group(1)

        # ── ScienceDirect: slug bazlı normalizasyon ──────────────────────
        if "sciencedirect.com" in url:
            m = re.search(r"sciencedirect\.com/journal/([a-zA-Z0-9\-]+)", url, re.IGNORECASE)
            if m:
                slug = m.group(1)
                # DB'de bazen sadece slug veya full URL saklanabilir
                candidates.append(f"https://www.sciencedirect.com/journal/{slug}")
                candidates.append(f"https://www.sciencedirect.com/journal/{slug}/issues")

        # Dedup
        seen = set()
        unique_candidates = [c for c in candidates if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]

        # Birebir eşleşme — tüm candidate URL'leri dene
        journal = None
        for candidate in unique_candidates:
            journal = await Journal.find_one({"url": candidate})
            if journal:
                break

        # IEEE punumber bazlı regex sorgusu (DB'de farklı URL formatı varsa)
        if not journal and ieee_punumber:
            journal = await Journal.find_one(
                {"url": {"$regex": f"punumber={ieee_punumber}", "$options": "i"}}
            )

        if journal:
            return {
                "exists": True,
                "journal": {
                    "id": str(journal.id),
                    "name": journal.name,
                    "url": journal.url,
                    "source_website": journal.source_website,
                    "article_count": getattr(journal, 'article_count', 0) or 0,
                    "issue_count": getattr(journal, 'issue_count', 0) or 0,
                    "publisher": getattr(journal, 'publisher', None),
                    "issn": getattr(journal, 'issn', None),
                    "updated_at": journal.updated_at.isoformat() if journal.updated_at else None,
                    "created_at": journal.created_at.isoformat() if journal.created_at else None,
                },
            }

        return {"exists": False, "journal": None}

    except Exception as e:
        logger.error(f"Journal check-exists hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Veritabanı kontrolü başarısız: {str(e)}")



@router.post(
    "/start",
    summary="Tekil journal scraping başlat",
)
async def start_single_journal(request: StartSingleJournalRequest):
    """
    Belirtilen URL için tek bir journal'ı scrape eder.
    Mevcut scraper altyapısını (IEEE/ACM/SD) kullanarak
    1-elemanlı journal kuyruğuyla çalıştırır.
    """
    manager = get_scraper_manager()
    url = request.url.strip()

    # Backend URL validasyonu
    scraper_type = _detect_scraper_type(url)
    if scraper_type is None:
        raise HTTPException(
            status_code=400,
            detail="URL desteklenen bir platforma ait değil (IEEE, ScienceDirect veya ACM).",
        )

    if scraper_type != request.scraper_type:
        raise HTTPException(
            status_code=400,
            detail=(
                f"URL {scraper_type} platformuna ait, "
                f"ancak scraper_type olarak '{request.scraper_type}' belirtildi."
            ),
        )

    # İlgili scraper'ın çalışmadığını doğrula
    status_map = {
        "ieee": manager.ieee_progress,
        "sciencedirect": manager.sciencedirect_progress,
        "acm": manager.acm_progress,
    }
    progress = status_map[scraper_type]
    if progress.status.value in ("running", "starting", "paused", "stopping"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{scraper_type.upper()} scraper zaten çalışıyor. "
                "Lütfen önce mevcut işlemi durdurun veya tamamlanmasını bekleyin."
            ),
        )

    # Tek journal scraping başlat
    success = await manager.start_single_journal(
        url=url,
        scraper_type=scraper_type,
        max_articles=request.max_articles,
        depth=request.depth,
        headless=request.headless,
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Scraper başlatılamadı. Lütfen tekrar deneyin.",
        )

    return {
        "success": True,
        "message": f"{scraper_type.upper()} scraper tek journal modu başlatıldı",
        "url": url,
        "scraper_type": scraper_type,
    }


@router.get(
    "/status",
    summary="Tekil journal scraper durumu",
)
async def get_single_journal_status(scraper_type: str = Query("ieee")):
    """
    Belirtilen scraper'ın mevcut durumunu döner (tekil journal modu da dahil).
    """
    manager = get_scraper_manager()
    status_map = {
        "ieee": manager.get_ieee_status,
        "sciencedirect": manager.get_sciencedirect_status,
        "acm": manager.get_acm_status,
    }
    getter = status_map.get(scraper_type)
    if not getter:
        raise HTTPException(status_code=400, detail="Geçersiz scraper_type")
    return getter()


@router.post(
    "/stop",
    summary="Tekil journal scraping durdur",
)
async def stop_single_journal(scraper_type: str = Query(..., description="Durdurulacak scraper tipi: ieee, sciencedirect veya acm")):
    """Çalışmakta olan tekil journal scraping işlemini durdurur."""
    manager = get_scraper_manager()
    stop_map = {
        "ieee": manager.stop_ieee,
        "sciencedirect": manager.stop_sciencedirect,
        "acm": manager.stop_acm,
    }
    stopper = stop_map.get(scraper_type)
    if not stopper:
        raise HTTPException(status_code=400, detail="Geçersiz scraper_type")
    try:
        success = await stopper()
        return {"success": success}
    except Exception as e:
        logger.error(f"Stop single journal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
