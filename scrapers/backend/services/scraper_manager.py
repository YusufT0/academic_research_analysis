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

logger = get_logger('scraper_manager')

# Pre-import scraper modules to avoid GIL deadlock in threads
# Bu import'lar thread başlamadan önce yapılır
logger.info("Scraper modülleri yükleniyor...")
try:
    from ieee_xplore.scraper import IEEEXploreScraper, ScraperStoppedException as IEEEScraperStoppedException
    from science_direct.scraper import ScienceDirectScraper, ScraperStoppedException as SDScraperStoppedException
    from acm.scraper import ACMScraper, ScraperStoppedException as ACMScraperStoppedException
    # Birleşik exception - her scraper için de kullanılabilir
    ScraperStoppedException = (IEEEScraperStoppedException, SDScraperStoppedException, ACMScraperStoppedException)
    logger.success("Scraper modülleri yüklendi")
except Exception as e:
    logger.error(f"Scraper modülleri yüklenemedi: {e}")
    IEEEXploreScraper = None
    ScienceDirectScraper = None
    ACMScraper = None
    ScraperStoppedException = Exception  # Fallback


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

        # Makale ilerleme
        self.article_list: List[str] = []           # Mevcut journal'ın makale başlıkları (ön bilgi)
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
        # Son 100 log'u tut
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]
        
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
        }
    
    def reset(self):
        """Durumu sıfırla"""
        self.status = ScraperStatus.IDLE
        self.current_journal = None
        self.current_journal_index = 0
        self.pending_journals = []
        self.completed_journals = []
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
        
        # Track UI-facing metric changes to keep the frontend progress bar fluid
        if name in ('current_journal_index', 'current_article_index', 'article_list', 'journals_scraped', 'articles_scraped', 'articles_updated', 'errors_count'):
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
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="scraper")
        
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
        
        # Database service
        self._db_service: Optional[DatabaseService] = None
        
        # Event loop reference for async database calls from threads
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Settings
        self.ieee_headless = True
        self.ieee_max_articles = 100
        self.sciencedirect_headless = True
        self.sciencedirect_max_articles = 100
        self.acm_headless = True
        self.acm_max_articles = 100
        
        # Round Robin Settings
        self.round_robin_journals_per_switch = 3
        
        # Round Robin State
        self._round_robin_future: Optional[concurrent.futures.Future] = None
        self._round_robin_stop_flag = threading.Event()
    
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
        
        return logs[:limit]
    
    # ==================== IEEE Scraper ====================
    
    async def start_ieee(self, headless: bool = True, max_articles: int = 100) -> bool:
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

        # Reset flags
        self._ieee_stop_flag.clear()
        self._ieee_pause_flag.clear()

        # Thread'de başlat - event loop'u bloklamaz
        self._ieee_future = self._executor.submit(self._run_ieee_scraper_sync)
        logger.info("IEEE scraper thread'de başlatıldı")

        return True
    
    def _run_ieee_scraper_sync(self):
        """
        IEEE scraper'ı senkron olarak çalıştır (ayrı thread'de).
        Bu metod thread pool'da çalışır ve main event loop'u bloklamaz.
        """
        progress = self.ieee_progress
        progress.reset()
        progress.status = ScraperStatus.STARTING
        progress.started_at = datetime.utcnow()
        progress.add_log("info", "IEEE scraper başlatılıyor (ayrı thread)...")
        logger.info("[IEEE Thread] Scraper başlatılıyor...")
        logger.info(f"[IEEE Thread] Headless: {self.ieee_headless}")
        print(f"[IEEE Thread] Başlatılıyor, headless={self.ieee_headless}", flush=True)
        
        scraper = None
        
        try:
            # Scraper zaten import edildi (modül başında)
            if IEEEXploreScraper is None:
                raise Exception("IEEE scraper modülü yüklenemedi")
            
            # Create and initialize
            logger.info("[IEEE Thread] Browser başlatılıyor...")
            print("[IEEE Thread] Browser başlatılıyor...", flush=True)
            scraper = IEEEXploreScraper(headless=self.ieee_headless, stop_flag=self._ieee_stop_flag)
            print("[IEEE Thread] Scraper oluşturuldu, initialize ediliyor...", flush=True)
            scraper.initialize()
            print("[IEEE Thread] Browser başlatıldı!", flush=True)
            
            progress.status = ScraperStatus.RUNNING
            progress.add_log("info", "Browser başlatıldı")
            logger.success("[IEEE Thread] Browser başlatıldı")
            
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
                
                # Pause check
                while self._ieee_pause_flag.is_set():
                    progress.status = ScraperStatus.PAUSED
                    import time
                    time.sleep(1)
                
                if progress.status == ScraperStatus.PAUSED:
                    progress.status = ScraperStatus.RUNNING
                
                journal_name = journal.get('name', 'Unknown')
                progress.current_journal = journal_name
                progress.current_journal_index = idx + 1
                progress.pending_journals = [j.get('name', '') for j in all_journals[idx + 1:]]
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

                try:
                    import time
                    scrape_start_t = time.time()
                    # Scrape articles
                    articles = scraper.scrape_journal_articles(journal, max_articles=self.ieee_max_articles, article_progress_callback=_ieee_article_cb, article_list_callback=_ieee_article_list_cb)
                    
                    try:
                        from backend.core.metrics import SCRAPER_DURATION
                        SCRAPER_DURATION.labels(source="ieee").observe(time.time() - scrape_start_t)
                    except ImportError:
                        pass
                    
                    # Makale olsun olmasın journal'ı veritabanına kaydet
                    # Bu sayede bir sonraki çalışmada tekrar kontrol edilmez
                    if self._db_service and self._loop:
                        # Save to database (async call from thread)
                        journal_info = {
                            'name': journal.get('name'),
                            'url': journal.get('url'),
                            'publisher': 'IEEE',
                            'open_access': journal.get('open_access', False),
                        }
                        
                        issue_data = {
                            'issue_number': journal.get('issue_number'),
                            'date': journal.get('issue_date'),
                            'url': journal.get('issue_url'),
                        }
                        
                        # Run async database call from thread
                        future = asyncio.run_coroutine_threadsafe(
                            self._db_service.add_journal_with_issue_and_articles(
                                journal_data=journal_info,
                                issue_data=issue_data,
                                articles_data=articles or [],  # Boş liste olabilir
                                source_website='ieeexplore'
                            ),
                            self._loop
                        )
                        result = future.result(timeout=30)  # 30 saniye timeout

                        articles_created = result.get('articles_created', 0)
                        progress.completed_journals.append({
                            'name': journal_name,
                            'articles_count': articles_created,
                            'article_list': progress.article_list.copy(),
                        })
                        progress.journals_scraped += 1
                        if result.get('issue_created'):
                            progress.issues_scraped += 1
                        progress.articles_scraped += articles_created
                        progress.articles_updated += result.get('articles_updated', 0)

                        if articles:
                            progress.add_log("success", f"{journal.get('name')}: {articles_created} makale eklendi")
                            logger.success(f"[IEEE Thread] {journal_name}: {articles_created} makale eklendi")
                        else:
                            progress.add_log("info", f"{journal.get('name')}: Makale yok, journal kaydedildi")
                            logger.info(f"[IEEE Thread] {journal_name}: Makale yok, journal kaydedildi")
                    
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
            
            if progress.status == ScraperStatus.RUNNING:
                progress.status = ScraperStatus.COMPLETED
                progress.add_log("success", "IEEE scraper tamamlandı")
                logger.success("[IEEE Thread] Scraper tamamlandı")
        
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
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            progress.last_activity = datetime.utcnow()
            # Distributed lock'u bırak
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    DistributedScraperLock.release("ieee"), self._loop
                )

    async def stop_ieee(self) -> bool:
        """IEEE scraper'ı durdur"""
        if self.ieee_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False
        
        logger.info("IEEE scraper durduruluyor...")
        self._ieee_stop_flag.set()
        self.ieee_progress.status = ScraperStatus.STOPPING
        self.ieee_progress.add_log("warning", "Durdurma sinyali gönderildi")
        
        if self._ieee_future:
            try:
                # Thread'in bitmesini bekle (max 15 saniye - browser kapanması için yeterli)
                self._ieee_future.result(timeout=15)
                logger.success("IEEE scraper düzgün şekilde durduruldu")
            except concurrent.futures.TimeoutError:
                logger.warning("IEEE scraper stop timeout - browser kapanmayı bekliyor olabilir")
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
    
    async def start_sciencedirect(self, headless: bool = True, max_articles: int = 100) -> bool:
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

        # Reset flags
        self._sciencedirect_stop_flag.clear()
        self._sciencedirect_pause_flag.clear()

        # Thread'de başlat - event loop'u bloklamaz
        self._sciencedirect_future = self._executor.submit(self._run_sciencedirect_scraper_sync)
        logger.info("ScienceDirect scraper thread'de başlatıldı")

        return True
    
    def _run_sciencedirect_scraper_sync(self):
        """
        ScienceDirect scraper'ı senkron olarak çalıştır (ayrı thread'de).
        Bu metod thread pool'da çalışır ve main event loop'u bloklamaz.
        """
        progress = self.sciencedirect_progress
        progress.reset()
        progress.status = ScraperStatus.STARTING
        progress.started_at = datetime.utcnow()
        progress.add_log("info", "ScienceDirect scraper başlatılıyor (ayrı thread)...")
        logger.info("[SD Thread] Scraper başlatılıyor...")
        logger.info(f"[SD Thread] Headless: {self.sciencedirect_headless}")
        print(f"[SD Thread] Başlatılıyor, headless={self.sciencedirect_headless}", flush=True)
        
        scraper = None
        
        try:
            # Scraper zaten import edildi (modül başında)
            if ScienceDirectScraper is None:
                raise Exception("ScienceDirect scraper modülü yüklenemedi")
            
            # Create and initialize
            logger.info("[SD Thread] Browser başlatılıyor...")
            print("[SD Thread] Browser başlatılıyor...", flush=True)
            scraper = ScienceDirectScraper(headless=self.sciencedirect_headless, stop_flag=self._sciencedirect_stop_flag)
            print("[SD Thread] Scraper oluşturuldu, initialize ediliyor...", flush=True)
            scraper.initialize()
            print("[SD Thread] Browser başlatıldı!", flush=True)
            
            progress.status = ScraperStatus.RUNNING
            progress.add_log("info", "Browser başlatıldı")
            logger.success("[SD Thread] Browser başlatıldı")
            
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
                
                # Pause check
                while self._sciencedirect_pause_flag.is_set():
                    progress.status = ScraperStatus.PAUSED
                    import time
                    time.sleep(1)
                
                if progress.status == ScraperStatus.PAUSED:
                    progress.status = ScraperStatus.RUNNING
                
                journal_name = journal.get('name', 'Unknown')
                progress.current_journal = journal_name
                progress.current_journal_index = idx + 1
                progress.pending_journals = [j.get('name', '') for j in all_journals[idx + 1:]]
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

                try:
                    import time
                    scrape_start_t = time.time()
                    # Scrape articles
                    articles = scraper.scrape_journal_articles(journal, max_articles=self.sciencedirect_max_articles, article_progress_callback=_sd_article_cb, article_list_callback=_sd_article_list_cb)
                    
                    try:
                        from backend.core.metrics import SCRAPER_DURATION
                        SCRAPER_DURATION.labels(source="sciencedirect").observe(time.time() - scrape_start_t)
                    except ImportError:
                        pass
                    
                    # Makale olsun olmasın journal'ı veritabanına kaydet
                    # Bu sayede bir sonraki çalışmada tekrar kontrol edilmez
                    if self._db_service and self._loop:
                        # Save to database (async call from thread)
                        journal_info = {
                            'name': journal.get('name'),
                            'url': journal.get('url'),
                            'publisher': 'Elsevier',
                            'open_access': journal.get('open_access', False),
                            'letter_group': journal.get('letter_group'),
                        }
                        
                        issue_data = {
                            'issue_number': journal.get('issue_number'),
                            'date': journal.get('issue_date'),
                            'url': journal.get('issue_url'),
                        }
                        
                        # Run async database call from thread
                        future = asyncio.run_coroutine_threadsafe(
                            self._db_service.add_journal_with_issue_and_articles(
                                journal_data=journal_info,
                                issue_data=issue_data,
                                articles_data=articles or [],  # Boş liste olabilir
                                source_website='sciencedirect'
                            ),
                            self._loop
                        )
                        result = future.result(timeout=30)  # 30 saniye timeout

                        articles_created = result.get('articles_created', 0)
                        progress.completed_journals.append({
                            'name': journal_name,
                            'articles_count': articles_created,
                            'article_list': progress.article_list.copy(),
                        })
                        progress.journals_scraped += 1
                        if result.get('issue_created'):
                            progress.issues_scraped += 1
                        progress.articles_scraped += articles_created
                        progress.articles_updated += result.get('articles_updated', 0)

                        if articles:
                            progress.add_log("success", f"{journal.get('name')}: {articles_created} makale eklendi")
                            logger.success(f"[SD Thread] {journal_name}: {articles_created} makale eklendi")
                        else:
                            progress.add_log("info", f"{journal.get('name')}: Makale yok, journal kaydedildi")
                            logger.info(f"[SD Thread] {journal_name}: Makale yok, journal kaydedildi")
                    
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
            
            if progress.status == ScraperStatus.RUNNING:
                progress.status = ScraperStatus.COMPLETED
                progress.add_log("success", "ScienceDirect scraper tamamlandı")
                logger.success("[SD Thread] Scraper tamamlandı")
        
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
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            progress.last_activity = datetime.utcnow()
            # Distributed lock'u bırak
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    DistributedScraperLock.release("sciencedirect"), self._loop
                )

    async def stop_sciencedirect(self) -> bool:
        """ScienceDirect scraper'ı durdur"""
        if self.sciencedirect_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False
        
        logger.info("ScienceDirect scraper durduruluyor...")
        self._sciencedirect_stop_flag.set()
        self.sciencedirect_progress.status = ScraperStatus.STOPPING
        self.sciencedirect_progress.add_log("warning", "Durdurma sinyali gönderildi")
        
        if self._sciencedirect_future:
            try:
                # Thread'in bitmesini bekle (max 15 saniye - browser kapanması için yeterli)
                self._sciencedirect_future.result(timeout=15)
                logger.success("ScienceDirect scraper düzgün şekilde durduruldu")
            except concurrent.futures.TimeoutError:
                logger.warning("ScienceDirect scraper stop timeout - browser kapanmayı bekliyor olabilir")
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
    
    async def start_acm(self, headless: bool = True, max_articles: int = 100) -> bool:
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

        # Reset flags
        self._acm_stop_flag.clear()
        self._acm_pause_flag.clear()

        # Thread'de başlat - event loop'u bloklamaz
        self._acm_future = self._executor.submit(self._run_acm_scraper_sync)
        logger.info("ACM scraper thread'de başlatıldı")

        return True
    
    def _run_acm_scraper_sync(self):
        """
        ACM scraper'ı senkron olarak çalıştır (ayrı thread'de).
        Bu metod thread pool'da çalışır ve main event loop'u bloklamaz.
        """
        progress = self.acm_progress
        progress.reset()
        progress.status = ScraperStatus.STARTING
        progress.started_at = datetime.utcnow()
        progress.add_log("info", "ACM scraper başlatılıyor (ayrı thread)...")
        logger.info("[ACM Thread] Scraper başlatılıyor...")
        logger.info(f"[ACM Thread] Headless: {self.acm_headless}")
        print(f"[ACM Thread] Başlatılıyor, headless={self.acm_headless}", flush=True)
        
        scraper = None
        
        try:
            # Scraper zaten import edildi (modül başında)
            if ACMScraper is None:
                raise Exception("ACM scraper modülü yüklenemedi")
            
            # Create and initialize
            logger.info("[ACM Thread] Browser başlatılıyor...")
            print("[ACM Thread] Browser başlatılıyor...", flush=True)
            scraper = ACMScraper(headless=self.acm_headless, stop_flag=self._acm_stop_flag)
            print("[ACM Thread] Scraper oluşturuldu, initialize ediliyor...", flush=True)
            scraper.initialize()
            print("[ACM Thread] Browser başlatıldı!", flush=True)
            
            progress.status = ScraperStatus.RUNNING
            progress.add_log("info", "Browser başlatıldı")
            logger.success("[ACM Thread] Browser başlatıldı")
            
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
                
                # Pause check
                while self._acm_pause_flag.is_set():
                    progress.status = ScraperStatus.PAUSED
                    import time
                    time.sleep(1)
                
                if progress.status == ScraperStatus.PAUSED:
                    progress.status = ScraperStatus.RUNNING
                
                journal_name = journal.get('name', 'Unknown')
                progress.current_journal = journal_name
                progress.current_journal_index = idx + 1
                progress.pending_journals = [j.get('name', '') for j in all_journals[idx + 1:]]
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

                try:
                    import time
                    scrape_start_t = time.time()
                    # Scrape articles
                    articles = scraper.scrape_journal_articles(journal, max_articles=self.acm_max_articles, article_progress_callback=_acm_article_cb, article_list_callback=_acm_article_list_cb)
                    
                    try:
                        from backend.core.metrics import SCRAPER_DURATION
                        SCRAPER_DURATION.labels(source="acm").observe(time.time() - scrape_start_t)
                    except ImportError:
                        pass
                    
                    # Makale olsun olmasın journal'ı veritabanına kaydet
                    # Bu sayede bir sonraki çalışmada tekrar kontrol edilmez
                    if self._db_service and self._loop:
                        # Save to database (async call from thread)
                        journal_info = {
                            'name': journal.get('name'),
                            'url': journal.get('url'),
                            'publisher': 'ACM',
                            'open_access': journal.get('open_access', False),
                        }
                        
                        issue_data = {
                            'issue_number': journal.get('issue_number'),
                            'date': journal.get('issue_date'),
                            'url': journal.get('issue_url'),
                        }
                        
                        # Run async database call from thread
                        future = asyncio.run_coroutine_threadsafe(
                            self._db_service.add_journal_with_issue_and_articles(
                                journal_data=journal_info,
                                issue_data=issue_data,
                                articles_data=articles or [],  # Boş liste olabilir
                                source_website='acm'
                            ),
                            self._loop
                        )
                        result = future.result(timeout=30)  # 30 saniye timeout

                        articles_created = result.get('articles_created', 0)
                        progress.completed_journals.append({
                            'name': journal_name,
                            'articles_count': articles_created,
                            'article_list': progress.article_list.copy(),
                        })
                        progress.journals_scraped += 1
                        if result.get('issue_created'):
                            progress.issues_scraped += 1
                        progress.articles_scraped += articles_created
                        progress.articles_updated += result.get('articles_updated', 0)

                        if articles:
                            progress.add_log("success", f"{journal.get('name')}: {articles_created} makale eklendi")
                            logger.success(f"[ACM Thread] {journal_name}: {articles_created} makale eklendi")
                        else:
                            progress.add_log("info", f"{journal.get('name')}: Makale yok, journal kaydedildi")
                            logger.info(f"[ACM Thread] {journal_name}: Makale yok, journal kaydedildi")
                    
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
            
            if progress.status == ScraperStatus.RUNNING:
                progress.status = ScraperStatus.COMPLETED
                progress.add_log("success", "ACM scraper tamamlandı")
                logger.success("[ACM Thread] Scraper tamamlandı")
        
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
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            progress.last_activity = datetime.utcnow()
            # Distributed lock'u bırak
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    DistributedScraperLock.release("acm"), self._loop
                )

    async def stop_acm(self) -> bool:
        """ACM scraper'ı durdur"""
        if self.acm_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False
        
        logger.info("ACM scraper durduruluyor...")
        self._acm_stop_flag.set()
        self.acm_progress.status = ScraperStatus.STOPPING
        self.acm_progress.add_log("warning", "Durdurma sinyali gönderildi")
        
        if self._acm_future:
            try:
                # Thread'in bitmesini bekle (max 15 saniye - browser kapanması için yeterli)
                self._acm_future.result(timeout=15)
                logger.success("ACM scraper düzgün şekilde durduruldu")
            except concurrent.futures.TimeoutError:
                logger.warning("ACM scraper stop timeout - browser kapanmayı bekliyor olabilir")
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
            results['ieee'] = await self.start_ieee(headless=headless, max_articles=self.ieee_max_articles)
        else:
            results['ieee'] = False
            logger.info("IEEE scraper devre dışı, atlanıyor...")
        
        # 5 saniye bekle - chromedriver dosya çakışmasını önlemek için
        if ieee_enabled and sd_enabled:
            logger.info("ScienceDirect için 5 saniye bekleniyor (chromedriver çakışmasını önlemek için)...")
            await asyncio.sleep(5)
        
        # ScienceDirect'i başlat (etkinse)
        if sd_enabled:
            results['sciencedirect'] = await self.start_sciencedirect(headless=headless, max_articles=self.sciencedirect_max_articles)
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
            results['ieee'] = await self.start_ieee(headless=headless, max_articles=self.ieee_max_articles)
            
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
            results['sciencedirect'] = await self.start_sciencedirect(headless=headless, max_articles=self.sciencedirect_max_articles)
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
                        # Scraper'ı oluştur ve başlat
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
