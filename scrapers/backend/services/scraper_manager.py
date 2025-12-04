"""
Scraper Manager Service

IEEE ve ScienceDirect scraper'larını yönetir.
Background task olarak çalıştırır, durum takibi yapar.

Scraper'lar ayrı thread'lerde çalışır - Selenium senkron kod içerdiğinden
asyncio event loop'unu bloklamaz.
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
from utils.logger import get_logger

logger = get_logger('scraper_manager')

# Pre-import scraper modules to avoid GIL deadlock in threads
# Bu import'lar thread başlamadan önce yapılır
logger.info("Scraper modülleri yükleniyor...")
try:
    from ieee_xplore.scraper import IEEEXploreScraper
    from science_direct.scraper import ScienceDirectScraper
    logger.success("Scraper modülleri yüklendi")
except Exception as e:
    logger.error(f"Scraper modülleri yüklenemedi: {e}")
    IEEEXploreScraper = None
    ScienceDirectScraper = None


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
        self.status = ScraperStatus.IDLE
        
        # İlerleme
        self.current_journal: Optional[str] = None
        self.current_journal_index: int = 0
        self.total_journals: int = 0
        
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e çevir"""
        return {
            "scraper_type": self.scraper_type,
            "status": self.status.value,
            "current_journal": self.current_journal,
            "current_journal_index": self.current_journal_index,
            "total_journals": self.total_journals,
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
        
        # Thread executor - scraper'lar için ayrı thread pool
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="scraper")
        
        # Futures
        self._ieee_future: Optional[concurrent.futures.Future] = None
        self._sciencedirect_future: Optional[concurrent.futures.Future] = None
        
        # Stop flags (thread-safe)
        self._ieee_stop_flag = threading.Event()
        self._sciencedirect_stop_flag = threading.Event()
        
        # Pause flags (thread-safe)
        self._ieee_pause_flag = threading.Event()
        self._sciencedirect_pause_flag = threading.Event()
        
        # Database service
        self._db_service: Optional[DatabaseService] = None
        
        # Event loop reference for async database calls from threads
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Settings
        self.ieee_headless = True
        self.ieee_max_articles = 10
        self.sciencedirect_headless = True
        self.sciencedirect_max_articles = 5
    
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
    
    def get_all_status(self) -> Dict[str, Any]:
        """Tüm scraper'ların durumu"""
        ieee = self.get_ieee_status()
        sd = self.get_sciencedirect_status()
        
        any_running = (
            self.ieee_progress.status == ScraperStatus.RUNNING or
            self.sciencedirect_progress.status == ScraperStatus.RUNNING
        )
        
        all_completed = (
            self.ieee_progress.status == ScraperStatus.COMPLETED and
            self.sciencedirect_progress.status == ScraperStatus.COMPLETED
        )
        
        return {
            "ieee": ieee,
            "sciencedirect": sd,
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
        
        # Timestamp'e göre sırala
        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return logs[:limit]
    
    # ==================== IEEE Scraper ====================
    
    async def start_ieee(self, headless: bool = True, max_articles: int = 10) -> bool:
        """IEEE scraper'ı başlat (ayrı thread'de)"""
        if self.ieee_progress.status == ScraperStatus.RUNNING:
            logger.warning("IEEE scraper already running")
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
            scraper = IEEEXploreScraper(headless=self.ieee_headless)
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
                progress.last_activity = datetime.utcnow()
                
                logger.info(f"[IEEE Thread] [{idx+1}/{len(all_journals)}] {journal_name} işleniyor...")
                
                try:
                    # Scrape articles
                    articles = scraper.scrape_journal_articles(journal, max_articles=self.ieee_max_articles)
                    
                    if articles and self._db_service and self._loop:
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
                                articles_data=articles,
                                source_website='ieeexplore'
                            ),
                            self._loop
                        )
                        result = future.result(timeout=30)  # 30 saniye timeout
                        
                        progress.journals_scraped += 1
                        if result.get('issue_created'):
                            progress.issues_scraped += 1
                        progress.articles_scraped += result.get('articles_created', 0)
                        progress.articles_updated += result.get('articles_updated', 0)
                        
                        progress.add_log("success", f"{journal.get('name')}: {result.get('articles_created', 0)} makale eklendi")
                        logger.success(f"[IEEE Thread] {journal_name}: {result.get('articles_created', 0)} makale eklendi")
                    
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
    
    async def stop_ieee(self) -> bool:
        """IEEE scraper'ı durdur"""
        if self.ieee_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False
        
        self._ieee_stop_flag.set()
        self.ieee_progress.status = ScraperStatus.STOPPING
        
        if self._ieee_future:
            try:
                # Thread'in bitmesini bekle (max 10 saniye)
                self._ieee_future.result(timeout=10)
            except concurrent.futures.TimeoutError:
                logger.warning("IEEE scraper stop timeout")
            except Exception:
                pass
        
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
    
    async def start_sciencedirect(self, headless: bool = True, max_articles: int = 5) -> bool:
        """ScienceDirect scraper'ı başlat (ayrı thread'de)"""
        if self.sciencedirect_progress.status == ScraperStatus.RUNNING:
            logger.warning("ScienceDirect scraper already running")
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
            scraper = ScienceDirectScraper(headless=self.sciencedirect_headless)
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
                progress.last_activity = datetime.utcnow()
                
                logger.info(f"[SD Thread] [{idx+1}/{len(all_journals)}] {journal_name} işleniyor...")
                
                try:
                    # Scrape articles
                    articles = scraper.scrape_journal_articles(journal, max_articles=self.sciencedirect_max_articles)
                    
                    if articles and self._db_service and self._loop:
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
                                articles_data=articles,
                                source_website='sciencedirect'
                            ),
                            self._loop
                        )
                        result = future.result(timeout=30)  # 30 saniye timeout
                        
                        progress.journals_scraped += 1
                        if result.get('issue_created'):
                            progress.issues_scraped += 1
                        progress.articles_scraped += result.get('articles_created', 0)
                        progress.articles_updated += result.get('articles_updated', 0)
                        
                        progress.add_log("success", f"{journal.get('name')}: {result.get('articles_created', 0)} makale eklendi")
                        logger.success(f"[SD Thread] {journal_name}: {result.get('articles_created', 0)} makale eklendi")
                    
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
    
    async def stop_sciencedirect(self) -> bool:
        """ScienceDirect scraper'ı durdur"""
        if self.sciencedirect_progress.status not in [ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            return False
        
        self._sciencedirect_stop_flag.set()
        self.sciencedirect_progress.status = ScraperStatus.STOPPING
        
        if self._sciencedirect_future:
            try:
                # Thread'in bitmesini bekle (max 10 saniye)
                self._sciencedirect_future.result(timeout=10)
            except concurrent.futures.TimeoutError:
                logger.warning("ScienceDirect scraper stop timeout")
            except Exception:
                pass
        
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
    
    # ==================== All Scrapers ====================
    
    async def start_all(self, headless: bool = True) -> Dict[str, bool]:
        """
        Tüm scraper'ları PARALEL modda başlat.
        Scraper'lar 5 saniye arayla başlar ve aynı anda çalışır.
        """
        import asyncio
        
        results = {}
        
        logger.info("PARALEL mod: Scraper'lar aynı anda çalışacak")
        
        # Önce IEEE'yi başlat
        results['ieee'] = await self.start_ieee(headless=headless, max_articles=self.ieee_max_articles)
        
        # 5 saniye bekle - chromedriver dosya çakışmasını önlemek için
        logger.info("ScienceDirect için 5 saniye bekleniyor (chromedriver çakışmasını önlemek için)...")
        await asyncio.sleep(5)
        
        # Sonra ScienceDirect'i başlat
        results['sciencedirect'] = await self.start_sciencedirect(headless=headless, max_articles=self.sciencedirect_max_articles)
        
        return results
    
    async def start_all_sequential(self, headless: bool = True) -> Dict[str, bool]:
        """
        Tüm scraper'ları SIRALI modda başlat.
        Önce IEEE tamamlanır, sonra ScienceDirect başlar.
        """
        import asyncio
        
        results = {}
        
        logger.info("SIRALI mod: IEEE bitince ScienceDirect başlayacak")
        
        # Önce IEEE'yi başlat
        results['ieee'] = await self.start_ieee(headless=headless, max_articles=self.ieee_max_articles)
        
        # IEEE'nin bitmesini bekle
        logger.info("IEEE scraper'ın bitmesi bekleniyor...")
        while self.ieee_progress.status in [ScraperStatus.STARTING, ScraperStatus.RUNNING, ScraperStatus.PAUSED]:
            await asyncio.sleep(2)
        
        logger.info(f"IEEE scraper tamamlandı (status: {self.ieee_progress.status.value})")
        
        # 3 saniye bekle
        await asyncio.sleep(3)
        
        # Şimdi ScienceDirect'i başlat
        logger.info("ScienceDirect scraper başlatılıyor...")
        results['sciencedirect'] = await self.start_sciencedirect(headless=headless, max_articles=self.sciencedirect_max_articles)
        
        return results
    
    async def stop_all(self) -> Dict[str, bool]:
        """Tüm scraper'ları durdur"""
        results = {}
        results['ieee'] = await self.stop_ieee()
        results['sciencedirect'] = await self.stop_sciencedirect()
        return results
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Database istatistikleri"""
        if self._db_service:
            return await self._db_service.get_statistics()
        return {}
