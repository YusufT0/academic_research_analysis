"""
Universal Logger System - Singleton Pattern

Tüm scraper'larda kullanılabilecek merkezi loglama sistemi.
- Renkli console çıktıları
- Dosyaya loglama
- Farklı log seviyeleri (DEBUG, INFO, SUCCESS, WARNING, ERROR)
- Thread-safe singleton pattern
"""

import os
import sys
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum


class LogLevel(Enum):
    """Log seviyeleri"""
    DEBUG = 10
    INFO = 20
    SUCCESS = 25  # Custom level
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class Colors:
    """ANSI renk kodları"""
    # Temel renkler
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    
    # Metin renkleri
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Parlak renkler
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Arka plan renkleri
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


class LogIcons:
    """Log ikonları (emoji/unicode)"""
    # Durum ikonları
    SUCCESS = '✓'
    ERROR = '✗'
    WARNING = '⚠'
    INFO = 'ℹ'
    DEBUG = '🔍'
    
    # İşlem ikonları
    ARROW_RIGHT = '→'
    ARROW_LEFT = '←'
    BULLET = '•'
    STAR = '★'
    
    # Scraper ikonları
    GLOBE = '🌐'
    PAGE = '📄'
    BOOK = '📖'
    JOURNAL = '📚'
    ARTICLE = '📝'
    DOWNLOAD = '⬇'
    UPLOAD = '⬆'
    CLOCK = '⏳'
    CHECK = '✅'
    CROSS = '❌'
    GEAR = '⚙'
    DATABASE = '💾'
    SEARCH = '🔎'
    LINK = '🔗'
    FOLDER = '📁'
    FILE = '📄'
    
    # Progress ikonları
    PROGRESS = '🔄'
    DONE = '✅'
    PENDING = '⏸'
    
    # Separator
    LINE = '─'
    DOUBLE_LINE = '═'
    DOTTED = '┄'


class ScraperLogger:
    """
    Singleton Logger sınıfı
    
    Kullanım:
        from utils.logger import ScraperLogger
        
        logger = ScraperLogger()
        logger.info("Mesaj")
        logger.success("Başarılı işlem")
        logger.warning("Uyarı mesajı")
        logger.error("Hata mesajı")
        logger.debug("Debug mesajı")
        
        # Özel formatlar
        logger.header("Başlık")
        logger.section("Bölüm başlığı")
        logger.progress(current=5, total=10, message="İşlem")
        logger.stats({"key": "value"})
    """
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern - thread-safe"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        name: str = 'scraper',
        log_dir: Optional[str] = None,
        console_level: LogLevel = LogLevel.INFO,
        file_level: LogLevel = LogLevel.DEBUG,
        enable_file_logging: bool = True,
        enable_colors: bool = True
    ):
        """
        Logger'ı başlat
        
        Args:
            name: Logger adı
            log_dir: Log dosyalarının kaydedileceği dizin
            console_level: Console log seviyesi
            file_level: Dosya log seviyesi
            enable_file_logging: Dosya loglamayı aktif et
            enable_colors: Renkli çıktıyı aktif et
        """
        # Singleton için sadece bir kez initialize et
        if ScraperLogger._initialized:
            return
        
        self.name = name
        self.console_level = console_level
        self.file_level = file_level
        self.enable_colors = enable_colors and self._supports_color()
        self.enable_file_logging = enable_file_logging
        
        # Log dizinini ayarla
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            # Varsayılan: scrapers/logs
            self.log_dir = Path(__file__).parent.parent / 'logs'
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Python logging modülünü yapılandır
        self._setup_logging()
        
        ScraperLogger._initialized = True
    
    def _supports_color(self) -> bool:
        """Terminal renk desteğini kontrol et"""
        # Windows için
        if sys.platform == 'win32':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                return True
            except:
                return os.environ.get('TERM') is not None
        
        # Unix/Linux/Mac için
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    def _setup_logging(self):
        """Python logging modülünü yapılandır"""
        # Custom SUCCESS level ekle
        logging.addLevelName(LogLevel.SUCCESS.value, 'SUCCESS')
        
        # Ana logger'ı oluştur
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Mevcut handler'ları temizle
        
        # Dosya handler
        if self.enable_file_logging:
            log_filename = f"{self.name}_{datetime.now().strftime('%Y%m%d')}.log"
            log_filepath = self.log_dir / log_filename
            
            file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
            file_handler.setLevel(self.file_level.value)
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def _colorize(self, text: str, color: str) -> str:
        """Metni renklendir"""
        if self.enable_colors:
            return f"{color}{text}{Colors.RESET}"
        return text
    
    def _get_timestamp(self) -> str:
        """Zaman damgası al"""
        return datetime.now().strftime('%H:%M:%S')
    
    def _format_message(self, level: LogLevel, message: str, icon: str = None) -> str:
        """Console için mesajı formatla"""
        timestamp = self._get_timestamp()
        
        # Seviyeye göre renk ve ikon belirle
        level_configs = {
            LogLevel.DEBUG: (Colors.BRIGHT_BLACK, LogIcons.DEBUG, 'DEBUG'),
            LogLevel.INFO: (Colors.BRIGHT_BLUE, LogIcons.INFO, 'INFO'),
            LogLevel.SUCCESS: (Colors.BRIGHT_GREEN, LogIcons.SUCCESS, 'SUCCESS'),
            LogLevel.WARNING: (Colors.BRIGHT_YELLOW, LogIcons.WARNING, 'WARNING'),
            LogLevel.ERROR: (Colors.BRIGHT_RED, LogIcons.ERROR, 'ERROR'),
            LogLevel.CRITICAL: (Colors.BG_RED + Colors.WHITE, LogIcons.CROSS, 'CRITICAL'),
        }
        
        color, default_icon, level_name = level_configs.get(level, (Colors.WHITE, '', 'INFO'))
        icon = icon or default_icon
        
        # Zaman damgası (gri)
        ts_colored = self._colorize(timestamp, Colors.BRIGHT_BLACK)
        
        # Seviye etiketi
        level_colored = self._colorize(f"[{level_name}]", color)
        
        # İkon
        icon_colored = self._colorize(icon, color)
        
        return f"{ts_colored} {level_colored} {icon_colored} {message}"
    
    def _log(self, level: LogLevel, message: str, icon: str = None):
        """Genel log fonksiyonu"""
        # Console'a yaz (seviye kontrolü)
        if level.value >= self.console_level.value:
            formatted = self._format_message(level, message, icon)
            print(formatted)
        
        # Dosyaya yaz
        if self.enable_file_logging:
            log_func = {
                LogLevel.DEBUG: self.logger.debug,
                LogLevel.INFO: self.logger.info,
                LogLevel.SUCCESS: lambda m: self.logger.log(LogLevel.SUCCESS.value, m),
                LogLevel.WARNING: self.logger.warning,
                LogLevel.ERROR: self.logger.error,
                LogLevel.CRITICAL: self.logger.critical,
            }.get(level, self.logger.info)
            log_func(message)
    
    # ==================== Ana Log Metodları ====================
    
    def debug(self, message: str):
        """Debug mesajı"""
        self._log(LogLevel.DEBUG, message)
    
    def info(self, message: str, icon: str = None):
        """Bilgi mesajı"""
        self._log(LogLevel.INFO, message, icon)
    
    def success(self, message: str):
        """Başarı mesajı"""
        self._log(LogLevel.SUCCESS, message)
    
    def warning(self, message: str):
        """Uyarı mesajı"""
        self._log(LogLevel.WARNING, message)
    
    def error(self, message: str):
        """Hata mesajı"""
        self._log(LogLevel.ERROR, message)
    
    def critical(self, message: str):
        """Kritik hata mesajı"""
        self._log(LogLevel.CRITICAL, message)
    
    # ==================== Özel Formatlar ====================
    
    def header(self, title: str, width: int = 80):
        """Büyük başlık"""
        line = LogIcons.DOUBLE_LINE * width
        print(self._colorize(line, Colors.BRIGHT_CYAN))
        print(self._colorize(f"  {title.upper()}", Colors.BOLD + Colors.BRIGHT_CYAN))
        print(self._colorize(line, Colors.BRIGHT_CYAN))
        
        if self.enable_file_logging:
            self.logger.info(f"{'=' * width}")
            self.logger.info(f"  {title.upper()}")
            self.logger.info(f"{'=' * width}")
    
    def section(self, title: str, width: int = 80):
        """Bölüm başlığı"""
        line = LogIcons.LINE * width
        print(self._colorize(line, Colors.BRIGHT_BLACK))
        print(self._colorize(f"{LogIcons.STAR} {title}", Colors.BRIGHT_WHITE + Colors.BOLD))
        print(self._colorize(line, Colors.BRIGHT_BLACK))
        
        if self.enable_file_logging:
            self.logger.info(f"{'-' * width}")
            self.logger.info(f"* {title}")
            self.logger.info(f"{'-' * width}")
    
    def subsection(self, title: str):
        """Alt bölüm başlığı"""
        dotted = LogIcons.DOTTED * 76
        print(self._colorize(f"  {dotted}", Colors.BRIGHT_BLACK))
        print(self._colorize(f"  {LogIcons.BULLET} {title}", Colors.BRIGHT_WHITE))
        print(self._colorize(f"  {dotted}", Colors.BRIGHT_BLACK))
        
        if self.enable_file_logging:
            self.logger.info(f"  --- {title} ---")
    
    def progress(self, current: int, total: int, message: str = "İşlem"):
        """İlerleme durumu"""
        percentage = (current / total * 100) if total > 0 else 0
        bar_length = 20
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        progress_str = f"[{current}/{total}]"
        bar_str = f"[{bar}]"
        percent_str = f"{percentage:.1f}%"
        
        output = f"{LogIcons.PROGRESS} {message} {progress_str} {bar_str} {percent_str}"
        
        print(self._colorize(output, Colors.BRIGHT_CYAN))
        
        if self.enable_file_logging:
            self.logger.info(f"Progress: {message} [{current}/{total}] {percentage:.1f}%")
    
    def stats(self, data: dict, title: str = "İstatistikler"):
        """İstatistik tablosu"""
        print(self._colorize(f"\n{LogIcons.DATABASE} {title}:", Colors.BRIGHT_MAGENTA + Colors.BOLD))
        
        for key, value in data.items():
            key_colored = self._colorize(f"  {LogIcons.BULLET} {key}:", Colors.BRIGHT_WHITE)
            value_colored = self._colorize(str(value), Colors.BRIGHT_YELLOW)
            print(f"{key_colored} {value_colored}")
        
        if self.enable_file_logging:
            self.logger.info(f"Stats - {title}:")
            for key, value in data.items():
                self.logger.info(f"  - {key}: {value}")
    
    def step(self, step_num: int, total_steps: int, description: str):
        """Adım göstergesi"""
        step_str = f"[{step_num}/{total_steps}]"
        output = f"{LogIcons.ARROW_RIGHT} Adım {step_str}: {description}"
        
        print(self._colorize(output, Colors.BRIGHT_BLUE))
        
        if self.enable_file_logging:
            self.logger.info(f"Step {step_num}/{total_steps}: {description}")
    
    def item(self, index: int, total: int, name: str, extra: str = None):
        """Liste öğesi"""
        idx_str = f"[{index}/{total}]"
        main = f"  {idx_str} {name}"
        
        print(self._colorize(main, Colors.WHITE), end='')
        if extra:
            print(self._colorize(f" - {extra}", Colors.BRIGHT_BLACK))
        else:
            print()
        
        if self.enable_file_logging:
            log_msg = f"Item {index}/{total}: {name}"
            if extra:
                log_msg += f" - {extra}"
            self.logger.info(log_msg)
    
    def url(self, url: str, prefix: str = "URL"):
        """URL gösterimi"""
        output = f"  {LogIcons.LINK} {prefix}: {url}"
        print(self._colorize(output, Colors.BRIGHT_CYAN))
        
        if self.enable_file_logging:
            self.logger.info(f"{prefix}: {url}")
    
    def found(self, count: int, item_type: str):
        """Bulunan öğe sayısı"""
        output = f"  {LogIcons.SUCCESS} {count} {item_type} bulundu"
        print(self._colorize(output, Colors.BRIGHT_GREEN))
        
        if self.enable_file_logging:
            self.logger.info(f"Found: {count} {item_type}")
    
    def not_found(self, item_type: str):
        """Bulunamayan öğe"""
        output = f"  {LogIcons.WARNING} {item_type} bulunamadı"
        print(self._colorize(output, Colors.BRIGHT_YELLOW))
        
        if self.enable_file_logging:
            self.logger.warning(f"Not found: {item_type}")
    
    def skipped(self, reason: str):
        """Atlanan öğe"""
        output = f"  {LogIcons.ARROW_RIGHT} Atlandı: {reason}"
        print(self._colorize(output, Colors.BRIGHT_BLACK))
        
        if self.enable_file_logging:
            self.logger.info(f"Skipped: {reason}")
    
    def saved(self, filepath: str):
        """Kaydedilen dosya"""
        output = f"  {LogIcons.DATABASE} Kaydedildi: {filepath}"
        print(self._colorize(output, Colors.BRIGHT_GREEN))
        
        if self.enable_file_logging:
            self.logger.info(f"Saved: {filepath}")
    
    def connecting(self, target: str):
        """Bağlantı mesajı"""
        output = f"{LogIcons.GLOBE} {target} bağlanılıyor..."
        print(self._colorize(output, Colors.BRIGHT_CYAN))
        
        if self.enable_file_logging:
            self.logger.info(f"Connecting to: {target}")
    
    def loading(self, message: str = "Yükleniyor"):
        """Yükleme mesajı"""
        output = f"{LogIcons.CLOCK} {message}..."
        print(self._colorize(output, Colors.BRIGHT_YELLOW))
        
        if self.enable_file_logging:
            self.logger.info(f"Loading: {message}")
    
    def done(self, message: str = "Tamamlandı"):
        """Tamamlanma mesajı"""
        output = f"{LogIcons.DONE} {message}"
        print(self._colorize(output, Colors.BRIGHT_GREEN + Colors.BOLD))
        
        if self.enable_file_logging:
            self.logger.info(f"Done: {message}")
    
    def failed(self, message: str, error: Exception = None):
        """Başarısız işlem"""
        output = f"{LogIcons.CROSS} {message}"
        if error:
            output += f": {str(error)}"
        
        print(self._colorize(output, Colors.BRIGHT_RED))
        
        if self.enable_file_logging:
            log_msg = f"Failed: {message}"
            if error:
                log_msg += f" - {str(error)}"
            self.logger.error(log_msg)
    
    def newline(self):
        """Boş satır"""
        print()
    
    def separator(self, char: str = '-', width: int = 80):
        """Ayırıcı çizgi"""
        print(self._colorize(char * width, Colors.BRIGHT_BLACK))


# Global logger instance
_logger_instance = None


def get_logger(
    name: str = 'scraper',
    log_dir: Optional[str] = None,
    console_level: LogLevel = LogLevel.INFO,
    file_level: LogLevel = LogLevel.DEBUG,
    enable_file_logging: bool = True
) -> ScraperLogger:
    """
    Global logger instance'ı al veya oluştur
    
    Args:
        name: Logger adı
        log_dir: Log dizini
        console_level: Console log seviyesi
        file_level: Dosya log seviyesi
        enable_file_logging: Dosya loglamayı aktif et
        
    Returns:
        ScraperLogger instance
    """
    global _logger_instance
    
    if _logger_instance is None:
        _logger_instance = ScraperLogger(
            name=name,
            log_dir=log_dir,
            console_level=console_level,
            file_level=file_level,
            enable_file_logging=enable_file_logging
        )
    
    return _logger_instance


# Kısa erişim için alias
logger = get_logger()
