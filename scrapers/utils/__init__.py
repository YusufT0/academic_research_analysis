"""
Utilities Module
PDF işleme, indirme, veri yönetimi ve loglama araçları
"""

from .compress_pdfs import PDFCompressor
from .pdf_downloader import PDFDownloader, ProxyConfig
from .academic_data_manager import AcademicDataManager
from .logger import ScraperLogger, get_logger, LogLevel, LogIcons, Colors

__all__ = [
    'PDFCompressor',
    'PDFDownloader',
    'ProxyConfig',
    'AcademicDataManager',
    'ScraperLogger',
    'get_logger',
    'LogLevel',
    'LogIcons',
    'Colors',
]

__version__ = '1.0.0'
