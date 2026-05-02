"""
Universal Logger System — structlog Refactored

structlog tabanlı, JSON ve console formatlarını destekleyen logger.
Eski ScraperLogger API'siyle geriye uyumlu.

Kullanım:
    from utils.logger import get_logger
    
    logger = get_logger("ieee_scraper")
    logger.info("Scraping started", journal="IEEE Access", progress=50)
    logger.error("Connection failed", url="https://...", retry=3)

Ortam değişkeni:
    LOG_FORMAT=json    → Production (Grafana/Loki parseable)
    LOG_FORMAT=pretty  → Development (renkli console)
"""

import os
import sys
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

import structlog


# ==================== Eski API Uyumluluk ====================

class LogLevel(Enum):
    """Log seviyeleri — geriye uyumluluk için"""
    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogIcons:
    """Log ikonları — geriye uyumluluk için"""
    SUCCESS = '✓'
    ERROR = '✗'
    WARNING = '⚠'
    INFO = 'ℹ'
    DEBUG = '🔍'
    ARROW_RIGHT = '→'
    BULLET = '•'
    STAR = '★'
    GLOBE = '🌐'
    PAGE = '📄'
    BOOK = '📖'
    JOURNAL = '📚'
    ARTICLE = '📝'
    DOWNLOAD = '⬇'
    CLOCK = '⏳'
    CHECK = '✅'
    CROSS = '❌'
    GEAR = '⚙'
    DATABASE = '💾'
    SEARCH = '🔎'
    LINK = '🔗'
    PROGRESS = '🔄'
    DONE = '✅'
    LINE = '─'
    DOUBLE_LINE = '═'
    DOTTED = '┄'


# ==================== Colors (dev mode için) ====================

class Colors:
    """ANSI renk kodları — dev console için"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    WHITE = '\033[37m'
    BG_RED = '\033[41m'


# ==================== structlog Configuration ====================

_configured = False
_lock = threading.Lock()


def _configure_structlog():
    """structlog'u bir kez yapılandır"""
    global _configured
    
    if _configured:
        return
    
    with _lock:
        if _configured:
            return
        
        # Log formatını belirle
        try:
            from backend.core.config import settings
            log_format = settings.log_format.lower()
        except ImportError:
            log_format = os.environ.get("LOG_FORMAT", "pretty").lower()
        
        # Custom SUCCESS level ekle
        logging.addLevelName(25, "SUCCESS")
        
        # Log dizinini oluştur
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Shared processors
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
        ]
        
        if log_format == "json":
            # Production: JSON output
            renderer = structlog.processors.JSONRenderer()
        else:
            # Development: renkli console
            renderer = structlog.dev.ConsoleRenderer(
                colors=_supports_color(),
            )
        
        # Scrapers that should be forwarded to the frontend via WebSocket
        _SCRAPER_LOGGERS = frozenset({
            'ieee_xplore', 'science_direct', 'acm', 'wiley',
            'scraper_manager', 'rate_limiter',
        })

        def _websocket_broadcaster(logger, log_method, event_dict):
            """Websocket üzerinden frontend'e scraper loglarını canlı yayınlar."""
            try:
                level = event_dict.get('level', 'info').lower()
                event_name = event_dict.get('event', '')
                logger_name = event_dict.get('logger', '')

                # Sadece bilinen scraper logger'larını ilet; kütüphane gürültüsünü atla
                if logger_name not in _SCRAPER_LOGGERS:
                    return event_dict

                # Scraper türünü belirle
                ln = logger_name.lower()
                en = event_name.lower()
                if 'ieee' in ln or '[ieee thread]' in en:
                    scraper_name = 'ieee'
                elif 'science' in ln or 'sd' in ln or '[sd thread]' in en:
                    scraper_name = 'sciencedirect'
                elif 'acm' in ln or '[acm thread]' in en:
                    scraper_name = 'acm'
                elif 'wiley' in ln or '[wiley thread]' in en:
                    scraper_name = 'wiley'
                else:
                    scraper_name = logger_name

                payload = {
                    "type": "log",
                    "scraper_type": scraper_name,
                    "timestamp": event_dict.get('timestamp', datetime.now().isoformat()),
                    "data": {
                        "level": level,
                        "message": event_name,
                        **{k: v for k, v in event_dict.items()
                           if k not in ('level', 'event', 'timestamp', 'logger')}
                    }
                }

                # Redis Pub/Sub üzerinden ilet (broadcast_from_thread'e gerek yok)
                from backend.utils.redis_pubsub import redis_pubsub, SCRAPER_EVENTS_CHANNEL
                redis_pubsub.publish_event_sync(SCRAPER_EVENTS_CHANNEL, payload)
            except Exception:
                pass
            return event_dict

        structlog.configure(
            processors=[
                *shared_processors,
                _websocket_broadcaster,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        # Root logger handler setup
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Sadece bizim eklediğimiz formatter var mı kontrol et
        has_structlog_console = any(
            isinstance(h, logging.StreamHandler) and hasattr(h, 'formatter') and h.formatter and
            'ProcessorFormatter' in type(h.formatter).__name__
            for h in root_logger.handlers
        )
        
        # 3. parti kütüphane log seviyelerini sınırla (selenium-wire vb. log kirliliğini önlemek için)
        noisy_loggers = [
            'seleniumwire', 'urllib3', 'hpack', 'selenium', 
            'WDM', 'undetected_chromedriver',
            'httpx', 'httpcore',
            'uvicorn.access'
        ]
        for nl in noisy_loggers:
            logging.getLogger(nl).setLevel(logging.WARNING)
            
        if not has_structlog_console:
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    renderer,
                ],
            )
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
            
            # File handler (JSON formatında)
            log_filename = f"scraper_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_dir / log_filename, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(),
                ],
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        
        _configured = True


def _supports_color() -> bool:
    """Terminal renk desteğini kontrol et"""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return os.environ.get("TERM") is not None
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# ==================== ScraperLogger (Backward Compatible Wrapper) ====================

class ScraperLogger:
    """
    structlog wrapper — eski API ile uyumlu.
    
    Artık singleton DEĞİL. Her get_logger(name) farklı logger döner.
    Tüm çıktılar structlog üzerinden geçer (JSON veya pretty).
    """
    
    def __init__(self, name: str = "scraper"):
        _configure_structlog()
        self._logger = structlog.get_logger(name)
        self.name = name
        self.enable_colors = _supports_color()
    
    # ==================== Ana Log Metodları ====================
    
    def debug(self, message: str, **kwargs):
        """Debug mesajı"""
        self._logger.debug(message, **kwargs)
    
    def info(self, message: str, icon: str = None, **kwargs):
        """Bilgi mesajı"""
        if icon:
            kwargs["icon"] = icon
        self._logger.info(message, **kwargs)
    
    def success(self, message: str, **kwargs):
        """Başarı mesajı (info seviyesinde, level=success marker)"""
        self._logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Uyarı mesajı"""
        self._logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Hata mesajı"""
        self._logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Kritik hata mesajı"""
        self._logger.critical(message, **kwargs)
    
    # ==================== Özel Formatlar (Backward Compat) ====================
    
    def header(self, title: str, width: int = 80):
        """Büyük başlık"""
        self._logger.info(f"{'=' * width}")
        self._logger.info(f"  {title.upper()}")
        self._logger.info(f"{'=' * width}")
    
    def section(self, title: str, width: int = 80):
        """Bölüm başlığı"""
        self._logger.info(f"--- {title} ---")
    
    def subsection(self, title: str):
        """Alt bölüm başlığı"""
        self._logger.info(f"  · {title}")
    
    def progress(self, current: int, total: int, message: str = "İşlem"):
        """İlerleme durumu"""
        percentage = (current / total * 100) if total > 0 else 0
        self._logger.info(
            message,
            current=current,
            total=total,
            percent=round(percentage, 1),
        )
    
    def stats(self, data: dict, title: str = "İstatistikler"):
        """İstatistik tablosu"""
        self._logger.info(title, **data)
    
    def step(self, step_num: int, total_steps: int, description: str):
        """Adım göstergesi"""
        self._logger.info(description, step=step_num, total_steps=total_steps)
    
    def item(self, index: int, total: int, name: str, extra: str = None):
        """Liste öğesi"""
        kwargs = {"index": index, "total": total}
        if extra:
            kwargs["extra"] = extra
        self._logger.info(name, **kwargs)
    
    def url(self, url: str, prefix: str = "URL"):
        """URL gösterimi"""
        self._logger.info(prefix, url=url)
    
    def found(self, count: int, item_type: str):
        """Bulunan öğe sayısı"""
        self._logger.info(f"{count} {item_type} bulundu", count=count, item_type=item_type)
    
    def not_found(self, item_type: str):
        """Bulunamayan öğe"""
        self._logger.warning(f"{item_type} bulunamadı", item_type=item_type)
    
    def skipped(self, reason: str):
        """Atlanan öğe"""
        self._logger.info(f"Atlandı: {reason}")
    
    def saved(self, filepath: str):
        """Kaydedilen dosya"""
        self._logger.info("Kaydedildi", filepath=filepath)
    
    def connecting(self, target: str):
        """Bağlantı mesajı"""
        self._logger.info(f"{target} bağlanılıyor...", target=target)
    
    def loading(self, message: str = "Yükleniyor"):
        """Yükleme mesajı"""
        self._logger.info(f"{message}...")
    
    def done(self, message: str = "Tamamlandı"):
        """Tamamlanma mesajı"""
        self._logger.info(message)
    
    def failed(self, message: str, error: Exception = None):
        """Başarısız işlem"""
        kwargs = {}
        if error:
            kwargs["error"] = str(error)
            kwargs["error_type"] = type(error).__name__
        self._logger.error(message, **kwargs)
    
    def newline(self):
        """Boş satır — structlog'da no-op"""
        pass
    
    def separator(self, char: str = "-", width: int = 80):
        """Ayırıcı çizgi"""
        self._logger.debug(char * min(width, 40))


# ==================== Logger Factory ====================

# Her logger name için ayrı instance cache
_loggers: Dict[str, ScraperLogger] = {}
_loggers_lock = threading.Lock()


def get_logger(
    name: str = "scraper",
    log_dir: Optional[str] = None,
    console_level: LogLevel = LogLevel.INFO,
    file_level: LogLevel = LogLevel.DEBUG,
    enable_file_logging: bool = True,
) -> ScraperLogger:
    """
    Logger instance al veya oluştur.
    
    Her name için farklı logger döner (singleton bug FIX).
    
    Args:
        name: Logger adı (her çağrıda aynı name = aynı logger)
    """
    with _loggers_lock:
        if name not in _loggers:
            _loggers[name] = ScraperLogger(name=name)
        return _loggers[name]


# Kısa erişim alias
logger = get_logger()
