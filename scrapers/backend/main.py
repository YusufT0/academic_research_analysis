"""
Academic Research Scraper API

FastAPI backend for managing IEEE and ScienceDirect scrapers.
"""

import sys
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

# Path setup
backend_path = Path(__file__).parent
scrapers_path = backend_path.parent
sys.path.insert(0, str(scrapers_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.dependencies import set_scraper_manager
from .services.scraper_manager import ScraperManager
from .routers import (
    journals_router,
    issues_router,
    articles_router,
    scrapers_router,
    stats_router,
)

from database import init_database, close_database
from utils.logger import get_logger

logger = get_logger('api')


# Scraper manager global instance
scraper_manager: ScraperManager = None


async def delayed_scraper_start(manager: ScraperManager, delay: float = 2.0):
    """
    Backend startup tamamlandıktan sonra scraper'ları başlat.
    Bu fonksiyon background'da çalışır ve API'yi bloklamaz.
    """
    await asyncio.sleep(delay)  # Backend'in tamamen hazır olmasını bekle
    logger.info("Otomatik scraper başlatma aktif, scraper'lar başlatılıyor...")
    logger.info(f"Headless mode: {settings.scraper_headless}")
    logger.info(f"Run mode: {settings.scraper_run_mode}")
    logger.info(f"Enabled scrapers: {settings.enabled_scrapers}")
    logger.info(f"IEEE enabled: {settings.ieee_enabled}")
    logger.info(f"ScienceDirect enabled: {settings.sciencedirect_enabled}")
    logger.info(f"IEEE max articles: {settings.ieee_max_articles}")
    logger.info(f"ScienceDirect max articles: {settings.sciencedirect_max_articles}")
    
    # Enabled scrapers kontrolü
    ieee_enabled = settings.ieee_enabled
    sd_enabled = settings.sciencedirect_enabled
    
    if not ieee_enabled and not sd_enabled:
        logger.warning("Hiçbir scraper etkin değil! ENABLED_SCRAPERS ayarını kontrol edin.")
        return
    
    if settings.scraper_run_mode == "sequential":
        # Sıralı mod: Önce IEEE bitsin, sonra ScienceDirect başlasın
        await manager.start_all_sequential(
            headless=settings.scraper_headless,
            ieee_enabled=ieee_enabled,
            sd_enabled=sd_enabled
        )
    elif settings.scraper_run_mode == "round_robin":
        # Round Robin mod: Her X journal'da bir site değiştirilir
        journals_per_switch = settings.round_robin_journals_per_switch
        logger.info(f"Round Robin journals per switch: {journals_per_switch}")
        await manager.start_all_round_robin(
            headless=settings.scraper_headless, 
            journals_per_switch=journals_per_switch,
            ieee_enabled=ieee_enabled,
            sd_enabled=sd_enabled
        )
    else:
        # Paralel mod: Scraper'lar aynı anda çalışır (5 sn arayla başlar)
        await manager.start_all(
            headless=settings.scraper_headless,
            ieee_enabled=ieee_enabled,
            sd_enabled=sd_enabled
        )
    
    logger.success("Scraper'lar arka planda başlatıldı")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Startup:
    - Database bağlantısı
    - Scraper manager initialization
    - Auto-start scrapers (if enabled) - BACKGROUND'da başlar
    
    Shutdown:
    - Stop all scrapers
    - Close database connection
    """
    global scraper_manager
    
    logger.header("BACKEND BAŞLATILIYOR")
    
    # Initialize database
    logger.info("Database bağlantısı kuruluyor...")
    db_success = await init_database()
    if not db_success:
        logger.error("Database bağlantısı kurulamadı!")
        raise RuntimeError("Database connection failed")
    logger.success("Database bağlantısı kuruldu")
    
    # Initialize scraper manager
    logger.info("Scraper manager başlatılıyor...")
    scraper_manager = ScraperManager()
    await scraper_manager.initialize()
    set_scraper_manager(scraper_manager)
    logger.success("Scraper manager hazır")
    
    logger.header("BACKEND HAZIR")
    logger.info(f"API: http://localhost:8000")
    logger.info(f"Docs: http://localhost:8000/docs")
    
    # Auto-start scrapers AFTER startup completes (background task)
    # Bu task yield'den sonra background'da çalışır
    scraper_task = None
    if settings.auto_start_scrapers:
        logger.info("Scraper'lar startup sonrası arka planda başlatılacak...")
        scraper_task = asyncio.create_task(delayed_scraper_start(scraper_manager))
    
    yield
    
    # Shutdown
    logger.header("BACKEND KAPATILIYOR")
    
    # Cancel pending scraper start task if exists
    if scraper_task and not scraper_task.done():
        scraper_task.cancel()
        try:
            await scraper_task
        except asyncio.CancelledError:
            pass
    
    # Stop all scrapers
    logger.info("Scraper'lar durduruluyor...")
    if scraper_manager:
        await scraper_manager.stop_all()
        await scraper_manager.close()
    
    # Close database
    logger.info("Database bağlantısı kapatılıyor...")
    await close_database()
    
    logger.success("Backend kapatıldı")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## Academic Research Scraper API

IEEE Xplore ve ScienceDirect'ten akademik makale toplayan scraper'ları yönetir.

### Özellikler

* **Scraper Yönetimi**: Başlatma, durdurma, duraklatma
* **İlerleme Takibi**: Gerçek zamanlı scraping ilerleme durumu
* **Database Erişimi**: Journals, Issues, Articles
* **Filtreleme & Pagination**: Gelişmiş arama ve sıralama
* **İstatistikler**: Database ve scraper metrikleri
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(journals_router, prefix="/api/v1")
app.include_router(issues_router, prefix="/api/v1")
app.include_router(articles_router, prefix="/api/v1")
app.include_router(scrapers_router, prefix="/api/v1")
app.include_router(stats_router, prefix="/api/v1")


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["Root"])
async def health_check():
    """Health check endpoint"""
    from database.connection import get_database
    
    db = get_database()
    db_connected = db is not None
    
    scraper_status = {}
    if scraper_manager:
        status = scraper_manager.get_all_status()
        scraper_status = {
            "ieee": status["ieee"]["status"],
            "sciencedirect": status["sciencedirect"]["status"],
        }
    
    return {
        "status": "healthy" if db_connected else "unhealthy",
        "database": "connected" if db_connected else "disconnected",
        "scrapers": scraper_status,
    }


# API info endpoint
@app.get("/api/v1", tags=["Root"])
async def api_info():
    """API version info"""
    return {
        "version": "v1",
        "endpoints": {
            "journals": "/api/v1/journals",
            "issues": "/api/v1/issues",
            "articles": "/api/v1/articles",
            "scrapers": "/api/v1/scrapers",
            "stats": "/api/v1/stats",
        }
    }
