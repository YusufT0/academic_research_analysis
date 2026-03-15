"""
Scraper Schemas
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ScraperType(str, Enum):
    """Scraper türleri"""
    IEEE = "ieee"
    SCIENCEDIRECT = "sciencedirect"
    ALL = "all"


class ScraperStatus(str, Enum):
    """Scraper durumları"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    COMPLETED = "completed"


class ScraperProgress(BaseModel):
    """Tek bir scraper'ın ilerleme durumu"""
    scraper_type: ScraperType
    status: ScraperStatus

    # İlerleme
    current_journal: Optional[str] = None
    current_journal_index: int = 0
    total_journals: int = 0
    pending_journals: List[str] = Field(default_factory=list)
    completed_journals: List[Dict[str, Any]] = Field(default_factory=list)
    article_list: List[str] = Field(default_factory=list)
    current_article: Optional[str] = None
    current_article_index: int = 0
    total_articles: int = 0

    # İstatistikler
    journals_scraped: int = 0
    issues_scraped: int = 0
    articles_scraped: int = 0
    articles_updated: int = 0
    errors_count: int = 0
    
    # Zaman bilgisi
    started_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    elapsed_seconds: float = 0
    
    # Yüzde
    progress_percent: float = Field(default=0.0, ge=0, le=100)
    
    # Hata mesajı (varsa)
    last_error: Optional[str] = None


class ScraperStateResponse(BaseModel):
    """Tüm scraper'ların durumu"""
    ieee: ScraperProgress
    sciencedirect: ScraperProgress
    
    # Genel durum
    any_running: bool = False
    all_completed: bool = False


class ScraperProgressResponse(BaseModel):
    """Scraper ilerleme response"""
    scraper_type: str
    progress: ScraperProgress


class ScraperControlRequest(BaseModel):
    """Scraper kontrol request"""
    scraper_type: ScraperType = Field(..., description="Hangi scraper")
    action: str = Field(..., description="İşlem: start, stop, pause, resume")
    
    # Opsiyonel parametreler
    headless: Optional[bool] = Field(None, description="Headless mod")
    max_articles: Optional[int] = Field(None, description="Maksimum makale sayısı")


class ScraperControlResponse(BaseModel):
    """Scraper kontrol response"""
    success: bool
    message: str
    scraper_type: str
    new_status: ScraperStatus


class ScraperStatsResponse(BaseModel):
    """Scraper istatistikleri"""
    # Toplam
    total_journals_scraped: int = 0
    total_issues_scraped: int = 0
    total_articles_scraped: int = 0
    
    # Kaynak bazlı
    ieee: Dict[str, Any] = Field(default_factory=dict)
    sciencedirect: Dict[str, Any] = Field(default_factory=dict)
    
    # Database durumu
    database_stats: Dict[str, Any] = Field(default_factory=dict)
    
    # Son güncelleme
    last_updated: Optional[datetime] = None


class ScraperLogEntry(BaseModel):
    """Scraper log entry"""
    timestamp: datetime
    level: str  # info, warning, error, success
    scraper_type: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ScraperLogsResponse(BaseModel):
    """Scraper logs response"""
    logs: List[ScraperLogEntry]
    total: int
