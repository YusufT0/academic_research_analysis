"""
IEEE Xplore Scraper - Main Entry Point

Bu script IEEE Xplore sitesine bağlanır, cookie consent'i handle eder
ve temel yapının çalıştığını test eder.
"""

import sys
import time
from pathlib import Path

# Parent directory'yi path'e ekle (utils klasörü için)
sys.path.insert(0, str(Path(__file__).parent.parent))

from ieee_xplore.config import ProxyConfig, IEEEXploreConfig
from ieee_xplore.driver import SeleniumDriver
from ieee_xplore.utils import handle_cookie_consent, wait_for_page_load
from ieee_xplore.navigation import PageNavigator
from ieee_xplore.parsers import JournalParser, ArticleParser
from utils.academic_data_manager import AcademicDataManager


def main():
    """Ana fonksiyon - IEEE Xplore'a bağlan ve cookie'leri handle et"""
    
    print("=" * 80)
    print("IEEE XPLORE SCRAPER - FULL PIPELINE")
    print("=" * 80)
    
    # Academic Data Manager'ı başlat
    data_manager = AcademicDataManager(website_name='ieeexplore', output_dir='./data')
    
    # Konfigürasyonları yükle
    proxy_config = ProxyConfig()
    ieee_config = IEEEXploreConfig()
    
    print("\n📋 Konfigürasyon:")
    print(f"  • Base URL: {ieee_config.base_url}")
    print(f"  • Proxy kullanımı: {proxy_config.use_proxy}")
    if proxy_config.is_configured():
        print(f"  • Proxy: {proxy_config.host}:{proxy_config.port}")
    
    # WebDriver'ı başlat
    driver = SeleniumDriver(proxy_config, headless=False)
    
    if not driver.start():
        print("\n❌ WebDriver başlatılamadı!")
        return
    
    try:
        # IEEE Xplore ana sayfasına git
        print(f"\n🌐 IEEE Xplore'a bağlanılıyor...")
        if not driver.get(ieee_config.base_url, wait_after=3):
            print("❌ Sayfa yüklenemedi!")
            return
        
        # Sayfanın tamamen yüklenmesini bekle
        print("⏳ Sayfa yükleniyor...")
        wait_for_page_load(driver.driver)
        time.sleep(2)
        
        # Cookie consent'i handle et (kısa timeout ile)
        # handle_cookie_consent(driver.driver, timeout=0.3)
        
        print("\n✓ Sayfa hazır!")
        
        # Tüm journal'ları toplamak için liste
        all_journals = []
        
        # Sayfa navigasyon bilgisini al
        navigator = PageNavigator(driver.driver)
        page_info = navigator.get_current_page_info()
        
        current_page = 1
        total_pages = page_info['total_pages']
        
        print(f"\n{'=' * 80}")
        print(f"🔄 TOPLAM {total_pages} SAYFA TARANACAK")
        print(f"{'=' * 80}")
        
        # Tüm sayfaları tara
        while True:
            print(f"\n{'─' * 80}")
            print(f"� Sayfa {current_page}/{total_pages} taraniyor...")
            print(f"{'─' * 80}")
            
            # Mevcut sayfadaki journal'ları parse et
            page_source = driver.driver.page_source
            journals = JournalParser.extract_journals_from_page(page_source)
            all_journals.extend(journals)
            
            print(f"\n✓ Sayfa {current_page}: {len(journals)} journal bulundu")
            print(f"📊 Toplam: {len(all_journals)} journal")
            
            # Sayfa bilgisini güncelle
            page_info = navigator.get_current_page_info()
            
            # Sonraki sayfa var mı?
            if not page_info['has_next']:
                print("\n✓ Tüm sayfalar tarandı!")
                break
            
            # Sonraki sayfaya geç
            print(f"\n→ Sayfa {current_page + 1}'e geçiliyor...")
            if not navigator.go_to_next_page():
                print("✗ Sonraki sayfaya geçilemedi, tarama sonlandırılıyor")
                break
            
            # Sayfanın yüklenmesini bekle
            wait_for_page_load(driver.driver)
            time.sleep(2)
            
            current_page += 1
        
        # Sayfanın başlığını al
        page_title = driver.driver.title
        current_url = driver.driver.current_url
        
        print("\n" + "=" * 80)
        print("✅ JOURNAL TARAMASI TAMAMLANDI!")
        print("=" * 80)
        print(f"\n📊 Özet İstatistikler:")
        print(f"  • Toplam Sayfa: {total_pages}")
        print(f"  • Toplam Journal: {len(all_journals)}")
        print(f"  • Most Recent Issue linki olan: {sum(1 for j in all_journals if j['most_recent_issue_url'])}")
        
        # Şimdi her journal'ın Most Recent Issue sayfasına girip makale linklerini topla
        journals_with_articles = [j for j in all_journals if j['most_recent_issue_url']]
        
        print(f"\n{'=' * 80}")
        print(f"📚 MAKALE LİNKLERİ TOPLANACAK")
        print(f"  • {len(journals_with_articles)} journal için makale linkleri toplanacak")
        print(f"{'=' * 80}")
        
        for idx, journal in enumerate(journals_with_articles, 1):
            try:
                print(f"\n{'─' * 80}")
                print(f"📖 [{idx}/{len(journals_with_articles)}] {journal['name']}")
                print(f"{'─' * 80}")
                
                # Most Recent Issue sayfasına git
                issue_url = journal['most_recent_issue_url']
                full_url = f"https://ieeexplore.ieee.org{issue_url}" if not issue_url.startswith('http') else issue_url
                
                print(f"  → URL: {full_url}")
                
                if not driver.get(full_url, wait_after=3):
                    print(f"  ✗ Sayfa yüklenemedi, atlanıyor...")
                    continue
                
                # Sayfanın yüklenmesini bekle
                wait_for_page_load(driver.driver)
                time.sleep(2)
                
                # Makale URL'lerini çıkar
                page_source = driver.driver.page_source
                article_urls = ArticleParser.extract_article_urls(page_source)
                
                print(f"  ✓ {len(article_urls)} makale linki bulundu")
                
                # Makale detaylarını topla
                articles = []
                
                for art_idx, art_url in enumerate(article_urls, 1):
                    try:
                        print(f"\n  {'┄' * 76}")
                        print(f"  📄 Makale {art_idx}/{len(article_urls)}")
                        print(f"  {'┄' * 76}")
                        
                        # Makale sayfasına git
                        full_article_url = f"https://ieeexplore.ieee.org{art_url}" if not art_url.startswith('http') else art_url
                        print(f"  → {art_url}")
                        
                        if not driver.get(full_article_url, wait_after=3):
                            print(f"  ✗ Makale sayfası yüklenemedi, atlanıyor...")
                            continue
                        
                        # Sayfanın yüklenmesini bekle
                        wait_for_page_load(driver.driver)
                        time.sleep(2)
                        
                        # Makale detaylarını çıkar
                        article_page_source = driver.driver.page_source
                        article_details = ArticleParser.extract_article_details(article_page_source, art_url)
                        
                        if article_details and article_details.get('title'):
                            articles.append(article_details)
                            print(f"  ✓ Makale detayları alındı")
                        else:
                            print(f"  ⚠ Makale detayları alınamadı")
                        
                    except Exception as e:
                        print(f"  ✗ Makale detay hatası: {e}")
                        continue
                
                # Journal ve makaleleri data manager'a kaydet
                if articles:
                    journal_info = {
                        'name': journal['name'],
                        'url': journal.get('url'),
                        'publisher': journal.get('publisher'),
                        'years': journal.get('years'),
                        'type': 'Journal',  # IEEE için varsayılan
                        'open_access': False  # IEEE için varsayılan
                    }
                    
                    data_manager.add_journal_with_articles(journal_info, articles)
                else:
                    print(f"  ⚠ Bu journal için makale detayı alınamadı")
                
            except Exception as e:
                print(f"  ✗ Journal işleme hatası: {e}")
                continue
        
        print("\n" + "=" * 80)
        print("✅ TÜM İŞLEMLER TAMAMLANDI!")
        print("=" * 80)
        
        # Data Manager istatistiklerini göster
        data_manager.print_statistics()
        
        print(f"\n📄 Sayfa Bilgileri:")
        print(f"  • Başlık: {page_title}")
        print(f"  • URL: {current_url}")
        
        # Kullanıcıya sayfayı inceleme fırsatı ver
        print("\n⏸  Sayfa açık - inceleyebilirsiniz...")
        print("   (Devam etmek için Enter'a basın)")
        input()
        
    except Exception as e:
        print(f"\n❌ Hata oluştu: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # WebDriver'ı kapat
        driver.close()
        print("\n" + "=" * 80)
        print("Program tamamlandı")
        print("=" * 80)


if __name__ == "__main__":
    main()
