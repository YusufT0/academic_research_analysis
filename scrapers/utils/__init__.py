"""
Utilities Module
PDF işleme, indirme ve veri yönetimi araçları
"""

from .compress_pdfs import PDFCompressor
from .pdf_downloader import PDFDownloader, ProxyConfig
from .academic_data_manager import AcademicDataManager

__all__ = [
    'PDFCompressor',
    'PDFDownloader',
    'ProxyConfig',
    'AcademicDataManager',
]

__version__ = '1.0.0'
