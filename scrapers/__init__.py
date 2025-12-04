"""
Academic Research Scrapers Package

IEEE Xplore ve ScienceDirect scraperları için ana paket.
MongoDB ile entegre async scraping desteği.

Kullanım:
    # Database service başlat
    from database import init_database_service, close_database
    
    service = await init_database_service()
    
    # Veri ekle
    journal, created = await service.add_journal(
        name="IEEE Access",
        source_website="ieeexplore"
    )
    
    # Bağlantıyı kapat
    await close_database()
"""

__version__ = '2.0.0'
__author__ = 'Academic Research Team'
