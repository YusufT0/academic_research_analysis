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

from utils.logger import get_logger
logger = get_logger('ieee_xplore')

from ieee_xplore.config import ProxyConfig, IEEEXploreConfig
from ieee_xplore.driver import SeleniumDriver
from ieee_xplore.utils import handle_cookie_consent, wait_for_page_load
from ieee_xplore.navigation import PageNavigator
from ieee_xplore.parsers import JournalParser, ArticleParser
from utils.academic_data_manager import AcademicDataManager


def main():
    """Ana fonksiyon - IEEE Xplore'a bağlan ve cookie'leri handle et"""
    
    logger.header("IEEE XPLORE SCRAPER - FULL PIPELINE")
    
    # Academic Data Manager'ı başlat
    data_manager = AcademicDataManager(website_name='ieeexplore', output_dir='./data')
    
    # Konfigürasyonları yükle
    proxy_config = ProxyConfig()
    ieee_config = IEEEXploreConfig()
    
    logger.section("Konfigürasyon")
    logger.info(f"Base URL: {ieee_config.base_url}")
    logger.info(f"Proxy kullanımı: {proxy_config.use_proxy}")
    if proxy_config.is_configured():
        logger.info(f"Proxy: {proxy_config.host}:{proxy_config.port}")
    
    # WebDriver'ı başlat
    driver = SeleniumDriver(proxy_config, headless=False)
    
    if not driver.start():
        logger.error("WebDriver başlatılamadı!")
        return
    
    try:
        # IEEE Xplore ana sayfasına git
        logger.url(ieee_config.base_url, "IEEE Xplore'a bağlanılıyor")
        if not driver.get(ieee_config.base_url, wait_after=3):
            logger.error("Sayfa yüklenemedi!")
            return
        
        # Sayfanın tamamen yüklenmesini bekle
        logger.loading("Sayfa yükleniyor")
        wait_for_page_load(driver.driver)
        time.sleep(2)
        
        # Cookie consent'i handle et (kısa timeout ile)
        # handle_cookie_consent(driver.driver, timeout=0.3)
        
        logger.success("Sayfa hazır!")
        
        # Tüm journal'ları toplamak için liste
        all_journals = []
        
        # Sayfa navigasyon bilgisini al
        navigator = PageNavigator(driver.driver)
        page_info = navigator.get_current_page_info()
        
        current_page = 1
        total_pages = page_info['total_pages']
        
        logger.section(f"TOPLAM {total_pages} SAYFA TARANACAK")
        
        # Tüm sayfaları tara
        while True:
            logger.subsection(f"Sayfa {current_page}/{total_pages} taranıyor")
            
            # Mevcut sayfadaki journal'ları parse et
            page_source = driver.driver.page_source
            journals = JournalParser.extract_journals_from_page(page_source)
            all_journals.extend(journals)
            
            logger.found(len(journals), f"journal (Sayfa {current_page})")
            logger.info(f"Toplam: {len(all_journals)} journal")
            
            # Sayfa bilgisini güncelle
            page_info = navigator.get_current_page_info()
            
            # Sonraki sayfa var mı?
            if not page_info['has_next']:
                logger.success("Tüm sayfalar tarandı!")
                break
            
            # Sonraki sayfaya geç
            logger.info(f"Sayfa {current_page + 1}'e geçiliyor...")
            if not navigator.go_to_next_page():
                logger.error("Sonraki sayfaya geçilemedi, tarama sonlandırılıyor")
                break
            
            # Sayfanın yüklenmesini bekle
            wait_for_page_load(driver.driver)
            time.sleep(2)
            
            current_page += 1
        
        # Sayfanın başlığını al
        page_title = driver.driver.title
        current_url = driver.driver.current_url
        
        logger.done("JOURNAL TARAMASI TAMAMLANDI!")
        logger.stats({
            'Toplam Sayfa': total_pages,
            'Toplam Journal': len(all_journals),
            'Most Recent Issue linki olan': sum(1 for j in all_journals if j['most_recent_issue_url'])
        }, "Özet İstatistikler")
        
        # Şimdi her journal'ın Most Recent Issue sayfasına girip makale linklerini topla
        journals_with_articles = [j for j in all_journals if j['most_recent_issue_url']]
        
        logger.header("MAKALE LİNKLERİ TOPLANACAK")
        logger.info(f"{len(journals_with_articles)} journal için makale linkleri toplanacak")
        
        for idx, journal in enumerate(journals_with_articles, 1):
            try:
                logger.item(idx, len(journals_with_articles), journal['name'])
                
                # Most Recent Issue sayfasına git
                issue_url = journal['most_recent_issue_url']
                full_url = f"https://ieeexplore.ieee.org{issue_url}" if not issue_url.startswith('http') else issue_url
                
                logger.url(full_url)
                
                if not driver.get(full_url, wait_after=3):
                    logger.warning("Sayfa yüklenemedi, atlanıyor")
                    continue
                
                # Sayfanın yüklenmesini bekle
                wait_for_page_load(driver.driver)
                time.sleep(2)
                
                # Sayfa kaynağını al
                page_source = driver.driver.page_source
                
                # Issue bilgisini çıkar (issue_number ve date)
                issue_info = ArticleParser.extract_issue_info(page_source)
                issue_url_full = driver.driver.current_url  # Issue sayfasının tam URL'si
                
                # Makale URL'lerini çıkar
                article_urls = ArticleParser.extract_article_urls(page_source)
                
                logger.found(len(article_urls), "makale linki")
                
                # Makale detaylarını topla
                articles = []
                
                for art_idx, art_url in enumerate(article_urls, 1):
                    try:
                        logger.subsection(f"Makale {art_idx}/{len(article_urls)}")
                        
                        # Makale sayfasına git
                        full_article_url = f"https://ieeexplore.ieee.org{art_url}" if not art_url.startswith('http') else art_url
                        logger.url(art_url)
                        
                        if not driver.get(full_article_url, wait_after=3):
                            logger.warning("Makale sayfası yüklenemedi, atlanıyor")
                            continue
                        
                        # Sayfanın yüklenmesini bekle
                        wait_for_page_load(driver.driver)
                        time.sleep(2)
                        
                        # Makale detaylarını çıkar
                        article_page_source = driver.driver.page_source
                        article_details = ArticleParser.extract_article_details(article_page_source, art_url)
                        
                        if article_details and article_details.get('title'):
                            articles.append(article_details)
                            logger.success("Makale detayları alındı")
                        else:
                            logger.warning("Makale detayları alınamadı")
                        
                    except Exception as e:
                        logger.error(f"Makale detay hatası: {e}")
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
                    
                    # Issue bilgisini ekle
                    issue_data = {
                        'issue_number': issue_info.get('issue_number') if issue_info else None,
                        'date': issue_info.get('date') if issue_info else None,
                        'url': issue_url_full
                    }
                    
                    data_manager.add_journal_with_articles(journal_info, articles, issue_info=issue_data)
                else:
                    logger.warning("Bu journal için makale detayı alınamadı")
                
            except Exception as e:
                logger.error(f"Journal işleme hatası: {e}")
                continue
        
        logger.done("TÜM İŞLEMLER TAMAMLANDI!")
        
        # Data Manager istatistiklerini göster
        data_manager.print_statistics()
        
        logger.stats({
            'Başlık': page_title,
            'URL': current_url
        }, "Sayfa Bilgileri")
        
        # Kullanıcıya sayfayı inceleme fırsatı ver
        logger.info("Sayfa açık - inceleyebilirsiniz...")
        logger.info("(Devam etmek için Enter'a basın)")
        input()
        
    except Exception as e:
        logger.failed("Hata oluştu", e)
        import traceback
        traceback.print_exc()
        
    finally:
        # WebDriver'ı kapat
        driver.close()
        logger.separator()
        logger.info("Program tamamlandı")
        logger.separator()


if __name__ == "__main__":
    main()
