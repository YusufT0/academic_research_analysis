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
from .core.error_handlers import register_error_handlers
from .services.scraper_manager import ScraperManager
from .services.cache_service import cache_service
from .middleware import RequestIdMiddleware, TimingMiddleware, RequestLoggingMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from .routers import (
    journals_router,
    issues_router,
    articles_router,
    scrapers_router,
    stats_router,
    nlp_router,
    websocket_router,
    search_router,
    openalex_router,
    citation_graph_router,
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


async def sync_es_on_startup():
    """Uygulama başlatılırken veritabanı ile Elasticsearch'ü senkronize eder."""
    try:
        from backend.services.elasticsearch_service import elasticsearch_service
        if not elasticsearch_service.is_connected:
            return
            
        from database.models import Article
        
        # Mongo makale sayısını al
        mongo_count = await Article.count()
        
        # ES makale sayısını al
        try:
            es_count_res = await elasticsearch_service._client.count(index=elasticsearch_service.articles_index)
            es_count = es_count_res.get("count", 0)
        except Exception:
            es_count = 0
            
        logger.info(f"Startup ES Sync Check: Mongo ({mongo_count}) vs ES ({es_count})")

        if mongo_count > 0 and es_count == 0:
            # İlk kurulum: ES tamamen boşsa bulk sync yap
            logger.info("ES boş — ilk kurulum bulk sync başlatılıyor...")
        elif mongo_count > 0 and mongo_count != es_count:
            # Sayı uyuşmazlığı: sadece ufak fark varsa sync, büyük farkta uyar
            diff = abs(mongo_count - es_count)
            if diff > mongo_count * 0.1:  # %10'dan fazla fark varsa sync
                logger.info(f"ES desync fazla ({diff} döküman) — bulk sync başlatılıyor...")
            else:
                logger.info(f"ES küçük uyuşmazlık ({diff} döküman) — event-driven sync devrede, atlanıyor")
                return

        if mongo_count > 0 and (es_count == 0 or abs(mongo_count - es_count) > mongo_count * 0.1):
            logger.info("MongoDB -> ES senkronizasyonu başlatılıyor...")
            articles = await Article.find_all().to_list()
            
            article_dicts = []
            for a in articles:
                d = a.model_dump()
                d["id"] = str(a.id)
                if a.journal_id: d["journal_id"] = str(a.journal_id)
                if a.issue_id: d["issue_id"] = str(a.issue_id)
                article_dicts.append(d)
                
            batch_size = 500
            total_indexed = 0
            for i in range(0, len(article_dicts), batch_size):
                batch = article_dicts[i:i + batch_size]
                count = await elasticsearch_service.bulk_index(batch)
                total_indexed += count
                
            logger.success(f"ES Senkronizasyonu tamamlandı: {total_indexed} makale indexlendi")
        else:
            logger.info("ES Senkronizasyonu atlandı (Veriler güncel)")
    except Exception as e:
        logger.error(f"ES Startup Sync hatası: {e}")

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
    
    # Run tests if enabled
    if settings.run_tests_on_startup:
        logger.info("Startup testleri çalıştırılıyor (RUN_TESTS_ON_STARTUP=true)...")
        import pytest
        loop = asyncio.get_running_loop()
        exit_code = await loop.run_in_executor(None, pytest.main, ["tests/", "-q"])
        if exit_code != 0:
            logger.error(f"Testler başarısız oldu (Exit code: {exit_code}). Kurulum iptal ediliyor.")
            raise RuntimeError("Test execution failed. Aborting startup.")
        logger.success("Tüm startup testleri başarıyla geçti")
    
    # Initialize database
    logger.info("Database bağlantısı kuruluyor...")
    db_success = await init_database()
    if not db_success:
        logger.error("Database bağlantısı kurulamadı!")
        raise RuntimeError("Database connection failed")
    logger.success("Database bağlantısı kuruldu")
    
    # Initialize Redis cache
    logger.info("Redis cache bağlantısı kuruluyor...")
    redis_success = await cache_service.connect()
    if redis_success:
        logger.success("Redis cache bağlantısı kuruldu")
    else:
        logger.warning("Redis cache bağlantısı kurulamadı - cache devre dışı")
    
    # Initialize Elasticsearch
    logger.info("Elasticsearch bağlantısı kuruluyor...")
    try:
        from backend.services.elasticsearch_service import elasticsearch_service
        await elasticsearch_service.connect()
        if elasticsearch_service.is_connected:
            logger.success("Elasticsearch bağlantısı kuruldu")
            # Auto-sync datbase to ES in background
            if settings.elasticsearch_auto_sync:
                asyncio.create_task(sync_es_on_startup())
            else:
                logger.info("Elasticsearch otomatik senkronizasyon kapalı.")
        else:
            logger.warning("Elasticsearch bağlantısı kurulamadı - arama devre dışı")
    except Exception as e:
        logger.warning(f"Elasticsearch başlatılamadı: {e}")
    
    # Redis Streams Workers: ES indexleme + Citation Updates
    try:
        from backend.services.stream_service import stream_service
        from backend.services.es_stream_handler import es_stream_handler
        from backend.services.openalex.worker import citation_worker

        await stream_service.connect()
        es_stream_handler.register()
        citation_worker.register_workers()
        await stream_service.start_consumers()
        logger.info("Stream service consumers başlatıldı (ES indexer + Citation worker).")
    except Exception as e:
        logger.error(f"Stream service başlatılamadı: {e}")

    # Start WebSocket Redis Pub/Sub subscription (before first client connects)
    try:
        from backend.routers.websocket import ws_manager
        await ws_manager.startup()
        logger.success("WebSocket Redis Pub/Sub consumer başlatıldı")
    except Exception as e:
        logger.warning(f"WebSocket startup hatası: {e}")

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
    
    # Close Redis cache
    logger.info("Redis cache bağlantısı kapatılıyor...")
    await cache_service.disconnect()
    
    # Close database
    logger.info("Database bağlantısı kapatılıyor...")
    await close_database()
    
    logger.success("Backend kapatıldı")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
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
app.include_router(nlp_router, prefix="/api/v1")
app.include_router(websocket_router)  # WebSocket — prefix yok, /ws/scrapers/events
app.include_router(search_router, prefix="/api/v1")
app.include_router(openalex_router, prefix="/api/v1")
app.include_router(citation_graph_router, prefix="/api/v1")

# Register global error handlers
register_error_handlers(app)

# Middleware zinciri (LIFO sıra — en son eklenen en dışta çalışır)
# 1. RequestId → 2. Timing → 3. Logging
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIdMiddleware)

# Prometheus HTTP metrics (auto: request count, latency, status codes)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["Monitoring"])


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


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check (backward compatible — redirects to /health/ready logic)"""
    return await health_ready()


@app.get("/health/live", tags=["Health"])
async def health_live():
    """Liveness probe — uygulama ayakta mı"""
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def health_ready():
    """Readiness probe — tüm dependency'ler hazır mı"""
    from database.connection import get_database
    
    checks = {}
    overall = True
    
    # MongoDB check
    try:
        db = get_database()
        if db and db.client:
            await db.client.admin.command("ping")
            checks["mongodb"] = {"status": "up"}
        else:
            checks["mongodb"] = {"status": "down", "error": "not connected"}
            overall = False
    except Exception as e:
        checks["mongodb"] = {"status": "down", "error": str(e)}
        overall = False
    
    # Redis check
    try:
        if cache_service and cache_service.redis:
            await cache_service.redis.ping()
            checks["redis"] = {"status": "up"}
        else:
            checks["redis"] = {"status": "down", "error": "not connected"}
            overall = False
    except Exception as e:
        checks["redis"] = {"status": "down", "error": str(e)}
        overall = False
    
    status_code = 200 if overall else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall else "unhealthy",
            "checks": checks,
        }
    )


@app.get("/health/deep", tags=["Health"])
async def health_deep():
    """Deep health check — detaylı diagnostik bilgi"""
    import time
    import psutil
    from database.connection import get_database
    from .core.circuit_breaker import get_all_breaker_statuses
    
    checks = {}
    
    # MongoDB check with latency
    try:
        db = get_database()
        if db and db.client:
            start = time.perf_counter()
            await db.client.admin.command("ping")
            latency = round((time.perf_counter() - start) * 1000, 2)
            checks["mongodb"] = {"status": "up", "latency_ms": latency}
        else:
            checks["mongodb"] = {"status": "down"}
    except Exception as e:
        checks["mongodb"] = {"status": "down", "error": str(e)}
    
    # Redis check with latency
    try:
        if cache_service and cache_service.redis:
            start = time.perf_counter()
            await cache_service.redis.ping()
            latency = round((time.perf_counter() - start) * 1000, 2)
            checks["redis"] = {"status": "up", "latency_ms": latency}
        else:
            checks["redis"] = {"status": "down"}
    except Exception as e:
        checks["redis"] = {"status": "down", "error": str(e)}
    
    # Scrapers status
    scraper_status = {}
    if scraper_manager:
        status = scraper_manager.get_all_status()
        scraper_status = {
            "ieee": status["ieee"]["status"],
            "sciencedirect": status["sciencedirect"]["status"],
        }
    
    # System info
    process = psutil.Process()
    system = {
        "uptime_seconds": round(time.time() - process.create_time(), 1),
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
        "cpu_percent": process.cpu_percent(),
        "threads": process.num_threads(),
    }
    
    # WebSocket connections
    from .routers.websocket import ws_manager
    
    return {
        "status": "healthy" if all(
            c.get("status") == "up" for c in checks.values()
        ) else "degraded",
        "checks": checks,
        "scrapers": scraper_status,
        "circuit_breakers": get_all_breaker_statuses(),
        "websocket_connections": ws_manager.connection_count,
        "system": system,
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
            "nlp" : "/api/v1/nlp"
        }
    }
