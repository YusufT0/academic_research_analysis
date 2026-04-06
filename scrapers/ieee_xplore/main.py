"""
IEEE Xplore Scraper - Main Entry Point (Async + MongoDB)

Bu script IEEE Xplore sitesine bağlanır, dergileri tarar
ve verileri MongoDB'ye kaydeder.

Rate limit tespit edildiğinde otomatik olarak Science Direct scraper'a geçiş yapar.

Öncelik Sistemi:
- Veritabanında bulunmayan dergiler öncelikli olarak işlenir
- Tüm dergiler veritabanındaysa, last_scraped_at tarihine göre en eski öncelikli
"""

import sys
import time
import asyncio
from pathlib import Path

# Parent directory'yi path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger
logger = get_logger('ieee_xplore')

from ieee_xplore.config import ProxyConfig, IEEEXploreConfig
from ieee_xplore.driver import SeleniumDriver
from ieee_xplore.utils import handle_cookie_consent, wait_for_page_load
from ieee_xplore.navigation import PageNavigator
from ieee_xplore.parsers import JournalParser, ArticleParser
from ieee_xplore.rate_limiter import IEEERateLimiter, RateLimitException
from database import init_database_service, close_database
from database.repositories import JournalRepository


async def main():
    """Ana fonksiyon - IEEE Xplore'a bağlan ve verileri MongoDB'ye kaydet"""
    
    logger.header("IEEE XPLORE SCRAPER - MONGODB")
    
    # Database service'i başlat
    try:
        db_service = await init_database_service()
    except Exception as e:
        logger.error(f"Database bağlantısı kurulamadı: {e}")
        return
    
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
        await close_database()
        return
    
    # Rate limiter oluştur
    rate_limiter = IEEERateLimiter(driver.driver, pause_duration=300)  # 5 dakika
    
    # Science Direct'e geçiş flag'i
    switch_to_sciencedirect = False
    
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
        
        logger.done("JOURNAL TARAMASI TAMAMLANDI!")
        logger.stats({
            'Toplam Sayfa': total_pages,
            'Toplam Journal': len(all_journals),
            'Most Recent Issue linki olan': sum(1 for j in all_journals if j['most_recent_issue_url'])
        }, "Özet İstatistikler")
        
        # Şimdi her journal'ın Most Recent Issue sayfasına girip makale linklerini topla
        journals_with_articles = [j for j in all_journals if j['most_recent_issue_url']]
        
        logger.header("ÖNCELİK SİSTEMİ - JOURNAL SIRALAMA")
        logger.info(f"{len(journals_with_articles)} journal için veri tabanı kontrolü yapılıyor...")
        
        # Journal repository'yi başlat
        journal_repo = JournalRepository()
        
        # Tüm journal'ların öncelik bilgilerini toplu olarak al
        journal_names = [j['name'] for j in journals_with_articles]
        priority_info = await journal_repo.get_bulk_priority_info(journal_names, 'ieeexplore')
        
        # İstatistikleri göster
        new_count = sum(1 for info in priority_info.values() if not info['exists'])
        existing_count = len(priority_info) - new_count
        
        logger.stats({
            'Toplam Journal': len(journals_with_articles),
            'Yeni (DB\'de yok)': new_count,
            'Mevcut (DB\'de var)': existing_count
        }, "Veri Tabanı Durumu")
        
        # Journal'ları öncelik sistemine göre sırala
        journals_with_articles = JournalRepository.prioritize_journals(journals_with_articles, priority_info)
        
        logger.success("Journal'lar öncelik sırasına göre sıralandı!")
        logger.info("Öncelik: 1) Yeni dergiler  2) En eski scrape edilenler")
        
        # İlk 5 journal'ı göster
        logger.subsection("İşlenecek İlk 5 Journal (Öncelik Sırasına Göre)")
        for i, j in enumerate(journals_with_articles[:5], 1):
            info = priority_info.get(j['name'], {})
            status = "🆕 YENİ" if not info.get('exists') else f"📅 Son: {info.get('last_scraped_at', 'Bilinmiyor')}"
            logger.info(f"  {i}. {j['name']} - {status}")
        
        logger.header("MAKALE LİNKLERİ TOPLANACAK")
        logger.info(f"{len(journals_with_articles)} journal için makale linkleri toplanacak (öncelik sırasına göre)")
        
        for idx, journal_data in enumerate(journals_with_articles, 1):
            try:
                logger.item(idx, len(journals_with_articles), journal_data['name'])
                
                # Most Recent Issue sayfasına git
                issue_url = journal_data['most_recent_issue_url']
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
                
                # Issue bilgisini çıkar
                issue_info = ArticleParser.extract_issue_info(page_source)
                issue_url_full = driver.driver.current_url
                
                # Rate limit kontrolü (issue sayfasında)
                try:
                    rate_limiter.check_and_handle_rate_limit()
                except RateLimitException:
                    logger.error("Rate limit aşıldı! Science Direct'e geçiş yapılacak...")
                    switch_to_sciencedirect = True
                    break
                
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
                        
                        # Rate limit kontrolü (her makale sayfasında)
                        try:
                            rate_limiter.check_and_handle_rate_limit()
                        except RateLimitException:
                            logger.error("Rate limit aşıldı! Science Direct'e geçiş yapılacak...")
                            switch_to_sciencedirect = True
                            break
                        
                        # Makale detaylarını çıkar
                        article_page_source = driver.driver.page_source
                        article_details = ArticleParser.extract_article_details(article_page_source, art_url)
                        
                        if article_details and article_details.get('title'):
                            articles.append(article_details)
                            logger.success("Makale detayları alındı")
                        else:
                            logger.warning("Makale detayları alınamadı")
                        
                    except RateLimitException:
                        # Rate limit exception'ı yukarı fırlat
                        raise
                    except Exception as e:
                        logger.error(f"Makale detay hatası: {e}")
                        continue
                
                # Science Direct'e geçiş gerekiyorsa döngüyü kır
                if switch_to_sciencedirect:
                    break
                
                # Verileri MongoDB'ye kaydet (makale olsun olmasın journal'ı kaydet)
                # Bu sayede bir sonraki çalışmada tekrar kontrol edilmez
                # Journal verisi
                journal_info = {
                    'name': journal_data['name'],
                    'url': journal_data.get('url'),
                    'publisher': journal_data.get('publisher', 'IEEE'),
                    'open_access': False
                }
                
                # Issue verisi
                issue_data = {
                    'issue_number': issue_info.get('issue_number') if issue_info else None,
                    'date': issue_info.get('date') if issue_info else None,
                    'url': issue_url_full
                }
                
                # Database'e kaydet
                result = await db_service.add_journal_with_issue_and_articles(
                    journal_data=journal_info,
                    issue_data=issue_data,
                    articles_data=articles or [],  # Boş liste olabilir
                    source_website='ieeexplore'
                )
                
                if articles:
                    logger.success(f"Kaydedildi: {result['articles_created']} yeni, {result['articles_updated']} güncelleme")
                else:
                    logger.info(f"Journal kaydedildi (makale yok): {journal_data['name']}")
                
            except RateLimitException:
                logger.error("Rate limit exception yakalandı!")
                switch_to_sciencedirect = True
                break
            except Exception as e:
                logger.error(f"Journal işleme hatası: {e}")
                continue
        
        # Science Direct'e geçiş kontrolü
        if switch_to_sciencedirect:
            logger.header("SCIENCE DIRECT'E GEÇİŞ YAPILIYOR")
            logger.warning("IEEE Xplore rate limit nedeniyle Science Direct scraper başlatılacak...")
            
            # IEEE tarayıcısını kapat
            driver.close()
            
            # Database bağlantısını kapat (Science Direct kendi bağlantısını açacak)
            await close_database()
            
            # Science Direct scraper'ı başlat
            from science_direct.main import main as run_science_direct
            await run_science_direct()
        else:
            logger.done("TÜM İŞLEMLER TAMAMLANDI!")
            
            # Database istatistiklerini göster
            await db_service.print_statistics()
            
            # Kullanıcıya sayfayı inceleme fırsatı ver
            logger.info("Sayfa açık - inceleyebilirsiniz...")
            logger.info("(Devam etmek için Enter'a basın)")
            input()
        
    except RateLimitException:
        logger.error("Rate limit exception ana döngüde yakalandı!")
        switch_to_sciencedirect = True
        
        # IEEE tarayıcısını kapat
        driver.close()
        
        # Database bağlantısını kapat (Science Direct kendi bağlantısını açacak)
        await close_database()
        
        # Science Direct scraper'ı başlat
        from science_direct.main import main as run_science_direct
        await run_science_direct()
        
    except Exception as e:
        logger.failed("Hata oluştu", e)
        import traceback
        traceback.print_exc()
        
    finally:
        # WebDriver'ı kapat
        try:
            driver.close()
        except:
            pass
        # Database bağlantısını kapat
        await close_database()
        logger.separator()
        logger.info("Program tamamlandı")
        logger.separator()


if __name__ == "__main__":
    asyncio.run(main())
