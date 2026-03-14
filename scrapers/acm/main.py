"""
Main execution script for ACM scraper (Async + MongoDB)

Öncelik Sistemi:
- Veritabanında bulunmayan dergiler öncelikli olarak işlenir
- Tüm dergiler veritabanındaysa, last_scraped_at tarihine göre en eski öncelikli
"""

import sys
import asyncio
from pathlib import Path

# utils klasörünü path'e ekle
utils_path = Path(__file__).parent.parent / 'utils'
sys.path.insert(0, str(utils_path))

sys.path.insert(0, str(__file__).rsplit('acm', 1)[0])
from utils.logger import get_logger
logger = get_logger('acm')

from scraper import ACMScraper
from database import init_database_service, close_database
from database.repositories import JournalRepository


async def main():
    """Ana fonksiyon"""
    scraper = None
    db_service = None
    
    try:
        # Database service'i başlat
        try:
            db_service = await init_database_service()
        except Exception as e:
            logger.error(f"Database bağlantısı kurulamadı: {e}")
            return
        
        # Scraper'ı oluştur (.env'deki USE_PROXY ayarını kullan, headless=False)
        scraper = ACMScraper(headless=False)
        
        # Başlat
        scraper.initialize()
        
        # Journals sayfasına git
        success = scraper.navigate_to_journals()
        
        if success:
            # ============================================================
            # Tüm journal'ları tara
            # ============================================================
            logger.success("Sayfa hazır, journal taraması başlatılıyor...")
            
            # Tüm journal'ları tara
            all_journals = scraper.scrape_journals()
            
            # Özet bilgi göster
            logger.header("TARAMA ÖZETİ")
            logger.info(f"Toplam Journal Sayısı: {len(all_journals)}")
            
            # Open access sayısı
            open_access_count = sum(1 for j in all_journals if j.get('open_access'))
            logger.info(f"Open Access: {open_access_count}/{len(all_journals)}")
            
            logger.separator()
            
            # ============================================================
            # ÖNCELİK SİSTEMİ - JOURNAL SIRALAMA
            # ============================================================
            logger.header("ÖNCELİK SİSTEMİ - JOURNAL SIRALAMA")
            logger.info(f"{len(all_journals)} journal için veri tabanı kontrolü yapılıyor...")
            
            # Journal repository'yi başlat
            journal_repo = JournalRepository()
            
            # Tüm journal'ların öncelik bilgilerini toplu olarak al
            journal_names = [j['name'] for j in all_journals if 'name' in j]
            priority_info = await journal_repo.get_bulk_priority_info(journal_names, 'acm')
            
            # İstatistikleri göster
            new_count = sum(1 for info in priority_info.values() if not info.get('exists'))
            existing_count = len(priority_info) - new_count
            
            logger.stats({
                'Toplam Journal': len(all_journals),
                'Yeni (DB\'de yok)': new_count,
                'Mevcut (DB\'de var)': existing_count
            }, "Veri Tabanı Durumu")
            
            # Journal'ları öncelik sistemine göre sırala
            all_journals = JournalRepository.prioritize_journals(all_journals, priority_info)
            
            logger.success("Journal'lar öncelik sırasına göre sıralandı!")
            logger.info("Öncelik: 1) Yeni dergiler  2) En eski scrape edilenler")
            
            # İlk 5 journal'ı göster
            logger.subsection("İşlenecek İlk 5 Journal (Öncelik Sırasına Göre)")
            for i, j in enumerate(all_journals[:5], 1):
                name = j.get('name', 'Unknown')
                info = priority_info.get(name, {})
                status = "🆕 YENİ" if not info.get('exists') else f"📅 Son: {info.get('last_scraped_at', 'Bilinmiyor')}"
                logger.info(f"  {i}. {name} - {status}")
            
            # Tüm journal'ların makalelerini tara
            logger.header("TÜM JOURNAL'LARIN MAKALELERİ TOPLANACAK")
            logger.info(f"{len(all_journals)} journal için makale linkleri toplanacak (öncelik sırasına göre)")
            
            total_articles_created = 0
            total_articles_updated = 0
            
            for idx, journal in enumerate(all_journals, 1):
                name = journal.get('name', 'Unknown')
                logger.section(f"Journal {idx}/{len(all_journals)}: {name}")
                
                # Her journal için makaleleri tara (max 100 makale)
                articles = scraper.scrape_journal_articles(journal, max_articles=100)
                
                # Veri yöneticisine kaydet (makale olsun olmasın journal'ı kaydet)
                # Journal verisi hazırla
                journal_info = {
                    'name': name,
                    'url': journal.get('url'),
                    'publisher': 'ACM',
                    'open_access': journal.get('open_access', False)
                }
                
                # Issue verisi
                issue_data = {
                    'issue_number': journal.get('issue_number'),
                    'date': journal.get('issue_date'),
                    'url': journal.get('issue_url')
                }
                
                # Database'e kaydet
                result = await db_service.add_journal_with_issue_and_articles(
                    journal_data=journal_info,
                    issue_data=issue_data,
                    articles_data=articles or [],  # Boş liste olabilir
                    source_website='acm'
                )
                
                total_articles_created += result.get('articles_created', 0)
                total_articles_updated += result.get('articles_updated', 0)
                
                if articles:
                    logger.success(f"{name}: {result.get('articles_created', 0)} yeni, {result.get('articles_updated', 0)} güncelleme")
                else:
                    logger.info(f"{name}: Makale yok, journal kaydedildi")
                
                logger.info(f"Şu ana kadar toplam: {total_articles_created} yeni makale")
            
            logger.header("TÜM JOURNAL'LAR TAMAMLANDI")
            logger.stats({
                'Toplam Journal': len(all_journals),
                'Yeni Makale': total_articles_created,
                'Güncellenen Makale': total_articles_updated
            })
            
            # Database istatistiklerini göster
            logger.newline()
            await db_service.print_statistics()
            
        else:
            logger.error("İşlem başarısız!")
        
    except KeyboardInterrupt:
        logger.warning("İşlem kullanıcı tarafından durduruldu")
    except Exception as e:
        logger.failed("Beklenmeyen hata", e)
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()
        # Database bağlantısını kapat
        if db_service:
            await close_database()


if __name__ == "__main__":
    asyncio.run(main())
