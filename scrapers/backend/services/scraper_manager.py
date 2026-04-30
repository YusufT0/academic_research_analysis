"""
Scraper Manager Service

IEEE ve ScienceDirect scraper'larını yönetir.
Background task olarak çalıştırır, durum takibi yapar.

Scraper'lar ayrı thread'lerde çalışır - Selenium senkron kod içerdiğinden
asyncio event loop'unu bloklamaz.

Öncelik Sistemi:
- Veritabanında bulunmayan dergiler öncelikli olarak işlenir
- Tüm dergiler veritabanındaysa, last_scraped_at tarihine göre en eski öncelikli
"""

import asyncio
import concurrent.futures
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import sys
from pathlib import Path

# Path'leri ayarla
scrapers_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(scrapers_path))

from database import init_database_service, close_database, DatabaseService
from database.repositories import JournalRepository
from utils.logger import get_logger
from backend.core.distributed_lock import DistributedScraperLock
from backend.core.config import settings

logger = get_logger('scraper_manager')

# Scraper module references (lazy or eager based on SCRAPER_LAZY_LOAD)
IEEEXploreScraper = None
ScienceDirectScraper = None
ACMScraper = None
ScraperStoppedException = Exception  # Fallback

_scraper_modules_loaded = False


def _load_scraper_modules():
    """Scraper modüllerini yükle (thread başlamadan önce çağrılmalı)"""
    global IEEEXploreScraper, ScienceDirectScraper, ACMScraper, ScraperStoppedException, _scraper_modules_loaded
    if _scraper_modules_loaded:
        return
    logger.info("Scraper modülleri yükleniyor...")
    try:
        from ieee_xplore.scraper import IEEEXploreScraper as _IEEE, ScraperStoppedException as IEEEScraperStoppedException
        from science_direct.scraper import ScienceDirectScraper as _SD, ScraperStoppedException as SDScraperStoppedException
        from acm.scraper import ACMScraper as _ACM, ScraperStoppedException as ACMScraperStoppedException
        IEEEXploreScraper = _IEEE
        ScienceDirectScraper = _SD
        ACMScraper = _ACM
        ScraperStoppedException = (IEEEScraperStoppedException, SDScraperStoppedException, ACMScraperStoppedException)
        logger.success("Scraper modülleri yüklendi")
    except Exception as e:
        logger.error(f"Scraper modülleri yüklenemedi: {e}")
    _scraper_modules_loaded = True


# SCRAPER_LAZY_LOAD=false ise modülleri hemen yükle (eski davranış)
if not settings.scraper_lazy_load:
    _load_scraper_modules()


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


class ScraperProgress:
    """Scraper ilerleme durumu"""
    
    def __init__(self, scraper_type: str):
        self.scraper_type = scraper_type
        self._status = ScraperStatus.IDLE
        
        # İlerleme
        self.current_journal: Optional[str] = None
        self.current_journal_index: int = 0
        self.total_journals: int = 0
        self.pending_journals: List[str] = []   # Kalan tüm dergiler
        self.completed_journals: List[Dict[str, Any]] = []  # [{name, articles_count}]

        # Issue ilerleme
        self.current_issue: Optional[str] = None
        self.current_issue_index: int = 0
        self.total_issues: int = 0
        self.completed_issues: List[Dict[str, Any]] = []  # [{title, articles_count, article_list}]
        self.pending_issues: List[str] = []  # Henüz işlenmemiş issue başlıkları

        # Makale ilerleme
        self.article_list: List[str] = []           # Mevcut issue'nun makale başlıkları (ön bilgi)
        self.current_article: Optional[str] = None
        self.current_article_index: int = 0
        self.total_articles: int = 0

        # İstatistikler
        self.journals_scraped: int = 0
        self.issues_scraped: int = 0
        self.articles_scraped: int = 0
        self.articles_updated: int = 0
        self.errors_count: int = 0
        
        # Zaman
        self.started_at: Optional[datetime] = None
        self.last_activity: Optional[datetime] = None
        
        # Hata
        self.last_error: Optional[str] = None
        
        # Logs
        self.logs: List[Dict[str, Any]] = []

        # Tekil journal modu flag'i
        # True olduğunda bu scraper, URL aracılığıyla tek bir journal
        # işlemek için başlatılmış demektir. Frontend bunu kullanarak
        # ana scraper kartını "meşgul" olarak göstermez.
        self.is_single_journal_mode: bool = False
        self.single_journal_url: Optional[str] = None
        self.single_journal_max_articles: Optional[int] = None
        self.single_journal_depth: Optional[int] = None
        
    @property
    def status(self) -> ScraperStatus:
        return self._status
        
    @status.setter
    def status(self, new_status: ScraperStatus):
        if hasattr(self, '_status') and self._status == new_status:
            return
            
        old_status = getattr(self, '_status', None)
        self._status = new_status
        
        # Prometheus Gauge update
        try:
            from backend.core.metrics import ACTIVE_SCRAPERS
            if new_status == ScraperStatus.RUNNING and old_status != ScraperStatus.RUNNING:
                ACTIVE_SCRAPERS.inc()
            elif old_status == ScraperStatus.RUNNING and new_status != ScraperStatus.RUNNING:
                ACTIVE_SCRAPERS.dec()
        except Exception:
            pass
        
        # Canlı websocket bildirimi
        try:
            # Geç import ile circular dependency önle
            from backend.routers.websocket import emit_scraper_event
            emit_scraper_event(
                event_type="status_update",
                scraper_type=self.scraper_type,
                data=self.to_dict()
            )
        except Exception:
            pass
            
    @property
    def progress_percent(self) -> float:
        """İlerleme yüzdesi"""
        if self.total_journals == 0:
            return 0.0
        return min(100.0, (self.current_journal_index / self.total_journals) * 100)
    
    @property
    def elapsed_seconds(self) -> float:
        """Geçen süre (saniye)"""
        if not self.started_at:
            return 0.0
        return (datetime.utcnow() - self.started_at).total_seconds()
    
    def add_log(self, level: str, message: str, details: Optional[Dict] = None):
        """Log ekle"""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "details": details
        }
        self.logs.append(entry)
        # Son 1000 log'u tut
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]
        
        # WebSocket üzerinden log event'i yayınla
        try:
            from backend.routers.websocket import emit_scraper_event
            emit_scraper_event(
                event_type="log",
                scraper_type=self.scraper_type,
                data={
                    "level": level,
                    "message": message,
                    "details": details,
                }
            )
        except Exception:
            pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e çevir"""
        return {
            "scraper_type": self.scraper_type,
            "status": self.status.value,
            "current_journal": self.current_journal,
            "current_journal_index": self.current_journal_index,
            "total_journals": self.total_journals,
            "pending_journals": self.pending_journals,
            "completed_journals": self.completed_journals,
            "current_issue": self.current_issue,
            "current_issue_index": self.current_issue_index,
            "total_issues": self.total_issues,
            "completed_issues": self.completed_issues,
            "pending_issues": self.pending_issues,
            "article_list": self.article_list,
            "current_article": self.current_article,
            "current_article_index": self.current_article_index,
            "total_articles": self.total_articles,
            "journals_scraped": self.journals_scraped,
            "issues_scraped": self.issues_scraped,
            "articles_scraped": self.articles_scraped,
            "articles_updated": self.articles_updated,
            "errors_count": self.errors_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "elapsed_seconds": self.elapsed_seconds,
            "progress_percent": self.progress_percent,
            "last_error": self.last_error,
            "is_single_journal_mode": self.is_single_journal_mode,
            "single_journal_url": self.single_journal_url,
            "single_journal_max_articles": self.single_journal_max_articles,
            "single_journal_depth": self.single_journal_depth,
        }
    
    def reset(self):
        """Durumu sıfırla"""
        self.status = ScraperStatus.IDLE
        self.current_journal = None
        self.current_journal_index = 0
        self.pending_journals = []
        self.completed_journals = []
        self.current_issue = None
        self.current_issue_index = 0
        self.total_issues = 0
        self.completed_issues = []
        self.pending_issues = []
        self.article_list = []
        self.current_article = None
        self.current_article_index = 0
        self.total_articles = 0
        self.total_journals = 0
        self.journals_scraped = 0
        self.issues_scraped = 0
        self.articles_scraped = 0
        self.articles_updated = 0
        self.errors_count = 0
        self.started_at = None
        self.last_activity = None
        self.last_error = None
        self.logs = []
        self.single_journal_url = None
        self.single_journal_max_articles = None
        self.single_journal_depth = None
        # Not: is_single_journal_mode burada sıfırlanmaz —
        # thread fonksiyonu override varlığına göre bunu yönetir.
        
    def __setattr__(self, name, value):
        # Önceki değeri al (sadece metrik artışlarını hesaplamak için)
        old_value = getattr(self, name, 0) if isinstance(value, int) else None
        
        super().__setattr__(name, value)
        
        # Sadece sayısal değerler (makale, hata) büyüyorsa Prometheus'a fırlat
        if old_value is not None and value > old_value:
            try:
                from backend.core.metrics import ARTICLES_SCRAPED, SCRAPER_ERRORS
                inc_amount = value - old_value
                if name == 'articles_scraped':
                    ARTICLES_SCRAPED.labels(source=self.scraper_type).inc(inc_amount)
                elif name == 'errors_count':
                    SCRAPER_ERRORS.labels(source=self.scraper_type, error_type="scraper_error").inc(inc_amount)
            except Exception:
                pass
        
        # Track UI-facing changes to keep frontend state in sync (queue + progress)
        if name in (
            'current_journal',
            'current_journal_index',
            'current_issue',
            'current_issue_index',
            'total_issues',
            'completed_issues',
            'pending_issues',
            'article_list',
            'current_article',
            'current_article_index',
            'total_articles',
            'journals_scraped',
            'issues_scraped',
            'articles_scraped',
            'articles_updated',
            'errors_count',
        ):
            # Sadece koşuyorken ilerlemeyi fırlat (başlangıçtaki resetleri yoksaymak için)
            if getattr(self, '_status', None) == ScraperStatus.RUNNING:
                try:
                    from backend.routers.websocket import emit_scraper_event
                    emit_scraper_event(
                        event_type="progress",
                        scraper_type=self.scraper_type,
                        data=self.to_dict()
                    )
                except Exception:
                    pass

class ScraperManager:
    """
    Scraper Manager
    
    Tüm scraper'ları merkezi olarak yönetir.
    Scraper'lar ayrı thread'lerde çalışır ve backend'i bloklamaz.
    """
    
    def __init__(self):
        # Progress tracking
        self.ieee_progress = ScraperProgress("ieee")
        self.sciencedirect_progress = ScraperProgress("sciencedirect")
        self.acm_progress = ScraperProgress("acm")
        
        # Thread executor - scraper'lar için ayrı thread pool
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="scraper")
        
        # Futures
        self._ieee_future: Optional[concurrent.futures.Future] = None
        self._sciencedirect_future: Optional[concurrent.futures.Future] = None
        self._acm_future: Optional[concurrent.futures.Future] = None
        
        # Stop flags (thread-safe)
        self._ieee_stop_flag = threading.Event()
        self._sciencedirect_stop_flag = threading.Event()
        self._acm_stop_flag = threading.Event()

        # Pause flags (thread-safe)
        self._ieee_pause_flag = threading.Event()
        self._sciencedirect_pause_flag = threading.Event()
        self._acm_pause_flag = threading.Event()

        # Live scraper references — set by threads, used for force-close on stop
        self._ieee_scraper = None
        self._sciencedirect_scraper = None
        self._acm_scraper = None
        
        # Database service
        self._db_service: Optional[DatabaseService] = None
        
        # Event loop reference for async database calls from threads
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Settings — env vars'dan oku (varsa), yoksa default
        try:
            from backend.core.config import settings as _settings
            self.ieee_headless = _settings.scraper_headless
            self.ieee_max_articles = _settings.ieee_max_articles
            self.ieee_depth = _settings.ieee_depth
            self.sciencedirect_headless = _settings.scraper_headless
            self.sciencedirect_max_articles = _settings.sciencedirect_max_articles
            self.sciencedirect_depth = 1  # ScienceDirect depth is set per start_sciencedirect call
            self.acm_headless = _settings.scraper_headless
            self.acm_max_articles = _settings.acm_max_articles
            self.acm_depth = 1
        except Exception:
            self.ieee_headless = True
            self.ieee_max_articles = 100
            self.ieee_depth = 1
            self.sciencedirect_headless = True
            self.sciencedirect_max_articles = 100
            self.sciencedirect_depth = 1
            self.acm_headless = True
            self.acm_max_articles = 100
            self.acm_depth = 1

        # Issue işleme sırası: "newest_first" (yeniden eskiye) veya "oldest_first" (eskiden yeniye)
        # Varsayılan: yeniden eskiye (newest_first)
        self.ieee_issues_order: str = "newest_first"
        self.sciencedirect_issues_order: str = "newest_first"
        self.acm_issues_order: str = "newest_first"

        # Sürekli mod: tamamlandıktan sonra otomatik yeniden başlat
        self.ieee_continuous: bool = False
        self.sciencedirect_continuous: bool = False
        self.acm_continuous: bool = False
        
        # Round Robin Settings
        self.round_robin_journals_per_switch = 3
        
        # Round Robin State
        self._round_robin_future: Optional[concurrent.futures.Future] = None
        self._round_robin_stop_flag = threading.Event()

        # Tekil journal restore context'i (refresh sonrası frontend'in aktif işi bulabilmesi için)
        self._ieee_single_journal_context: Optional[Dict[str, Any]] = None
        self._sd_single_journal_context: Optional[Dict[str, Any]] = None
        self._acm_single_journal_context: Optional[Dict[str, Any]] = None
    
    async def initialize(self):
        """Manager'ı initialize et"""
        try:
            self._db_service = await init_database_service()
            self._loop = asyncio.get_running_loop()
            logger.success("ScraperManager initialized")
            return True
        except Exception as e:
            logger.error(f"ScraperManager initialization failed: {e}")
            return False
    
    async def close(self):
        """Temizlik"""
        await self.stop_all()
        self._executor.shutdown(wait=False)
        await close_database()
        logger.info("ScraperManager closed")
    
    # ==================== Status Methods ====================
    
    def get_ieee_status(self) -> Dict[str, Any]:
        """IEEE scraper durumu"""
        return self.ieee_progress.to_dict()
    
    def get_sciencedirect_status(self) -> Dict[str, Any]:
        """ScienceDirect scraper durumu"""
        return self.sciencedirect_progress.to_dict()
        
    def get_acm_status(self) -> Dict[str, Any]:
        """ACM scraper durumu"""
        return self.acm_progress.to_dict()
    
    def get_all_status(self) -> Dict[str, Any]:
        """Tüm scraper'ların durumu"""
        ieee = self.get_ieee_status()
        sd = self.get_sciencedirect_status()
        acm = self.get_acm_status()
        
        any_running = (
            self.ieee_progress.status == ScraperStatus.RUNNING or
            self.sciencedirect_progress.status == ScraperStatus.RUNNING or
            self.acm_progress.status == ScraperStatus.RUNNING
        )
        
        all_completed = (
            self.ieee_progress.status == ScraperStatus.COMPLETED and
            self.sciencedirect_progress.status == ScraperStatus.COMPLETED and
            self.acm_progress.status == ScraperStatus.COMPLETED
        )
        
        return {
            "ieee": ieee,
            "sciencedirect": sd,
            "acm": acm,
            "any_running": any_running,
            "all_completed": all_completed,
        }
    
    def get_logs(self, scraper_type: str = "all", limit: int = 50) -> List[Dict]:
        """Logları getir"""
        logs = []
        
        if scraper_type in ["all", "ieee"]:
            for log in self.ieee_progress.logs:
                log["scraper_type"] = "ieee"
                logs.append(log)
        
        if scraper_type in ["all", "sciencedirect"]:
            for log in self.sciencedirect_progress.logs:
                log["scraper_type"] = "sciencedirect"
                logs.append(log)
                
        if scraper_type in ["all", "acm"]:
            for log in self.acm_progress.logs:
                log["scraper_type"] = "acm"
                logs.append(log)
        
        # Timestamp'e göre sırala
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

        return logs[:limit] if limit else logs
    
    # ==================== Single Journal Scraper ====================

    async def start_single_journal(
        self,
        url: str,
        scraper_type: str,
        max_articles: int = 50,
        depth: int = 1,
        headless: bool = True,
    ) -> bool:
        """
        Tek bir journal URL'sini scrape eder.

        Mevcut IEEE/ScienceDirect/ACM scraper altyapısını kullanır —
        journal listesi olarak yalnızca verilen URL'yi temsil eden
        1 elemanlı bir liste oluşturur, ardından ilgili scraper'ı başlatır.
        Böylece mevcut progress tracking, WebSocket events ve
        JournalQueue UI'ı değiştirilmeden çalışır.
        """
        url = url.strip()

        progress_map = {
            "ieee": self.ieee_progress,
            "sciencedirect": self.sciencedirect_progress,
            "acm": self.acm_progress,
        }
        progress = progress_map.get(scraper_type)
        if progress is not None:
            progress.single_journal_url = url
            progress.single_journal_max_articles = max_articles
            progress.single_journal_depth = depth

        # Platforma göre tek-elemanlı journal dicts oluştur
        if scraper_type == "ieee":
            # IEEE'de journal dict: {name, url, punumber}
            import re as _re
            m = _re.search(r"punumber=(\d+)", url, _re.IGNORECASE)
            punumber = m.group(1) if m else "unknown"
            single_journal_list = [{
                "name": f"Journal (punumber={punumber})",
                "url": url,
                "punumber": punumber,
                "open_access": False,
                "aims_and_scope": None,
                "resolve_name_from_url": True,
            }]
            self._ieee_single_journal_override = single_journal_list
            self._ieee_single_journal_context = {
                "url": url,
                "max_articles": max_articles,
                "depth": depth,
            }
            return await self.start_ieee(
                headless=headless,
                max_articles=max_articles,
                depth=depth,
            )

        elif scraper_type == "sciencedirect":
            import re as _re
            m = _re.search(r"/journal/([a-zA-Z0-9\-]+)", url, _re.IGNORECASE)
            journal_slug = m.group(1) if m else "unknown"
            single_journal_list = [{
                "name": f"Journal ({journal_slug})",
                "url": url,
                "slug": journal_slug,
                "open_access": False,
                "resolve_name_from_url": True,
            }]
            self._sd_single_journal_override = single_journal_list
            self._sd_single_journal_context = {
                "url": url,
                "max_articles": max_articles,
                "depth": depth,
            }
            return await self.start_sciencedirect(
                headless=headless,
                max_articles=max_articles,
                depth=depth,
            )

        elif scraper_type == "acm":
            import re as _re
            m = _re.search(r"/(journal|loi)/([a-zA-Z0-9\-]+)", url, _re.IGNORECASE)
            acm_id = m.group(2) if m else "unknown"
            single_journal_list = [{
                "name": f"Journal ({acm_id})",
                "url": f"/journal/{acm_id}",   # ACM DB'de relative path saklıyor
                "code": acm_id,                 # ACM scraper.scrape_journal_articles bunu bekliyor
                "open_access": False,
                "resolve_name_from_url": True,
            }]
            self._acm_single_journal_override = single_journal_list
            self._acm_single_journal_context = {
                "url": url,
                "max_articles": max_articles,
                "depth": depth,
            }
            return await self.start_acm(
                headless=headless,
                max_articles=max_articles,
                depth=depth,
            )

        return False


    # ==================== IEEE Scraper ====================
    
    async def start_ieee(self, headless: bool = True, max_articles: int = 100, depth: int = 1, issues_order: str = "newest_first", continuous: bool = False) -> bool:
        """IEEE scraper'ı başlat (ayrı thread'de)"""
        if self.ieee_progress.status == ScraperStatus.RUNNING:
            logger.warning("IEEE scraper already running")
            return False

        # Distributed lock — başka bir instance zaten çalıştırıyorsa engelle
        if not await DistributedScraperLock.acquire("ieee"):
            logger.warning("IEEE scraper distributed lock alınamadı — başka bir instance çalıştırıyor")
            return False

        self.ieee_headless = headless
        self.ieee_max_articles = max_articles
        self.ieee_depth = depth
        self.ieee_issues_order = issues_order
        self.ieee_continuous = continuous

        # Reset flags
        self._ieee_stop_flag.clear()
        self._ieee_pause_flag.clear()

        # Thread'de başlat - event loop'u bloklamaz
        self._ieee_future = self._executor.submit(self._run_ieee_scraper_sync)
        logger.info(f"IEEE scraper thread'de başlatıldı (issues_order={issues_order})")

        return True
    
    def _run_ieee_scraper_sync(self):
        """
        IEEE scraper'ı senkron olarak çalıştır (ayrı thread'de).
        Bu metod thread pool'da çalışır ve main event loop'u bloklamaz.
        """
        progress = self.ieee_progress
        progress.reset()
        # Tekil journal modu kontrolü — override set edilmişse flag'ı koru
        progress.is_single_journal_mode = bool(getattr(self, '_ieee_single_journal_override', None))
        if progress.is_single_journal_mode and self._ieee_single_journal_context:
            progress.single_journal_url = self._ieee_single_journal_context.get("url")
            progress.single_journal_max_articles = self._ieee_single_journal_context.get("max_articles")
            progress.single_journal_depth = self._ieee_single_journal_context.get("depth")
        progress.status = ScraperStatus.STARTING
        progress.started_at = datetime.utcnow()
        progress.add_log("info", "IEEE scraper başlatılıyor (ayrı thread)...")
        logger.info("[IEEE Thread] Scraper başlatılıyor...")
        logger.info(f"[IEEE Thread] Headless: {self.ieee_headless}")
        print(f"[IEEE Thread] Başlatılıyor, headless={self.ieee_headless}", flush=True)
        
        scraper = None
        nlp_futures: List[concurrent.futures.Future] = []
        
        try:
            _load_scraper_modules()
            if IEEEXploreScraper is None:
                raise Exception("IEEE scraper modülü yüklenemedi")

            # Create and initialize
            logger.info("[IEEE Thread] Browser başlatılıyor...")
            print("[IEEE Thread] Browser başlatılıyor...", flush=True)
            scraper = IEEEXploreScraper(headless=self.ieee_headless, stop_flag=self._ieee_stop_flag, pause_flag=self._ieee_pause_flag)
            self._ieee_scraper = scraper
            print("[IEEE Thread] Scraper oluşturuldu, initialize ediliyor...", flush=True)
            scraper.initialize()
            print("[IEEE Thread] Browser başlatıldı!", flush=True)
            
            progress.status = ScraperStatus.RUNNING
            progress.add_log("info", "Browser başlatıldı")
            logger.success("[IEEE Thread] Browser başlatıldı")
            
            # ── Tekil journal override kontrolü ──────────────────────────
            _single_override = getattr(self, '_ieee_single_journal_override', None)
            if _single_override:
                self._ieee_single_journal_override = None  # tüket — bir kere kullan
                all_journals = _single_override
                progress.total_journals = len(all_journals)
                progress.add_log("info", f"Tekil journal modu — URL: {all_journals[0].get('url', '')}")
                logger.info(f"[IEEE Thread] Tekil journal modu: {all_journals[0].get('url', '')}")
            else:
                # Navigate to journals page
                logger.info("[IEEE Thread] Journals sayfasına gidiliyor...")
                success = scraper.navigate_to_journals()
                if not success:
                    raise Exception("Journals sayfasına gidilemedi")

                progress.add_log("success", "Journals sayfasına gidildi")
                logger.success("[IEEE Thread] Journals sayfasına gidildi")

                # Get all journals
                logger.info("[IEEE Thread] Journal listesi alınıyor...")
                all_journals = scraper.scrape_all_journals()
                progress.total_journals = len(all_journals)
                progress.add_log("info", f"{len(all_journals)} journal bulundu")
                logger.info(f"[IEEE Thread] {len(all_journals)} journal bulundu")

                # ============================================================
                # ÖNCELİK SİSTEMİ - JOURNAL SIRALAMA
                # ============================================================
                logger.info("[IEEE Thread] Öncelik sistemi: Veri tabanı kontrolü yapılıyor...")
                progress.add_log("info", "Öncelik sistemi: Veri tabanı kontrolü yapılıyor...")

                # Journal repository'yi başlat ve öncelik bilgilerini al (async call from thread)
                journal_names = [j.get('name', '') for j in all_journals]

                # Async call from thread
                journal_repo = JournalRepository()
                future = asyncio.run_coroutine_threadsafe(
                    journal_repo.get_bulk_priority_info(journal_names, 'ieeexplore'),
                    self._loop
                )
                priority_info = future.result(timeout=30)

                # İstatistikleri hesapla
                new_count = sum(1 for info in priority_info.values() if not info['exists'])
                existing_count = len(priority_info) - new_count

                logger.info(f"[IEEE Thread] Öncelik: {new_count} yeni, {existing_count} mevcut dergi")
                progress.add_log("info", f"Öncelik: {new_count} yeni, {existing_count} mevcut dergi")

                # Journal'ları öncelik sistemine göre sırala
                all_journals = JournalRepository.prioritize_journals(all_journals, priority_info)

                logger.success("[IEEE Thread] Journal'lar öncelik sırasına göre sıralandı!")
                progress.add_log("success", "Journal'lar öncelik sırasına göre sıralandı (Yeni dergiler önce, sonra en eski scrape edilenler)")

                # İlk 5 journal'ı logla
                for i, j in enumerate(all_journals[:5], 1):
                    info = priority_info.get(j.get('name', ''), {})
                    status = "🆕 YENİ" if not info.get('exists') else f"📅 Son: {info.get('last_scraped_at', 'Bilinmiyor')}"
                    logger.info(f"[IEEE Thread]   {i}. {j.get('name', 'Unknown')} - {status}")
            
            # Scrape each journal
            for idx, journal in enumerate(all_journals):
                # Stop check
                if self._ieee_stop_flag.is_set():
                    progress.status = ScraperStatus.STOPPED
                    progress.add_log("warning", "Scraper durduruldu")
                    logger.warning("[IEEE Thread] Scraper durduruldu")
                    break
                
                # Pause check — scraper'ın _interruptible_sleep'i de pause'u yakalar;
                # burada sadece status güncellemesi yapılır
                if self._ieee_pause_flag.is_set():
                    progress.status = ScraperStatus.PAUSED
                    while self._ieee_pause_flag.is_set():
                        import time as _t; _t.sleep(0.3)
                    progress.status = ScraperStatus.RUNNING
                
                journal_name = journal.get('name', 'Unknown')
                progress.current_journal = journal_name
                progress.current_journal_index = idx + 1
                progress.pending_journals = [j.get('name', '') for j in all_journals[idx + 1:]]
                progress.current_issue = None
                progress.current_issue_index = 0
                progress.total_issues = 0
                progress.completed_issues = []
                progress.article_list = []
                progress.current_article = None
                progress.current_article_index = 0
                progress.total_articles = 0
                progress.last_activity = datetime.utcnow()

                logger.info(f"[IEEE Thread] [{idx+1}/{len(all_journals)}] {journal_name} işleniyor...")

                def _ieee_article_list_cb(titles: List[str]):
                    progress.article_list = titles

                def _ieee_article_cb(art_idx: int, art_total: int, art_title: Optional[str]):
                    progress.total_articles = art_total
                    progress.current_article = art_title or f"Makale {art_idx}/{art_total}"
                    progress.current_article_index = art_idx

                def _ieee_issue_start_cb(issue_idx: int, total_issues: int, issue_title: str, pending_titles: list = None):
                    progress.total_issues = total_issues
                    progress.current_issue = issue_title or f"Issue {issue_idx}"
                    progress.current_issue_index = issue_idx
                    progress.pending_issues = pending_titles or []
                    progress.article_list = []
                    progress.current_article = None
                    progress.current_article_index = 0
                    progress.total_articles = 0

                def _ieee_issue_complete_cb(issue_idx: int, articles_count: int, article_titles: List[str]):
                    title = progress.current_issue or f"Issue {issue_idx}"
                    new_issues = progress.completed_issues + [{
                        'title': title,
                        'articles_count': articles_count,
                        'article_list': article_titles[:30],
                    }]
                    progress.completed_issues = new_issues
                    # Son tamamlanan issue'nun "aktif" satırda tekrar görünmesini engelle
                    progress.current_issue = None
                    progress.pending_issues = []
                    progress.article_list = []
                    progress.current_article = None
                    progress.current_article_index = 0
                    progress.total_articles = 0

                def _ieee_journal_name_cb(resolved_name: str):
                    progress.current_journal = resolved_name

                try:
                    import time
                    scrape_start_t = time.time()

                    # DB'deki mevcut issue URL'lerini al (depth sayımı için)
                    existing_issue_urls: set = set()
                    if self._db_service and self._loop:
                        async def _get_ieee_existing_issue_urls():
                            journal_doc = await self._db_service.get_journal(
                                journal.get('name', ''), 'ieeexplore'
                            )
                            if not journal_doc:
                                return set()
                            from database import Issue
                            issues = await Issue.find_by_journal(journal_doc.id)
                            result = set()
                            for iss in issues:
                                if iss.url:
                                    url = iss.url.replace('https://ieeexplore.ieee.org', '')
                                    result.add(url)
                            return result
                        try:
                            fut = asyncio.run_coroutine_threadsafe(
                                _get_ieee_existing_issue_urls(), self._loop
                            )
                            existing_issue_urls = fut.result(timeout=15)
                            if existing_issue_urls:
                                logger.info(
                                    f"[IEEE Thread] {journal_name}: "
                                    f"{len(existing_issue_urls)} mevcut issue URL'si bulundu, atlanacak"
                                )
                        except Exception as e:
                            logger.warning(f"[IEEE Thread] Mevcut issue URL'leri alınamadı: {e}")

                    # Scrape issues + articles
                    issue_results = scraper.scrape_journal_articles(
                        journal,
                        depth=self.ieee_depth,
                        max_articles=self.ieee_max_articles,
                        article_progress_callback=_ieee_article_cb,
                        article_list_callback=_ieee_article_list_cb,
                        journal_name_callback=_ieee_journal_name_cb,
                        existing_issue_urls=existing_issue_urls,
                        issue_start_callback=_ieee_issue_start_cb,
                        issue_complete_callback=_ieee_issue_complete_cb,
                        issues_order=self.ieee_issues_order,
                    )

                    if self._ieee_stop_flag.is_set():
                        progress.status = ScraperStatus.STOPPED
                        progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
                        logger.warning("[IEEE Thread] Stop sinyali sonrası journal kaydı atlandı")
                        break

                    resolved_journal_name = journal.get('name', journal_name)
                    if resolved_journal_name != journal_name:
                        journal_name = resolved_journal_name
                        progress.current_journal = resolved_journal_name

                    try:
                        from backend.core.metrics import SCRAPER_DURATION
                        SCRAPER_DURATION.labels(source="ieee").observe(time.time() - scrape_start_t)
                    except ImportError:
                        pass

                    # Makale olsun olmasın journal'ı veritabanına kaydet
                    if self._db_service and self._loop:
                        journal_info = {
                            'name': journal.get('name'),
                            'url': journal.get('url'),
                            'publisher': 'IEEE',
                            'open_access': journal.get('open_access', False),
                            'aims_and_scope': journal.get('aims_and_scope'),
                        }

                        async def _save_ieee_journal_issues():
                            journal_doc, _ = await self._db_service.add_journal(
                                source_website='ieeexplore', **journal_info
                            )
                            total_created = 0
                            total_updated = 0
                            issues_created = 0
                            for res in issue_results:
                                i_data = res['issue_info']
                                issue_doc, issue_created = await self._db_service.add_issue(
                                    journal=journal_doc,
                                    issue_number=i_data.get('issue_number'),
                                    date=i_data.get('date'),
                                    url=i_data.get('url'),
                                )
                                created, updated = await self._db_service.add_articles_bulk(
                                    issue_doc, res['articles']
                                )
                                total_created += created
                                total_updated += updated
                                if issue_created:
                                    issues_created += 1
                            await self._db_service.recalculate_journal_counts(journal_doc.id)
                            return total_created, total_updated, issues_created

                        # Run async database call from thread
                        future = asyncio.run_coroutine_threadsafe(
                            _save_ieee_journal_issues(), self._loop
                        )
                        articles_created, articles_updated, issues_created = future.result(timeout=60)

                        progress.completed_journals.append({
                            'name': journal_name,
                            'articles_count': articles_created,
                            'issues': progress.completed_issues.copy(),
                        })
                        progress.journals_scraped += 1
                        progress.issues_scraped += issues_created
                        progress.articles_scraped += articles_created
                        progress.articles_updated += articles_updated

                        if issue_results:
                            progress.add_log("success", f"{journal.get('name')}: {articles_created} makale eklendi")
                            logger.success(f"[IEEE Thread] {journal_name}: {articles_created} makale eklendi")
                        else:
                            progress.add_log("info", f"{journal.get('name')}: Makale yok, journal kaydedildi")
                            logger.info(f"[IEEE Thread] {journal_name}: Makale yok, journal kaydedildi")

                        if articles_created > 0 and self._loop and not progress.is_single_journal_mode:
                            async def _ieee_journal_cluster_update():
                                try:
                                    from backend.services.nlp_service import NLPService
                                    result = await NLPService().assign_new_articles(min_abstract_length=50)
                                    logger.success(f"[IEEE Thread] Incremental clustering tamamland\u0131: {result}")
                                except FileNotFoundError:
                                    logger.info("[IEEE Thread] NLP modeli bulunamad\u0131, incremental clustering atland\u0131")
                                except Exception as _e:
                                    logger.warning(f"[IEEE Thread] Incremental clustering hatas\u0131: {_e}")
                            nlp_future = asyncio.run_coroutine_threadsafe(
                                _ieee_journal_cluster_update(), self._loop
                            )
                            nlp_futures.append(nlp_future)
                        elif articles_created > 0 and progress.is_single_journal_mode:
                            progress.add_log("info", "Tekil URL modu: incremental NLP scraping aşamasında atlandı, analyzing aşamasında çalışacak")
                    
                except ScraperStoppedException:
                    # Stop sinyali alındı - döngüden çık
                    progress.status = ScraperStatus.STOPPED
                    progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
                    logger.warning(f"[IEEE Thread] Scraper durduruldu (makale işlemi sırasında)")
                    break
                except Exception as e:
                    progress.errors_count += 1
                    progress.last_error = str(e)
                    progress.add_log("error", f"{journal.get('name')}: {str(e)}")
                    logger.error(f"[IEEE Thread] {journal_name} hatası: {str(e)}")
                
                # Rate limiting
                import time
                time.sleep(2)
            
            if progress.status == ScraperStatus.RUNNING and nlp_futures:
                # Scraping döngüsü bitti; artık arka plan NLP işleri bekleniyor.
                # UI'da stale "Dergi Kuyruğu" görünmemesi için aktif/pending alanları temizle.
                progress.current_journal = None
                progress.pending_journals = []
                progress.current_issue = None
                progress.pending_issues = []
                progress.article_list = []
                progress.current_article = None
                progress.current_article_index = 0
                progress.total_articles = 0
                progress.add_log("info", f"Arka plan NLP işleri bekleniyor ({len(nlp_futures)})")
                for nlp_future in nlp_futures:
                    if self._ieee_stop_flag.is_set():
                        progress.status = ScraperStatus.STOPPED
                        progress.add_log("warning", "Scraper durduruldu")
                        break
                    try:
                        nlp_future.result(timeout=600)
                    except Exception as e:
                        logger.warning(f"[IEEE Thread] Arka plan NLP işi beklenirken hata: {e}")

            if progress.status == ScraperStatus.RUNNING:
                progress.status = ScraperStatus.COMPLETED
                progress.add_log("success", "IEEE scraper tamamlandı")
                logger.success("[IEEE Thread] Scraper tamamlandı")
                if self.ieee_continuous:
                    progress.add_log("info", "Sürekli mod aktif — yeniden başlatma bekleniyor...")
        
        except ScraperStoppedException:
            # Stop sinyali - normal sonlanma
            progress.status = ScraperStatus.STOPPED
            progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
            logger.warning("[IEEE Thread] Scraper durduruldu")
        except Exception as e:
            progress.status = ScraperStatus.ERROR
            progress.last_error = str(e)
            progress.add_log("error", f"Fatal error: {str(e)}")
            logger.error(f"[IEEE Thread] Fatal error: {e}")
            print(f"[IEEE Thread] HATA: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        finally:
            self._ieee_scraper = None
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            progress.last_activity = datetime.utcnow()
            # Browser kapandıktan sonra kısa bekle — asyncio loop'un
            # daha önce schedule edilmiş event'leri göndermesine izin ver
            import time as _t; _t.sleep(0.5)
            # Final status event'ini tekrar gönder (ilki browser kapanırken kaybolmuş olabilir)
            try:
                from backend.routers.websocket import emit_scraper_event
                emit_scraper_event("status_update", progress.scraper_type, progress.to_dict())
            except Exception:
                pass
            # Distributed lock'u bırak
            if self._loop:
                fut = asyncio.run_coroutine_threadsafe(
                    DistributedScraperLock.release("ieee"), self._loop
                )
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass
            # Sürekli mod: lock serbest bırakıldıktan sonra yeniden başlat
            if (self.ieee_continuous
                    and progress.status == ScraperStatus.COMPLETED
                    and not self._ieee_stop_flag.is_set()
                    and self._loop):
                import time as _ct; _ct.sleep(5)
                asyncio.run_coroutine_threadsafe(
                    self.start_ieee(
                        headless=self.ieee_headless,
                        max_articles=self.ieee_max_articles,
                        depth=self.ieee_depth,
                        issues_order=self.ieee_issues_order,
                        continuous=True,
                    ),
                    self._loop,
                )

    async def stop_ieee(self) -> bool:
        """IEEE scraper'ı durdur"""
        if self.ieee_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False

        logger.info("IEEE scraper durduruluyor...")
        self._ieee_stop_flag.set()
        self.ieee_progress.status = ScraperStatus.STOPPING
        self.ieee_progress.add_log("warning", "Durdurma sinyali gönderildi")

        # Tarayıcıyı hemen kapat — cdp.get() gibi uzun beklemeleri keser
        s = self._ieee_scraper
        if s:
            try:
                s.selenium_driver.close()
            except Exception:
                pass

        if self._ieee_future:
            try:
                self._ieee_future.result(timeout=10)
                logger.success("IEEE scraper düzgün şekilde durduruldu")
            except concurrent.futures.TimeoutError:
                logger.warning("IEEE scraper stop timeout")
                self.ieee_progress.status = ScraperStatus.STOPPED
            except Exception as e:
                logger.warning(f"IEEE scraper stop hatası: {e}")
                self.ieee_progress.status = ScraperStatus.STOPPED

        return True
    
    async def pause_ieee(self) -> bool:
        """IEEE scraper'ı duraklat"""
        if self.ieee_progress.status != ScraperStatus.RUNNING:
            return False
        
        self._ieee_pause_flag.set()
        return True
    
    async def resume_ieee(self) -> bool:
        """IEEE scraper'ı devam ettir"""
        if self.ieee_progress.status != ScraperStatus.PAUSED:
            return False
        
        self._ieee_pause_flag.clear()
        return True
    
    # ==================== ScienceDirect Scraper ====================
    
    async def start_sciencedirect(self, headless: bool = True, max_articles: int = 100, depth: int = 1, issues_order: str = "newest_first", continuous: bool = False) -> bool:
        """ScienceDirect scraper'ı başlat (ayrı thread'de)"""
        if self.sciencedirect_progress.status == ScraperStatus.RUNNING:
            logger.warning("ScienceDirect scraper already running")
            return False

        # Distributed lock
        if not await DistributedScraperLock.acquire("sciencedirect"):
            logger.warning("ScienceDirect scraper distributed lock alınamadı — başka bir instance çalıştırıyor")
            return False

        self.sciencedirect_headless = headless
        self.sciencedirect_max_articles = max_articles
        self.sciencedirect_depth = depth
        self.sciencedirect_issues_order = issues_order
        self.sciencedirect_continuous = continuous

        # Reset flags
        self._sciencedirect_stop_flag.clear()
        self._sciencedirect_pause_flag.clear()

        # Thread'de başlat - event loop'u bloklamaz
        self._sciencedirect_future = self._executor.submit(self._run_sciencedirect_scraper_sync)
        logger.info(f"ScienceDirect scraper thread'de başlatıldı (issues_order={issues_order})")

        return True
    
    def _run_sciencedirect_scraper_sync(self):
        """
        ScienceDirect scraper'ı senkron olarak çalıştır (ayrı thread'de).
        Bu metod thread pool'da çalışır ve main event loop'u bloklamaz.
        """
        progress = self.sciencedirect_progress
        progress.reset()
        # Tekil journal modu kontrolü — override set edilmişse flag'ı koru
        progress.is_single_journal_mode = bool(getattr(self, '_sd_single_journal_override', None))
        if progress.is_single_journal_mode and self._sd_single_journal_context:
            progress.single_journal_url = self._sd_single_journal_context.get("url")
            progress.single_journal_max_articles = self._sd_single_journal_context.get("max_articles")
            progress.single_journal_depth = self._sd_single_journal_context.get("depth")
        progress.status = ScraperStatus.STARTING
        progress.started_at = datetime.utcnow()
        progress.add_log("info", "ScienceDirect scraper başlatılıyor (ayrı thread)...")
        logger.info("[SD Thread] Scraper başlatılıyor...")
        logger.info(f"[SD Thread] Headless: {self.sciencedirect_headless}")
        print(f"[SD Thread] Başlatılıyor, headless={self.sciencedirect_headless}", flush=True)
        
        scraper = None
        nlp_futures: List[concurrent.futures.Future] = []
        
        try:
            _load_scraper_modules()
            if ScienceDirectScraper is None:
                raise Exception("ScienceDirect scraper modülü yüklenemedi")

            # Create and initialize
            logger.info("[SD Thread] Browser başlatılıyor...")
            print("[SD Thread] Browser başlatılıyor...", flush=True)
            scraper = ScienceDirectScraper(headless=self.sciencedirect_headless, stop_flag=self._sciencedirect_stop_flag, pause_flag=self._sciencedirect_pause_flag)
            self._sciencedirect_scraper = scraper
            print("[SD Thread] Scraper oluşturuldu, initialize ediliyor...", flush=True)
            scraper.initialize()
            print("[SD Thread] Browser başlatıldı!", flush=True)
            
            progress.status = ScraperStatus.RUNNING
            progress.add_log("info", "Browser başlatıldı")
            logger.success("[SD Thread] Browser başlatıldı")
            
            # ── Tekil journal override kontrolü ──────────────────────────
            _single_override = getattr(self, '_sd_single_journal_override', None)
            if _single_override:
                self._sd_single_journal_override = None  # tüket
                all_journals = _single_override
                progress.total_journals = len(all_journals)
                progress.add_log("info", f"Tekil journal modu — URL: {all_journals[0].get('url', '')}")
                logger.info(f"[SD Thread] Tekil journal modu: {all_journals[0].get('url', '')}")
            else:
                # Navigate to journals page
                logger.info("[SD Thread] Journals sayfasına gidiliyor...")
                success = scraper.navigate_to_journals()
                if not success:
                    raise Exception("Journals sayfasına gidilemedi")

                progress.add_log("success", "Journals sayfasına gidildi")
                logger.success("[SD Thread] Journals sayfasına gidildi")

                # Get all journals
                logger.info("[SD Thread] Journal listesi alınıyor...")
                all_journals = scraper.scrape_all_journals()
                progress.total_journals = len(all_journals)
                progress.add_log("info", f"{len(all_journals)} journal bulundu")
                logger.info(f"[SD Thread] {len(all_journals)} journal bulundu")

                # ============================================================
                # ÖNCELİK SİSTEMİ - JOURNAL SIRALAMA
                # ============================================================
                logger.info("[SD Thread] Öncelik sistemi: Veri tabanı kontrolü yapılıyor...")
                progress.add_log("info", "Öncelik sistemi: Veri tabanı kontrolü yapılıyor...")

                # Journal repository'yi başlat ve öncelik bilgilerini al (async call from thread)
                journal_names = [j.get('name', '') for j in all_journals]

                # Async call from thread
                journal_repo = JournalRepository()
                future = asyncio.run_coroutine_threadsafe(
                    journal_repo.get_bulk_priority_info(journal_names, 'sciencedirect'),
                    self._loop
                )
                priority_info = future.result(timeout=30)

                # İstatistikleri hesapla
                new_count = sum(1 for info in priority_info.values() if not info['exists'])
                existing_count = len(priority_info) - new_count

                logger.info(f"[SD Thread] Öncelik: {new_count} yeni, {existing_count} mevcut dergi")
                progress.add_log("info", f"Öncelik: {new_count} yeni, {existing_count} mevcut dergi")

                # Journal'ları öncelik sistemine göre sırala
                all_journals = JournalRepository.prioritize_journals(all_journals, priority_info)

                logger.success("[SD Thread] Journal'lar öncelik sırasına göre sıralandı!")
                progress.add_log("success", "Journal'lar öncelik sırasına göre sıralandı (Yeni dergiler önce, sonra en eski scrape edilenler)")

                # İlk 5 journal'ı logla
                for i, j in enumerate(all_journals[:5], 1):
                    info = priority_info.get(j.get('name', ''), {})
                    status = "🆕 YENİ" if not info.get('exists') else f"📅 Son: {info.get('last_scraped_at', 'Bilinmiyor')}"
                    logger.info(f"[SD Thread]   {i}. {j.get('name', 'Unknown')} - {status}")
            
            # Scrape each journal
            for idx, journal in enumerate(all_journals):
                # Stop check
                if self._sciencedirect_stop_flag.is_set():
                    progress.status = ScraperStatus.STOPPED
                    progress.add_log("warning", "Scraper durduruldu")
                    logger.warning("[SD Thread] Scraper durduruldu")
                    break
                
                if self._sciencedirect_pause_flag.is_set():
                    progress.status = ScraperStatus.PAUSED
                    while self._sciencedirect_pause_flag.is_set():
                        import time as _t; _t.sleep(0.3)
                    progress.status = ScraperStatus.RUNNING

                if progress.status == ScraperStatus.PAUSED:
                    progress.status = ScraperStatus.RUNNING
                
                journal_name = journal.get('name', 'Unknown')
                progress.current_journal = journal_name
                progress.current_journal_index = idx + 1
                progress.pending_journals = [j.get('name', '') for j in all_journals[idx + 1:]]
                progress.current_issue = None
                progress.current_issue_index = 0
                progress.total_issues = 0
                progress.completed_issues = []
                progress.article_list = []
                progress.current_article = None
                progress.current_article_index = 0
                progress.total_articles = 0
                progress.last_activity = datetime.utcnow()

                logger.info(f"[SD Thread] [{idx+1}/{len(all_journals)}] {journal_name} işleniyor...")

                def _sd_article_list_cb(titles: List[str]):
                    progress.article_list = titles

                def _sd_article_cb(art_idx: int, art_total: int, art_title: Optional[str]):
                    progress.total_articles = art_total
                    progress.current_article = art_title or f"Makale {art_idx}/{art_total}"
                    progress.current_article_index = art_idx

                def _sd_issue_start_cb(issue_idx: int, total_issues: int, issue_title: str, pending_titles: list = None):
                    progress.total_issues = total_issues
                    progress.current_issue = issue_title or f"Issue {issue_idx}"
                    progress.current_issue_index = issue_idx
                    progress.pending_issues = pending_titles or []
                    progress.article_list = []
                    progress.current_article = None
                    progress.current_article_index = 0
                    progress.total_articles = 0

                def _sd_issue_complete_cb(issue_idx: int, articles_count: int, article_titles: List[str]):
                    title = progress.current_issue or f"Issue {issue_idx}"
                    new_issues = progress.completed_issues + [{
                        'title': title,
                        'articles_count': articles_count,
                        'article_list': article_titles[:30],
                    }]
                    progress.completed_issues = new_issues
                    progress.current_issue = None
                    progress.pending_issues = []
                    progress.article_list = []
                    progress.current_article = None
                    progress.current_article_index = 0
                    progress.total_articles = 0

                def _sd_journal_name_cb(resolved_name: str):
                    progress.current_journal = resolved_name

                try:
                    import time
                    scrape_start_t = time.time()

                    # DB'de bu journal için mevcut issue URL'lerini çek
                    # (daha önce işlenmiş issue'lar depth sayımına dahil edilmez)
                    existing_issue_urls: set = set()
                    if self._db_service and self._loop:
                        async def _get_existing_issue_urls():
                            journal_doc = await self._db_service.get_journal(
                                journal.get('name', ''), 'sciencedirect'
                            )
                            if not journal_doc:
                                return set()
                            from database import Issue
                            issues = await Issue.find_by_journal(journal_doc.id)
                            result = set()
                            for iss in issues:
                                if iss.url:
                                    # DB'de tam URL saklanır; relative path kısmını çıkar
                                    url = iss.url.replace('https://www.sciencedirect.com', '')
                                    result.add(url)
                            return result

                        try:
                            fut = asyncio.run_coroutine_threadsafe(
                                _get_existing_issue_urls(), self._loop
                            )
                            existing_issue_urls = fut.result(timeout=15)
                            if existing_issue_urls:
                                logger.info(
                                    f"[SD Thread] {journal_name}: "
                                    f"{len(existing_issue_urls)} mevcut issue URL'si bulundu, atlanacak"
                                )
                        except Exception as e:
                            logger.warning(f"[SD Thread] Mevcut issue URL'leri alınamadı: {e}")

                    # Scrape issues + articles
                    issue_results = scraper.scrape_journal_articles(
                        journal,
                        depth=self.sciencedirect_depth,
                        max_articles=self.sciencedirect_max_articles,
                        article_progress_callback=_sd_article_cb,
                        article_list_callback=_sd_article_list_cb,
                        journal_name_callback=_sd_journal_name_cb,
                        existing_issue_urls=existing_issue_urls,
                        issue_start_callback=_sd_issue_start_cb,
                        issue_complete_callback=_sd_issue_complete_cb,
                        issues_order=self.sciencedirect_issues_order,
                    )

                    if self._sciencedirect_stop_flag.is_set():
                        progress.status = ScraperStatus.STOPPED
                        progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
                        logger.warning("[SD Thread] Stop sinyali sonrası journal kaydı atlandı")
                        break

                    resolved_journal_name = journal.get('name', journal_name)
                    if resolved_journal_name != journal_name:
                        journal_name = resolved_journal_name
                        progress.current_journal = resolved_journal_name

                    try:
                        from backend.core.metrics import SCRAPER_DURATION
                        SCRAPER_DURATION.labels(source="sciencedirect").observe(time.time() - scrape_start_t)
                    except ImportError:
                        pass

                    # Makale olsun olmasın journal'ı veritabanına kaydet
                    if self._db_service and self._loop:
                        journal_info = {
                            'name': journal.get('name'),
                            'url': journal.get('url'),
                            'publisher': 'Elsevier',
                            'open_access': journal.get('open_access', False),
                            'letter_group': journal.get('letter_group'),
                            'aims_and_scope': journal.get('aims_and_scope'),
                        }

                        async def _save_journal_issues():
                            journal_doc, _ = await self._db_service.add_journal(
                                source_website='sciencedirect',
                                **journal_info
                            )
                            total_created = 0
                            total_updated = 0
                            issues_created = 0
                            for res in issue_results:
                                i_data = res['issue_info']
                                issue_doc, issue_created = await self._db_service.add_issue(
                                    journal=journal_doc,
                                    issue_number=i_data.get('issue_number'),
                                    date=i_data.get('date'),
                                    url=i_data.get('url'),
                                    status=i_data.get('status'),
                                )
                                created, updated = await self._db_service.add_articles_bulk(
                                    issue_doc, res['articles']
                                )
                                total_created += created
                                total_updated += updated
                                if issue_created:
                                    issues_created += 1
                            await self._db_service.recalculate_journal_counts(journal_doc.id)
                            return total_created, total_updated, issues_created

                        future = asyncio.run_coroutine_threadsafe(_save_journal_issues(), self._loop)
                        articles_created, articles_updated, issues_created = future.result(timeout=60)

                        progress.completed_journals.append({
                            'name': journal.get('name', journal_name),
                            'articles_count': articles_created,
                            'issues': progress.completed_issues.copy(),
                        })
                        progress.journals_scraped += 1
                        progress.issues_scraped += issues_created
                        progress.articles_scraped += articles_created
                        progress.articles_updated += articles_updated

                        if issue_results:
                            progress.add_log("success", f"{journal.get('name')}: {articles_created} makale eklendi")
                            logger.success(f"[SD Thread] {journal_name}: {articles_created} makale eklendi")
                        else:
                            progress.add_log("info", f"{journal.get('name')}: Makale yok, journal kaydedildi")
                            logger.info(f"[SD Thread] {journal_name}: Makale yok, journal kaydedildi")

                        if articles_created > 0 and self._loop and not progress.is_single_journal_mode:
                            async def _sd_journal_cluster_update():
                                try:
                                    from backend.services.nlp_service import NLPService
                                    result = await NLPService().assign_new_articles()
                                    logger.success(f"[SD Thread] Incremental clustering tamamland\u0131: {result}")
                                except FileNotFoundError:
                                    logger.info("[SD Thread] NLP modeli bulunamad\u0131, incremental clustering atland\u0131")
                                except Exception as _e:
                                    logger.warning(f"[SD Thread] Incremental clustering hatas\u0131: {_e}")
                            nlp_future = asyncio.run_coroutine_threadsafe(
                                _sd_journal_cluster_update(), self._loop
                            )
                            nlp_futures.append(nlp_future)
                        elif articles_created > 0 and progress.is_single_journal_mode:
                            progress.add_log("info", "Tekil URL modu: incremental NLP scraping aşamasında atlandı, analyzing aşamasında çalışacak")
                    
                except ScraperStoppedException:
                    # Stop sinyali alındı - döngüden çık
                    progress.status = ScraperStatus.STOPPED
                    progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
                    logger.warning(f"[SD Thread] Scraper durduruldu (makale işlemi sırasında)")
                    break
                except Exception as e:
                    progress.errors_count += 1
                    progress.last_error = str(e)
                    progress.add_log("error", f"{journal.get('name')}: {str(e)}")
                    logger.error(f"[SD Thread] {journal_name} hatası: {str(e)}")
                
                # Rate limiting
                import time
                time.sleep(2)
            
            if progress.status == ScraperStatus.RUNNING and nlp_futures:
                progress.current_journal = None
                progress.pending_journals = []
                progress.current_issue = None
                progress.pending_issues = []
                progress.article_list = []
                progress.current_article = None
                progress.current_article_index = 0
                progress.total_articles = 0
                progress.add_log("info", f"Arka plan NLP işleri bekleniyor ({len(nlp_futures)})")
                for nlp_future in nlp_futures:
                    if self._sciencedirect_stop_flag.is_set():
                        progress.status = ScraperStatus.STOPPED
                        progress.add_log("warning", "Scraper durduruldu")
                        break
                    try:
                        nlp_future.result(timeout=600)
                    except Exception as e:
                        logger.warning(f"[SD Thread] Arka plan NLP işi beklenirken hata: {e}")

            if progress.status == ScraperStatus.RUNNING:
                progress.status = ScraperStatus.COMPLETED
                progress.add_log("success", "ScienceDirect scraper tamamlandı")
                logger.success("[SD Thread] Scraper tamamlandı")
                if self.sciencedirect_continuous:
                    progress.add_log("info", "Sürekli mod aktif — yeniden başlatma bekleniyor...")
        
        except ScraperStoppedException:
            # Stop sinyali - normal sonlanma
            progress.status = ScraperStatus.STOPPED
            progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
            logger.warning("[SD Thread] Scraper durduruldu")
        except Exception as e:
            progress.status = ScraperStatus.ERROR
            progress.last_error = str(e)
            progress.add_log("error", f"Fatal error: {str(e)}")
            logger.error(f"[SD Thread] Fatal error: {e}")
            print(f"[SD Thread] HATA: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        finally:
            self._sciencedirect_scraper = None
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            progress.last_activity = datetime.utcnow()
            import time as _t; _t.sleep(0.5)
            try:
                from backend.routers.websocket import emit_scraper_event
                emit_scraper_event("status_update", progress.scraper_type, progress.to_dict())
            except Exception:
                pass
            # Distributed lock'u bırak
            if self._loop:
                fut = asyncio.run_coroutine_threadsafe(
                    DistributedScraperLock.release("sciencedirect"), self._loop
                )
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass
            # Sürekli mod: lock serbest bırakıldıktan sonra yeniden başlat
            if (self.sciencedirect_continuous
                    and progress.status == ScraperStatus.COMPLETED
                    and not self._sciencedirect_stop_flag.is_set()
                    and self._loop):
                import time as _ct; _ct.sleep(5)
                asyncio.run_coroutine_threadsafe(
                    self.start_sciencedirect(
                        headless=self.sciencedirect_headless,
                        max_articles=self.sciencedirect_max_articles,
                        depth=self.sciencedirect_depth,
                        issues_order=self.sciencedirect_issues_order,
                        continuous=True,
                    ),
                    self._loop,
                )

    async def stop_sciencedirect(self) -> bool:
        """ScienceDirect scraper'ı durdur"""
        if self.sciencedirect_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False

        logger.info("ScienceDirect scraper durduruluyor...")
        self._sciencedirect_stop_flag.set()
        self.sciencedirect_progress.status = ScraperStatus.STOPPING
        self.sciencedirect_progress.add_log("warning", "Durdurma sinyali gönderildi")

        # Tarayıcıyı hemen kapat
        s = self._sciencedirect_scraper
        if s:
            try:
                s.selenium_driver.close()
            except Exception:
                pass

        if self._sciencedirect_future:
            try:
                self._sciencedirect_future.result(timeout=10)
                logger.success("ScienceDirect scraper düzgün şekilde durduruldu")
            except concurrent.futures.TimeoutError:
                logger.warning("ScienceDirect scraper stop timeout")
                self.sciencedirect_progress.status = ScraperStatus.STOPPED
            except Exception as e:
                logger.warning(f"ScienceDirect scraper stop hatası: {e}")
                self.sciencedirect_progress.status = ScraperStatus.STOPPED

        return True
    
    async def pause_sciencedirect(self) -> bool:
        """ScienceDirect scraper'ı duraklat"""
        if self.sciencedirect_progress.status != ScraperStatus.RUNNING:
            return False
        
        self._sciencedirect_pause_flag.set()
        return True
    
    async def resume_sciencedirect(self) -> bool:
        """ScienceDirect scraper'ı devam ettir"""
        if self.sciencedirect_progress.status != ScraperStatus.PAUSED:
            return False
        
        self._sciencedirect_pause_flag.clear()
        return True
    

    # ==================== ACM Scraper ====================
    
    async def start_acm(self, headless: bool = True, max_articles: int = 100, depth: int = 1, issues_order: str = "newest_first", continuous: bool = False) -> bool:
        """ACM scraper'ı başlat (ayrı thread'de)"""
        if self.acm_progress.status == ScraperStatus.RUNNING:
            logger.warning("ACM scraper already running")
            return False

        # Distributed lock
        if not await DistributedScraperLock.acquire("acm"):
            logger.warning("ACM scraper distributed lock alınamadı — başka bir instance çalıştırıyor")
            return False

        self.acm_headless = headless
        self.acm_max_articles = max_articles
        self.acm_depth = depth
        self.acm_issues_order = issues_order
        self.acm_continuous = continuous

        # Reset flags
        self._acm_stop_flag.clear()
        self._acm_pause_flag.clear()

        # Thread'de başlat - event loop'u bloklamaz
        self._acm_future = self._executor.submit(self._run_acm_scraper_sync)
        logger.info(f"ACM scraper thread'de başlatıldı (issues_order={issues_order})")

        return True
    
    def _run_acm_scraper_sync(self):
        """
        ACM scraper'ı senkron olarak çalıştır (ayrı thread'de).
        Bu metod thread pool'da çalışır ve main event loop'u bloklamaz.
        """
        progress = self.acm_progress
        progress.reset()
        # Tekil journal modu kontrolü — override set edilmişse flag'ı koru
        progress.is_single_journal_mode = bool(getattr(self, '_acm_single_journal_override', None))
        if progress.is_single_journal_mode and self._acm_single_journal_context:
            progress.single_journal_url = self._acm_single_journal_context.get("url")
            progress.single_journal_max_articles = self._acm_single_journal_context.get("max_articles")
            progress.single_journal_depth = self._acm_single_journal_context.get("depth")
        progress.status = ScraperStatus.STARTING
        progress.started_at = datetime.utcnow()
        progress.add_log("info", "ACM scraper başlatılıyor (ayrı thread)...")
        logger.info("[ACM Thread] Scraper başlatılıyor...")
        logger.info(f"[ACM Thread] Headless: {self.acm_headless}")
        print(f"[ACM Thread] Başlatılıyor, headless={self.acm_headless}", flush=True)
        
        scraper = None
        nlp_futures: List[concurrent.futures.Future] = []
        
        try:
            _load_scraper_modules()
            if ACMScraper is None:
                raise Exception("ACM scraper modülü yüklenemedi")

            # Create and initialize
            logger.info("[ACM Thread] Browser başlatılıyor...")
            print("[ACM Thread] Browser başlatılıyor...", flush=True)
            scraper = ACMScraper(headless=self.acm_headless, stop_flag=self._acm_stop_flag, pause_flag=self._acm_pause_flag)
            self._acm_scraper = scraper
            print("[ACM Thread] Scraper oluşturuldu, initialize ediliyor...", flush=True)
            scraper.initialize()
            print("[ACM Thread] Browser başlatıldı!", flush=True)
            
            progress.status = ScraperStatus.RUNNING
            progress.add_log("info", "Browser başlatıldı")
            logger.success("[ACM Thread] Browser başlatıldı")
            
            # ── Tekil journal override kontrolü ──────────────────────────
            _single_override = getattr(self, '_acm_single_journal_override', None)
            if _single_override:
                self._acm_single_journal_override = None  # tüket
                all_journals = _single_override
                progress.total_journals = len(all_journals)
                progress.add_log("info", f"Tekil journal modu — URL: {all_journals[0].get('url', '')}")
                logger.info(f"[ACM Thread] Tekil journal modu: {all_journals[0].get('url', '')}")
            else:
                # Navigate to journals page
                logger.info("[ACM Thread] Journals sayfasına gidiliyor...")
                success = scraper.navigate_to_journals()
                if not success:
                    raise Exception("Journals sayfasına gidilemedi")

                progress.add_log("success", "Journals sayfasına gidildi")
                logger.success("[ACM Thread] Journals sayfasına gidildi")

                # Get all journals
                logger.info("[ACM Thread] Journal listesi alınıyor...")
                all_journals = scraper.scrape_journals()
                progress.total_journals = len(all_journals)
                progress.add_log("info", f"{len(all_journals)} journal bulundu")
                logger.info(f"[ACM Thread] {len(all_journals)} journal bulundu")

                # ============================================================
                # ÖNCELİK SİSTEMİ - JOURNAL SIRALAMA
                # ============================================================
                logger.info("[ACM Thread] Öncelik sistemi: Veri tabanı kontrolü yapılıyor...")
                progress.add_log("info", "Öncelik sistemi: Veri tabanı kontrolü yapılıyor...")

                # Journal repository'yi başlat ve öncelik bilgilerini al (async call from thread)
                journal_names = [j.get('name', '') for j in all_journals]

                # Async call from thread
                journal_repo = JournalRepository()
                future = asyncio.run_coroutine_threadsafe(
                    journal_repo.get_bulk_priority_info(journal_names, 'acm'),
                    self._loop
                )
                priority_info = future.result(timeout=30)

                # İstatistikleri hesapla
                new_count = sum(1 for info in priority_info.values() if not info['exists'])
                existing_count = len(priority_info) - new_count

                logger.info(f"[ACM Thread] Öncelik: {new_count} yeni, {existing_count} mevcut dergi")
                progress.add_log("info", f"Öncelik: {new_count} yeni, {existing_count} mevcut dergi")

                # Journal'ları öncelik sistemine göre sırala
                all_journals = JournalRepository.prioritize_journals(all_journals, priority_info)

                logger.success("[ACM Thread] Journal'lar öncelik sırasına göre sıralandı!")
                progress.add_log("success", "Journal'lar öncelik sırasına göre sıralandı (Yeni dergiler önce, sonra en eski scrape edilenler)")

                # İlk 5 journal'ı logla
                for i, j in enumerate(all_journals[:5], 1):
                    info = priority_info.get(j.get('name', ''), {})
                    status = "🆕 YENİ" if not info.get('exists') else f"📅 Son: {info.get('last_scraped_at', 'Bilinmiyor')}"
                    logger.info(f"[ACM Thread]   {i}. {j.get('name', 'Unknown')} - {status}")
            
            # Scrape each journal
            for idx, journal in enumerate(all_journals):
                # Stop check
                if self._acm_stop_flag.is_set():
                    progress.status = ScraperStatus.STOPPED
                    progress.add_log("warning", "Scraper durduruldu")
                    logger.warning("[ACM Thread] Scraper durduruldu")
                    break
                
                if self._acm_pause_flag.is_set():
                    progress.status = ScraperStatus.PAUSED
                    while self._acm_pause_flag.is_set():
                        import time as _t; _t.sleep(0.3)
                    progress.status = ScraperStatus.RUNNING

                if progress.status == ScraperStatus.PAUSED:
                    progress.status = ScraperStatus.RUNNING
                
                journal_name = journal.get('name', 'Unknown')
                progress.current_journal = journal_name
                progress.current_journal_index = idx + 1
                progress.pending_journals = [j.get('name', '') for j in all_journals[idx + 1:]]
                progress.current_issue = None
                progress.current_issue_index = 0
                progress.total_issues = 0
                progress.completed_issues = []
                progress.article_list = []
                progress.current_article = None
                progress.current_article_index = 0
                progress.total_articles = 0
                progress.last_activity = datetime.utcnow()

                logger.info(f"[ACM Thread] [{idx+1}/{len(all_journals)}] {journal_name} işleniyor...")

                def _acm_article_list_cb(titles: List[str]):
                    progress.article_list = titles

                def _acm_article_cb(art_idx: int, art_total: int, art_title: Optional[str]):
                    progress.total_articles = art_total
                    progress.current_article = art_title or f"Makale {art_idx}/{art_total}"
                    progress.current_article_index = art_idx

                def _acm_issue_start_cb(issue_idx: int, total_issues: int, issue_title: str, pending_titles: list = None):
                    progress.total_issues = total_issues
                    progress.current_issue = issue_title or f"Issue {issue_idx}"
                    progress.current_issue_index = issue_idx
                    progress.pending_issues = pending_titles or []
                    progress.article_list = []
                    progress.current_article = None
                    progress.current_article_index = 0
                    progress.total_articles = 0

                def _acm_issue_complete_cb(issue_idx: int, articles_count: int, article_titles: List[str]):
                    title = progress.current_issue or f"Issue {issue_idx}"
                    new_issues = progress.completed_issues + [{
                        'title': title,
                        'articles_count': articles_count,
                        'article_list': article_titles[:30],
                    }]
                    progress.completed_issues = new_issues
                    progress.current_issue = None
                    progress.pending_issues = []
                    progress.article_list = []
                    progress.current_article = None
                    progress.current_article_index = 0
                    progress.total_articles = 0

                def _acm_journal_name_cb(resolved_name: str):
                    progress.current_journal = resolved_name

                try:
                    import time
                    scrape_start_t = time.time()

                    # DB'deki mevcut issue URL'lerini al (depth sayımı için)
                    existing_issue_urls: set = set()
                    if self._db_service and self._loop:
                        async def _get_acm_existing_issue_urls():
                            journal_doc = await self._db_service.get_journal(
                                journal.get('name', ''), 'acm'
                            )
                            if not journal_doc:
                                return set()
                            from database import Issue
                            issues = await Issue.find_by_journal(journal_doc.id)
                            result = set()
                            for iss in issues:
                                if iss.url:
                                    url = iss.url.replace('https://dl.acm.org', '')
                                    result.add(url)
                            return result
                        try:
                            fut = asyncio.run_coroutine_threadsafe(
                                _get_acm_existing_issue_urls(), self._loop
                            )
                            existing_issue_urls = fut.result(timeout=15)
                            if existing_issue_urls:
                                logger.info(
                                    f"[ACM Thread] {journal_name}: "
                                    f"{len(existing_issue_urls)} mevcut issue URL'si bulundu, atlanacak"
                                )
                        except Exception as e:
                            logger.warning(f"[ACM Thread] Mevcut issue URL'leri alınamadı: {e}")

                    # Scrape issues + articles
                    issue_results = scraper.scrape_journal_articles(
                        journal,
                        depth=self.acm_depth,
                        max_articles=self.acm_max_articles,
                        article_progress_callback=_acm_article_cb,
                        article_list_callback=_acm_article_list_cb,
                        journal_name_callback=_acm_journal_name_cb,
                        existing_issue_urls=existing_issue_urls,
                        issue_start_callback=_acm_issue_start_cb,
                        issue_complete_callback=_acm_issue_complete_cb,
                        issues_order=self.acm_issues_order,
                    )

                    if self._acm_stop_flag.is_set():
                        progress.status = ScraperStatus.STOPPED
                        progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
                        logger.warning("[ACM Thread] Stop sinyali sonrası journal kaydı atlandı")
                        break

                    resolved_journal_name = journal.get('name', journal_name)
                    if resolved_journal_name != journal_name:
                        journal_name = resolved_journal_name
                        progress.current_journal = resolved_journal_name

                    try:
                        from backend.core.metrics import SCRAPER_DURATION
                        SCRAPER_DURATION.labels(source="acm").observe(time.time() - scrape_start_t)
                    except ImportError:
                        pass

                    # Makale olsun olmasın journal'ı veritabanına kaydet
                    if self._db_service and self._loop:
                        journal_info = {
                            'name': journal.get('name'),
                            'url': journal.get('url'),
                            'publisher': 'ACM',
                            'open_access': journal.get('open_access', False),
                            'aims_and_scope': journal.get('aims_and_scope'),
                        }

                        async def _save_acm_journal_issues():
                            journal_doc, _ = await self._db_service.add_journal(
                                source_website='acm', **journal_info
                            )
                            total_created = 0
                            total_updated = 0
                            issues_created = 0
                            for res in issue_results:
                                i_data = res['issue_info']
                                issue_doc, issue_created = await self._db_service.add_issue(
                                    journal=journal_doc,
                                    issue_number=i_data.get('issue_number'),
                                    date=i_data.get('date'),
                                    url=i_data.get('url'),
                                )
                                created, updated = await self._db_service.add_articles_bulk(
                                    issue_doc, res['articles']
                                )
                                total_created += created
                                total_updated += updated
                                if issue_created:
                                    issues_created += 1
                            await self._db_service.recalculate_journal_counts(journal_doc.id)
                            return total_created, total_updated, issues_created

                        # Run async database call from thread
                        future = asyncio.run_coroutine_threadsafe(
                            _save_acm_journal_issues(), self._loop
                        )
                        articles_created, articles_updated, issues_created = future.result(timeout=60)

                        progress.completed_journals.append({
                            'name': journal_name,
                            'articles_count': articles_created,
                            'issues': progress.completed_issues.copy(),
                        })
                        progress.journals_scraped += 1
                        progress.issues_scraped += issues_created
                        progress.articles_scraped += articles_created
                        progress.articles_updated += articles_updated

                        if issue_results:
                            progress.add_log("success", f"{journal.get('name')}: {articles_created} makale eklendi")
                            logger.success(f"[ACM Thread] {journal_name}: {articles_created} makale eklendi")
                        else:
                            progress.add_log("info", f"{journal.get('name')}: Makale yok, journal kaydedildi")
                            logger.info(f"[ACM Thread] {journal_name}: Makale yok, journal kaydedildi")

                        if articles_created > 0 and self._loop and not progress.is_single_journal_mode:
                            async def _acm_journal_cluster_update():
                                try:
                                    from backend.services.nlp_service import NLPService
                                    result = await NLPService().assign_new_articles()
                                    logger.success(f"[ACM Thread] Incremental clustering tamamland\u0131: {result}")
                                except FileNotFoundError:
                                    logger.info("[ACM Thread] NLP modeli bulunamad\u0131, incremental clustering atland\u0131")
                                except Exception as _e:
                                    logger.warning(f"[ACM Thread] Incremental clustering hatas\u0131: {_e}")
                            nlp_future = asyncio.run_coroutine_threadsafe(
                                _acm_journal_cluster_update(), self._loop
                            )
                            nlp_futures.append(nlp_future)
                        elif articles_created > 0 and progress.is_single_journal_mode:
                            progress.add_log("info", "Tekil URL modu: incremental NLP scraping aşamasında atlandı, analyzing aşamasında çalışacak")

                except ScraperStoppedException:
                    # Stop sinyali alındı - döngüden çık
                    progress.status = ScraperStatus.STOPPED
                    progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
                    logger.warning(f"[ACM Thread] Scraper durduruldu (makale işlemi sırasında)")
                    break
                except Exception as e:
                    progress.errors_count += 1
                    progress.last_error = str(e)
                    progress.add_log("error", f"{journal.get('name')}: {str(e)}")
                    logger.error(f"[ACM Thread] {journal_name} hatası: {str(e)}")
                
                # Rate limiting
                import time
                time.sleep(2)
            
            if progress.status == ScraperStatus.RUNNING and nlp_futures:
                progress.current_journal = None
                progress.pending_journals = []
                progress.current_issue = None
                progress.pending_issues = []
                progress.article_list = []
                progress.current_article = None
                progress.current_article_index = 0
                progress.total_articles = 0
                progress.add_log("info", f"Arka plan NLP işleri bekleniyor ({len(nlp_futures)})")
                for nlp_future in nlp_futures:
                    if self._acm_stop_flag.is_set():
                        progress.status = ScraperStatus.STOPPED
                        progress.add_log("warning", "Scraper durduruldu")
                        break
                    try:
                        nlp_future.result(timeout=600)
                    except Exception as e:
                        logger.warning(f"[ACM Thread] Arka plan NLP işi beklenirken hata: {e}")

            if progress.status == ScraperStatus.RUNNING:
                progress.status = ScraperStatus.COMPLETED
                progress.add_log("success", "ACM scraper tamamlandı")
                logger.success("[ACM Thread] Scraper tamamlandı")
                if self.acm_continuous:
                    progress.add_log("info", "Sürekli mod aktif — yeniden başlatma bekleniyor...")
        
        except ScraperStoppedException:
            # Stop sinyali - normal sonlanma
            progress.status = ScraperStatus.STOPPED
            progress.add_log("warning", "Scraper kullanıcı tarafından durduruldu")
            logger.warning("[ACM Thread] Scraper durduruldu")
        except Exception as e:
            progress.status = ScraperStatus.ERROR
            progress.last_error = str(e)
            progress.add_log("error", f"Fatal error: {str(e)}")
            logger.error(f"[ACM Thread] Fatal error: {e}")
            print(f"[ACM Thread] HATA: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        finally:
            self._acm_scraper = None
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            progress.last_activity = datetime.utcnow()
            import time as _t; _t.sleep(0.5)
            try:
                from backend.routers.websocket import emit_scraper_event
                emit_scraper_event("status_update", progress.scraper_type, progress.to_dict())
            except Exception:
                pass
            # Distributed lock'u bırak
            if self._loop:
                fut = asyncio.run_coroutine_threadsafe(
                    DistributedScraperLock.release("acm"), self._loop
                )
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass
            # Sürekli mod: lock serbest bırakıldıktan sonra yeniden başlat
            if (self.acm_continuous
                    and progress.status == ScraperStatus.COMPLETED
                    and not self._acm_stop_flag.is_set()
                    and self._loop):
                import time as _ct; _ct.sleep(5)
                asyncio.run_coroutine_threadsafe(
                    self.start_acm(
                        headless=self.acm_headless,
                        max_articles=self.acm_max_articles,
                        depth=self.acm_depth,
                        issues_order=self.acm_issues_order,
                        continuous=True,
                    ),
                    self._loop,
                )

    async def stop_acm(self) -> bool:
        """ACM scraper'ı durdur"""
        if self.acm_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False

        logger.info("ACM scraper durduruluyor...")
        self._acm_stop_flag.set()
        self.acm_progress.status = ScraperStatus.STOPPING
        self.acm_progress.add_log("warning", "Durdurma sinyali gönderildi")

        # Tarayıcıyı hemen kapat
        s = self._acm_scraper
        if s:
            try:
                s.selenium_driver.close()
            except Exception:
                pass

        if self._acm_future:
            try:
                self._acm_future.result(timeout=10)
                logger.success("ACM scraper düzgün şekilde durduruldu")
            except concurrent.futures.TimeoutError:
                logger.warning("ACM scraper stop timeout")
                self.acm_progress.status = ScraperStatus.STOPPED
            except Exception as e:
                logger.warning(f"ACM scraper stop hatası: {e}")
                self.acm_progress.status = ScraperStatus.STOPPED

        return True
    
    async def pause_acm(self) -> bool:
        """ACM scraper'ı duraklat"""
        if self.acm_progress.status != ScraperStatus.RUNNING:
            return False
        
        self._acm_pause_flag.set()
        return True
    
    async def resume_acm(self) -> bool:
        """ACM scraper'ı devam ettir"""
        if self.acm_progress.status != ScraperStatus.PAUSED:
            return False
        
        self._acm_pause_flag.clear()
        return True

    # ==================== All Scrapers ====================
    
    async def start_all(self, headless: bool = True, ieee_enabled: bool = True, sd_enabled: bool = True, acm_enabled: bool = True) -> Dict[str, bool]:
        """
        Tüm scraper'ları PARALEL modda başlat.
        Scraper'lar 5 saniye arayla başlar ve aynı anda çalışır.
        
        Args:
            headless: Browser headless mod
            ieee_enabled: IEEE scraper etkin mi
            sd_enabled: ScienceDirect scraper etkin mi
        """
        import asyncio
        
        results = {}
        
        logger.info("PARALEL mod: Etkin scraper'lar aynı anda çalışacak")
        logger.info(f"  IEEE enabled: {ieee_enabled}, ScienceDirect enabled: {sd_enabled}, ACM enabled: {acm_enabled}")
        
        # IEEE'yi başlat (etkinse)
        if ieee_enabled:
            results['ieee'] = await self.start_ieee(headless=headless, max_articles=self.ieee_max_articles, depth=self.ieee_depth)
        else:
            results['ieee'] = False
            logger.info("IEEE scraper devre dışı, atlanıyor...")
        
        # 5 saniye bekle - chromedriver dosya çakışmasını önlemek için
        if ieee_enabled and sd_enabled:
            logger.info("ScienceDirect için 5 saniye bekleniyor (chromedriver çakışmasını önlemek için)...")
            await asyncio.sleep(5)
        
        # ScienceDirect'i başlat (etkinse)
        if sd_enabled:
            results['sciencedirect'] = await self.start_sciencedirect(headless=headless, max_articles=self.sciencedirect_max_articles, depth=self.sciencedirect_depth)
        else:
            results['sciencedirect'] = False
            logger.info("ScienceDirect scraper devre dışı, atlanıyor...")
        

        # ACM'i başlat (etkinse)
        if acm_enabled:
            # 5 saniye bekle
            if ieee_enabled or sd_enabled:
                await asyncio.sleep(5)
            results['acm'] = await self.start_acm(headless=headless, max_articles=self.acm_max_articles)
        else:
            results['acm'] = False
            logger.info("ACM scraper devre dışı, atlanıyor...")

        return results
    
    async def start_all_sequential(self, headless: bool = True, ieee_enabled: bool = True, sd_enabled: bool = True, acm_enabled: bool = True) -> Dict[str, bool]:
        """
        Tüm scraper'ları SIRALI modda başlat.
        Önce IEEE tamamlanır, sonra ScienceDirect başlar.
        
        Args:
            headless: Browser headless mod
            ieee_enabled: IEEE scraper etkin mi
            sd_enabled: ScienceDirect scraper etkin mi
        """
        import asyncio
        
        results = {}
        
        logger.info("SIRALI mod: Etkin scraper'lar sırayla çalışacak")
        logger.info(f"  IEEE enabled: {ieee_enabled}, ScienceDirect enabled: {sd_enabled}, ACM enabled: {acm_enabled}")
        
        # IEEE'yi başlat (etkinse)
        if ieee_enabled:
            results['ieee'] = await self.start_ieee(headless=headless, max_articles=self.ieee_max_articles, depth=self.ieee_depth)
            
            # IEEE'nin bitmesini bekle
            logger.info("IEEE scraper'ın bitmesi bekleniyor...")
            while self.ieee_progress.status in [ScraperStatus.STARTING, ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
                await asyncio.sleep(2)
            
            logger.info(f"IEEE scraper tamamlandı (status: {self.ieee_progress.status.value})")
            
            # 3 saniye bekle
            await asyncio.sleep(3)
        else:
            results['ieee'] = False
            logger.info("IEEE scraper devre dışı, atlanıyor...")
        
        # ScienceDirect'i başlat (etkinse)
        if sd_enabled:
            logger.info("ScienceDirect scraper başlatılıyor...")
            results['sciencedirect'] = await self.start_sciencedirect(headless=headless, max_articles=self.sciencedirect_max_articles, depth=self.sciencedirect_depth)
        else:
            results['sciencedirect'] = False
            logger.info("ScienceDirect scraper devre dışı, atlanıyor...")
        

        # ACM'i başlat (etkinse)
        if acm_enabled:
            # Öncekilerin bitmesini bekle
            if ieee_enabled or sd_enabled:
                logger.info("Önceki scraper'ların bitmesi bekleniyor...")
                while self.ieee_progress.status in [ScraperStatus.STARTING, ScraperStatus.RUNNING, ScraperStatus.PAUSED] or self.sciencedirect_progress.status in [ScraperStatus.STARTING, ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
                    await asyncio.sleep(2)
                await asyncio.sleep(3)
                
            logger.info("ACM scraper başlatılıyor...")
            results['acm'] = await self.start_acm(headless=headless, max_articles=self.acm_max_articles)
        else:
            results['acm'] = False
            logger.info("ACM scraper devre dışı, atlanıyor...")

        return results
    
    async def start_all_round_robin(self, headless: bool = True, journals_per_switch: int = 3, ieee_enabled: bool = True, sd_enabled: bool = True, acm_enabled: bool = True) -> Dict[str, bool]:
        """
        Tüm scraper'ları ROUND ROBIN modda başlat.
        Her X journal'da bir driver kapatılıp diğer siteye geçilir.
        Döngü: IEEE -> ScienceDirect -> IEEE -> ...
        
        Args:
            headless: Browser headless mod
            journals_per_switch: Kaç journal'da bir site değiştirilecek
            ieee_enabled: IEEE scraper etkin mi
            sd_enabled: ScienceDirect scraper etkin mi
        """
        # Sadece bir scraper etkinse, sequential modda çalıştır
        active_count = sum([ieee_enabled, sd_enabled, acm_enabled])
        if active_count == 1:
            logger.info("Sadece 1 scraper etkin, sequential modda çalışacak")
            return await self.start_all_sequential(headless=headless, ieee_enabled=ieee_enabled, sd_enabled=sd_enabled, acm_enabled=acm_enabled)
            
        if active_count == 0:
            logger.warning("Hiçbir scraper etkin değil!")
            return {'ieee': False, 'sciencedirect': False, 'acm': False}
        
        self.round_robin_journals_per_switch = journals_per_switch
        self._round_robin_stop_flag.clear()
        
        logger.info(f"ROUND ROBIN mod: Her {journals_per_switch} journal'da bir site değiştirilecek")
        logger.info(f"  IEEE enabled: {ieee_enabled}, ScienceDirect enabled: {sd_enabled}, ACM enabled: {acm_enabled}")
        
        # Thread'de başlat
        self._round_robin_future = self._executor.submit(
            self._run_round_robin_sync, 
            headless,
            ieee_enabled,
            sd_enabled
        )
        
        return {'ieee': ieee_enabled, 'sciencedirect': sd_enabled}
    
    def _run_round_robin_sync(self, headless: bool, ieee_enabled: bool = True, sd_enabled: bool = True, acm_enabled: bool = True):
        """
        Round Robin modda scraper'ları çalıştır (ayrı thread'de).
        Her X journal'da bir site değiştirir.
        """
        import time
        
        logger.info("[RoundRobin Thread] Başlatılıyor...")
        print("[RoundRobin Thread] Başlatılıyor...", flush=True)
        
        # Scraper sırası ve state'leri (sadece etkin olanlar)
        sites = []
        if ieee_enabled:
            sites.append('ieee')
        if sd_enabled:
            sites.append('sciencedirect')
        if acm_enabled:
            sites.append('acm')
        
        if not sites:
            logger.error("[RoundRobin] Hiçbir scraper etkin değil!")
            return
        
        logger.info(f"[RoundRobin] Etkin siteler: {sites}")
        current_site_idx = 0
        
        # Her site için journal listesi ve index (lazy loading)
        site_journals = {
            'ieee': None,
            'sciencedirect': None,
            'acm': None
        }
        site_indices = {
            'ieee': 0,
            'sciencedirect': 0,
            'acm': 0
        }
        site_priority_info = {
            'ieee': None,
            'sciencedirect': None,
            'acm': None
        }
        
        # Aktif scraper instance'ları
        scrapers = {
            'ieee': None,
            'sciencedirect': None,
            'acm': None
        }
        
        # Source website mapping
        source_websites = {
            'ieee': 'ieeexplore',
            'sciencedirect': 'sciencedirect',
            'acm': 'acm'
        }
        
        # Tüm siteler bitene kadar döngü
        all_completed = False
        
        try:
            while not all_completed and not self._round_robin_stop_flag.is_set():
                current_site = sites[current_site_idx]
                progress = self.ieee_progress if current_site == 'ieee' else self.sciencedirect_progress if current_site == 'sciencedirect' else self.acm_progress
                other_progress = self.sciencedirect_progress if current_site == 'ieee' else self.ieee_progress # A bit complex for 3 sites, but we'll leave it as is for other_progress or fix it
                
                # İlk kez bu siteye geçiyorsak başlat
                if scrapers[current_site] is None:
                    logger.info(f"[RoundRobin] {current_site.upper()} scraper başlatılıyor...")
                    progress.reset()
                    progress.status = ScraperStatus.STARTING
                    progress.started_at = datetime.utcnow()
                    progress.add_log("info", f"{current_site.upper()} scraper başlatılıyor (Round Robin)...")
                    
                    temp_scraper = None
                    try:
                        _load_scraper_modules()
                        if current_site == 'ieee':
                            if IEEEXploreScraper is None:
                                raise Exception("IEEE scraper modülü yüklenemedi")
                            temp_scraper = IEEEXploreScraper(headless=headless)
                            temp_scraper.initialize()
                            
                            # Journals sayfasına git
                            if not temp_scraper.navigate_to_journals():
                                raise Exception("IEEE journals sayfasına gidilemedi")
                            
                            # Başarılı - scraper'ı kaydet
                            scrapers['ieee'] = temp_scraper
                        elif current_site == 'sciencedirect':
                            if ScienceDirectScraper is None:
                                raise Exception("ScienceDirect scraper modülü yüklenemedi")
                            temp_scraper = ScienceDirectScraper(headless=headless)
                            temp_scraper.initialize()
                            
                            # Journals sayfasına git
                            if not temp_scraper.navigate_to_journals():
                                raise Exception("ScienceDirect journals sayfasına gidilemedi")
                            
                            # Başarılı - scraper'ı kaydet
                            scrapers['sciencedirect'] = temp_scraper
                        elif current_site == 'acm':
                            if ACMScraper is None:
                                raise Exception("ACM scraper modülü yüklenemedi")
                            temp_scraper = ACMScraper(headless=headless)
                            temp_scraper.initialize()
                            
                            # Journals sayfasına git
                            if not temp_scraper.navigate_to_journals():
                                raise Exception("ACM journals sayfasına gidilemedi")
                            
                            # Başarılı - scraper'ı kaydet
                            scrapers['acm'] = temp_scraper
                        
                        progress.status = ScraperStatus.RUNNING
                        progress.add_log("success", f"{current_site.upper()} browser başlatıldı")
                        logger.success(f"[RoundRobin] {current_site.upper()} browser başlatıldı")
                        
                    except Exception as e:
                        # Hata durumunda tarayıcıyı kapat
                        if temp_scraper:
                            try:
                                logger.info(f"[RoundRobin] {current_site.upper()} hata nedeniyle kapatılıyor...")
                                temp_scraper.close()
                            except:
                                pass
                        
                        progress.status = ScraperStatus.ERROR
                        progress.last_error = str(e)
                        progress.add_log("error", f"Browser başlatma hatası: {e}")
                        logger.error(f"[RoundRobin] {current_site.upper()} başlatma hatası: {e}")
                        
                        # ERR_TUNNEL_CONNECTION_FAILED gibi bağlantı hatalarında
                        # tüm scraperları durdur çünkü proxy çalışmıyor demektir
                        error_str = str(e).lower()
                        if 'err_tunnel' in error_str or 'connection_failed' in error_str or 'proxy' in error_str:
                            logger.error(f"[RoundRobin] Proxy/Tunnel bağlantı hatası tespit edildi!")
                            logger.error(f"[RoundRobin] Tüm scraperlar durduruluyor (proxy sorunlu)...")
                            progress.add_log("error", "Proxy bağlantı hatası - tüm scraperlar durduruluyor")
                            other_progress.status = ScraperStatus.ERROR
                            other_progress.last_error = "Proxy bağlantı hatası"
                            break
                        
                        # Sonraki siteye geç
                        current_site_idx = (current_site_idx + 1) % len(sites)
                        continue
                
                # Journal listesi henüz alınmadıysa al
                if site_journals[current_site] is None:
                    # Scraper başarıyla başlatılmış mı kontrol et
                    scraper = scrapers[current_site]
                    if scraper is None:
                        logger.warning(f"[RoundRobin] {current_site.upper()} scraper başlatılamamış, atlanıyor...")
                        progress.add_log("warning", "Scraper başlatılamamış, site atlanıyor")
                        site_journals[current_site] = []  # Boş liste ata ki tekrar denenmesin
                        current_site_idx = (current_site_idx + 1) % len(sites)
                        continue
                    
                    logger.info(f"[RoundRobin] {current_site.upper()} journal listesi alınıyor...")
                    progress.add_log("info", "Journal listesi alınıyor...")
                    
                    all_journals = scraper.scrape_journals() if current_site == 'acm' else scraper.scrape_all_journals()
                    
                    if not all_journals:
                        logger.warning(f"[RoundRobin] {current_site.upper()} journal bulunamadı")
                        progress.add_log("warning", "Journal bulunamadı")
                        site_journals[current_site] = []
                    else:
                        progress.total_journals = len(all_journals)
                        progress.add_log("info", f"{len(all_journals)} journal bulundu")
                        logger.info(f"[RoundRobin] {current_site.upper()}: {len(all_journals)} journal bulundu")
                        
                        # Öncelik sistemini uygula
                        logger.info(f"[RoundRobin] {current_site.upper()} öncelik sistemi uygulanıyor...")
                        journal_names = [j.get('name', '') for j in all_journals]
                        
                        journal_repo = JournalRepository()
                        future = asyncio.run_coroutine_threadsafe(
                            journal_repo.get_bulk_priority_info(journal_names, source_websites[current_site]),
                            self._loop
                        )
                        priority_info = future.result(timeout=30)
                        site_priority_info[current_site] = priority_info
                        
                        # İstatistikleri hesapla
                        new_count = sum(1 for info in priority_info.values() if not info['exists'])
                        existing_count = len(priority_info) - new_count
                        logger.info(f"[RoundRobin] {current_site.upper()}: {new_count} yeni, {existing_count} mevcut dergi")
                        progress.add_log("info", f"Öncelik: {new_count} yeni, {existing_count} mevcut dergi")
                        
                        # Journal'ları önceliğe göre sırala
                        all_journals = JournalRepository.prioritize_journals(all_journals, priority_info)
                        site_journals[current_site] = all_journals
                        
                        logger.success(f"[RoundRobin] {current_site.upper()} journal'lar öncelik sırasına göre sıralandı!")
                        progress.add_log("success", "Journal'lar öncelik sırasına göre sıralandı")
                
                # Bu sitede işlenecek journal var mı kontrol et
                journals = site_journals[current_site]
                start_idx = site_indices[current_site]
                
                # Tüm siteler başarısız olduysa (hepsi boş liste) döngüyü sonlandır
                all_sites_failed = all(
                    site_journals.get(s) is not None and len(site_journals.get(s, [])) == 0
                    for s in sites
                )
                if all_sites_failed:
                    logger.error("[RoundRobin] Tüm siteler başarısız - hiçbir journal bulunamadı!")
                    self.ieee_progress.status = ScraperStatus.ERROR
                    self.ieee_progress.last_error = "Hiçbir journal bulunamadı (proxy/bağlantı hatası olabilir)"
                    self.sciencedirect_progress.status = ScraperStatus.ERROR
                    self.sciencedirect_progress.last_error = "Hiçbir journal bulunamadı (proxy/bağlantı hatası olabilir)"
                    self.acm_progress.status = ScraperStatus.ERROR
                    self.acm_progress.last_error = "Hiçbir journal bulunamadı (proxy/bağlantı hatası olabilir)"
                    break
                
                if start_idx >= len(journals):
                    # Bu site tamamlandı (veya hiç journal yoktu)
                    if len(journals) > 0:
                        progress.status = ScraperStatus.COMPLETED
                        progress.add_log("success", f"{current_site.upper()} scraper tamamlandı")
                        logger.success(f"[RoundRobin] {current_site.upper()} scraper tamamlandı!")
                    else:
                        logger.warning(f"[RoundRobin] {current_site.upper()} için journal bulunamadı, atlanıyor...")
                    
                    # Driver'ı kapat
                    if scrapers[current_site]:
                        try:
                            scrapers[current_site].close()
                        except:
                            pass
                        scrapers[current_site] = None
                    
                    # Tüm siteler tamamlandı mı kontrol et
                    all_completed = all(
                        site_journals.get(s) is not None and site_indices.get(s, 0) >= len(site_journals.get(s, []))
                        for s in sites
                    )
                    
                    if not all_completed:
                        # Sonraki siteye geç
                        current_site_idx = (current_site_idx + 1) % len(sites)
                    continue
                
                # Bu turda işlenecek journal sayısı
                end_idx = min(start_idx + self.round_robin_journals_per_switch, len(journals))
                journals_to_process = journals[start_idx:end_idx]
                
                logger.info(f"[RoundRobin] {current_site.upper()}: {len(journals_to_process)} journal işlenecek ({start_idx+1}-{end_idx}/{len(journals)})")
                progress.add_log("info", f"{len(journals_to_process)} journal işlenecek ({start_idx+1}-{end_idx})")
                
                scraper = scrapers[current_site]
                max_articles = self.ieee_max_articles if current_site == 'ieee' else self.sciencedirect_max_articles if current_site == 'sciencedirect' else self.acm_max_articles
                
                # Bu turdaki journal'ları işle
                for i, journal in enumerate(journals_to_process):
                    # Stop kontrolü
                    if self._round_robin_stop_flag.is_set():
                        logger.warning("[RoundRobin] Durduruldu")
                        progress.status = ScraperStatus.STOPPED
                        other_progress.status = ScraperStatus.STOPPED
                        break
                    
                    global_idx = start_idx + i
                    journal_name = journal.get('name', 'Unknown')
                    progress.current_journal = journal_name
                    progress.current_journal_index = global_idx + 1
                    progress.last_activity = datetime.utcnow()
                    
                    logger.info(f"[RoundRobin] [{current_site.upper()}] [{global_idx+1}/{len(journals)}] {journal_name} işleniyor...")
                    
                    try:
                        # Makale topla
                        articles = scraper.scrape_journal_articles(journal, max_articles=max_articles)
                        
                        # Makale olsun olmasın journal'ı veritabanına kaydet
                        # Bu sayede bir sonraki çalışmada tekrar kontrol edilmez
                        if self._db_service and self._loop:
                            # Veritabanına kaydet
                            journal_info = {
                                'name': journal.get('name'),
                                'url': journal.get('url'),
                                'publisher': 'IEEE' if current_site == 'ieee' else 'Elsevier' if current_site == 'sciencedirect' else 'ACM',
                                'open_access': journal.get('open_access', False),
                            }
                            if current_site == 'sciencedirect':
                                journal_info['letter_group'] = journal.get('letter_group')
                            
                            issue_data = {
                                'issue_number': journal.get('issue_number'),
                                'date': journal.get('issue_date'),
                                'url': journal.get('issue_url'),
                            }
                            
                            future = asyncio.run_coroutine_threadsafe(
                                self._db_service.add_journal_with_issue_and_articles(
                                    journal_data=journal_info,
                                    issue_data=issue_data,
                                    articles_data=articles or [],  # Boş liste olabilir
                                    source_website=source_websites[current_site]
                                ),
                                self._loop
                            )
                            result = future.result(timeout=30)
                            
                            progress.journals_scraped += 1
                            if result.get('issue_created'):
                                progress.issues_scraped += 1
                            progress.articles_scraped += result.get('articles_created', 0)
                            progress.articles_updated += result.get('articles_updated', 0)
                            
                            if articles:
                                progress.add_log("success", f"{journal_name}: {result.get('articles_created', 0)} makale eklendi")
                                logger.success(f"[RoundRobin] {journal_name}: {result.get('articles_created', 0)} makale eklendi")
                            else:
                                progress.add_log("info", f"{journal_name}: Makale yok, journal kaydedildi")
                                logger.info(f"[RoundRobin] {journal_name}: Makale yok, journal kaydedildi")
                        
                    except Exception as e:
                        progress.errors_count += 1
                        progress.last_error = str(e)
                        progress.add_log("error", f"{journal_name}: {str(e)}")
                        logger.error(f"[RoundRobin] {journal_name} hatası: {e}")
                    
                    # Rate limiting
                    time.sleep(2)
                
                # Index'i güncelle
                site_indices[current_site] = end_idx
                
                # Stop kontrolü
                if self._round_robin_stop_flag.is_set():
                    break
                
                # Driver'ı kapat ve sonraki siteye geç
                logger.info(f"[RoundRobin] {current_site.upper()} driver kapatılıyor, sonraki siteye geçiliyor...")
                progress.add_log("info", "Driver kapatılıyor, site değiştiriliyor...")
                
                if scrapers[current_site]:
                    try:
                        scrapers[current_site].close()
                    except:
                        pass
                    scrapers[current_site] = None
                
                # Kısa bekleme
                time.sleep(2)
                
                # Sonraki siteye geç
                current_site_idx = (current_site_idx + 1) % len(sites)
            
            logger.success("[RoundRobin] Tüm siteler tamamlandı!")
            
        except Exception as e:
            logger.error(f"[RoundRobin] Fatal error: {e}")
            import traceback
            traceback.print_exc()
            
            # Tüm progress'leri error olarak işaretle
            self.ieee_progress.status = ScraperStatus.ERROR
            self.ieee_progress.last_error = str(e)
            self.sciencedirect_progress.status = ScraperStatus.ERROR
            self.sciencedirect_progress.last_error = str(e)
            self.acm_progress.status = ScraperStatus.ERROR
            self.acm_progress.last_error = str(e)
        
        finally:
            # Tüm açık scraper'ları kapat
            for site, scraper in scrapers.items():
                if scraper:
                    try:
                        scraper.close()
                    except:
                        pass
            
            self.ieee_progress.last_activity = datetime.utcnow()
            self.sciencedirect_progress.last_activity = datetime.utcnow()
            self.acm_progress.last_activity = datetime.utcnow()
    
    async def stop_round_robin(self) -> bool:
        """Round Robin scraper'ı durdur"""
        self._round_robin_stop_flag.set()
        
        if self._round_robin_future:
            try:
                self._round_robin_future.result(timeout=15)
            except concurrent.futures.TimeoutError:
                logger.warning("Round Robin scraper stop timeout")
            except Exception:
                pass
        
        return True
    
    async def stop_all(self) -> Dict[str, bool]:
        """Tüm scraper'ları durdur"""
        results = {}
        results['ieee'] = await self.stop_ieee()
        results['sciencedirect'] = await self.stop_sciencedirect()
        results['acm'] = await self.stop_acm()
        results['round_robin'] = await self.stop_round_robin()
        return results
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Database istatistikleri"""
        if self._db_service:
            return await self._db_service.get_statistics()
        return {}
