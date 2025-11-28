"""
Main execution script for Science Direct scraper
"""

import sys
from pathlib import Path

# utils klasörünü path'e ekle
utils_path = Path(__file__).parent.parent / 'utils'
sys.path.insert(0, str(utils_path))

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
            print("\n✓ Sayfa hazır, journal taraması başlatılıyor...\n")
            
            # Tüm journal'ları tara
            all_journals = scraper.scrape_all_journals()
            
            # Özet bilgi göster
            print("\n" + "=" * 60)
            print("📊 TARAMA ÖZETİ")
            print("=" * 60)
            print(f"Toplam Journal Sayısı: {len(all_journals)}")
            
            # Harf gruplarına göre sayı
            from collections import Counter
            letter_counts = Counter(j['letter_group'] for j in all_journals if j['letter_group'])
            print(f"\nHarf Gruplarına Göre Dağılım:")
            for letter in sorted(letter_counts.keys()):
                print(f"  {letter}: {letter_counts[letter]} journal")
            
            # Open access sayısı
            open_access_count = sum(1 for j in all_journals if j['open_access'])
            print(f"\nOpen Access: {open_access_count}/{len(all_journals)}")
            
            print("\n" + "=" * 60)
            
            # Tüm journal'ların makalelerini tara
            print("\n" + "=" * 80)
            print("📚 TÜM JOURNAL'LARIN MAKALELERİ TOPLANACAK")
            print("=" * 80)
            
            all_articles = []
            
            for idx, journal in enumerate(all_journals, 1):
                print(f"\n{'=' * 80}")
                print(f"📖 Journal {idx}/{len(all_journals)}: {journal['name']}")
                print(f"{'=' * 80}")
                
                # Her journal için makaleleri tara (max 5 makale - çok uzun sürmemesi için)
                articles = scraper.scrape_journal_articles(journal, max_articles=5)
                all_articles.extend(articles)
                
                # Veri yöneticisine kaydet
                data_manager.add_journal_with_articles(
                    journal_info=journal,
                    articles=articles
                )
                
                print(f"\n✅ {journal['name']}: {len(articles)} makale toplandı")
                print(f"📊 Şu ana kadar toplam: {len(all_articles)} makale")
            
            print("\n" + "=" * 80)
            print("✅ TÜM JOURNAL'LAR TAMAMLANDI")
            print(f"📚 Toplam Journal: {len(all_journals)}")
            print(f"📊 Toplam Makale: {len(all_articles)}")
            print("=" * 80)
            
            # İstatistikleri göster
            print("\n")
            data_manager.print_statistics()
            
            # Sadece makaleleri dışa aktar (PDF downloader için)
            articles_file = data_manager.export_articles_only()
            print(f"\n✓ PDF indirmek için şu dosyayı kullanabilirsiniz:")
            print(f"  python utils/pdf_downloader.py -j {articles_file} -w sciencedirect --compress")
            
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
            #         print(f"\n{'=' * 80}")
            #         print(f"📖 Journal {idx}/{len(search_results)}: {journal['name']}")
            #         print(f"{'=' * 80}")
            #         
            #         articles = scraper.scrape_journal_articles(journal, max_articles=5)
            #         all_articles.extend(articles)
            #         
            #         print(f"\n✅ {journal['name']}: {len(articles)} makale toplandı")
            #     
            #     print("\n" + "=" * 80)
            #     print(f"📊 Toplam Makale: {len(all_articles)}")
            #     print("=" * 80)
            
        else:
            print("\n✗ İşlem başarısız!")
        
    except KeyboardInterrupt:
        print("\n\n⚠ İşlem kullanıcı tarafından durduruldu")
    except Exception as e:
        print(f"\n✗ Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if scraper:
            scraper.close()


if __name__ == "__main__":
    main()
