"""
Main execution script for Science Direct scraper
"""

import sys
from pathlib import Path

# utils klasörünü path'e ekle
utils_path = Path(__file__).parent.parent / 'utils'
sys.path.insert(0, str(utils_path))

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')

from scraper import ScienceDirectScraper
from academic_data_manager import AcademicDataManager


def main():
    """Ana fonksiyon"""
    scraper = None
    
    try:
        # Veri yöneticisi oluştur
        data_manager = AcademicDataManager(
            website_name="sciencedirect",
            output_dir="./data"
        )
        
        # Scraper'ı oluştur (.env'deki USE_PROXY ayarını kullan)
        scraper = ScienceDirectScraper(headless=False)
        
        # Başlat
        scraper.initialize()
        
        # Journals sayfasına git
        success = scraper.navigate_to_journals()
        
        if success:
            # ============================================================
            # SEÇENEK 1: Tüm journal'ları tara
            # ============================================================
            logger.success("Sayfa hazır, journal taraması başlatılıyor...")
            
            # Tüm journal'ları tara
            all_journals = scraper.scrape_all_journals()
            
            # Özet bilgi göster
            logger.header("TARAMA ÖZETİ")
            logger.info(f"Toplam Journal Sayısı: {len(all_journals)}")
            
            # Harf gruplarına göre sayı
            from collections import Counter
            letter_counts = Counter(j['letter_group'] for j in all_journals if j['letter_group'])
            logger.info("Harf Gruplarına Göre Dağılım:")
            for letter in sorted(letter_counts.keys()):
                logger.info(f"  {letter}: {letter_counts[letter]} journal")
            
            # Open access sayısı
            open_access_count = sum(1 for j in all_journals if j['open_access'])
            logger.info(f"Open Access: {open_access_count}/{len(all_journals)}")
            
            logger.separator()
            
            # Tüm journal'ların makalelerini tara
            logger.header("TÜM JOURNAL'LARIN MAKALELERİ TOPLANACAK")
            
            all_articles = []
            
            for idx, journal in enumerate(all_journals, 1):
                logger.section(f"Journal {idx}/{len(all_journals)}: {journal['name']}")
                
                # Her journal için makaleleri tara (max 5 makale - çok uzun sürmemesi için)
                articles = scraper.scrape_journal_articles(journal, max_articles=5)
                all_articles.extend(articles)
                
                # Veri yöneticisine kaydet (sadece makale varsa)
                if articles:
                    data_manager.add_journal_with_articles(
                        journal_info=journal,
                        articles=articles
                    )
                    logger.success(f"{journal['name']}: {len(articles)} makale toplandı ve kaydedildi")
                else:
                    logger.warning(f"{journal['name']}: Makale bulunamadı, kayıt atlandı")
                logger.info(f"Şu ana kadar toplam: {len(all_articles)} makale")
            
            logger.header("TÜM JOURNAL'LAR TAMAMLANDI")
            logger.stats({
                'Toplam Journal': len(all_journals),
                'Toplam Makale': len(all_articles)
            })
            
            # İstatistikleri göster
            logger.newline()
            data_manager.print_statistics()
            
            # Sadece makaleleri dışa aktar (PDF downloader için)
            articles_file = data_manager.export_articles_only()
            logger.success("PDF indirmek için şu dosyayı kullanabilirsiniz:")
            logger.info(f"  python utils/pdf_downloader.py -j {articles_file} -w sciencedirect --compress")
            
            # ============================================================
            # SEÇENEK 2: Belirli bir kelime ile arama yap
            # ============================================================
            # Alternatif olarak arama yapmak isterseniz:
            # search_term = "Machine"
            # print(f"\n🔍 '{search_term}' araması yapılıyor...")
            # search_results = scraper.search_journals(search_term)
            # 
            # if search_results:
            #     print(f"\n✓ {len(search_results)} journal bulundu")
            #     
            #     all_articles = []
            #     
            #     for idx, journal in enumerate(search_results, 1):
            #         logger.section(f"Journal {idx}/{len(search_results)}: {journal['name']}")
            #         
            #         articles = scraper.scrape_journal_articles(journal, max_articles=5)
            #         all_articles.extend(articles)
            #         
            #         logger.success(f"{journal['name']}: {len(articles)} makale toplandı")
            #     
            #     logger.stats({'Toplam Makale': len(all_articles)})
            
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


if __name__ == "__main__":
    main()
