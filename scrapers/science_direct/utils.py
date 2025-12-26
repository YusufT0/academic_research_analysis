"""
Utility functions for Science Direct scraper
"""

import sys
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')


def handle_cookie_consent(driver):
    """Cookie onay popup'larını kapatır"""
    try:
        logger.info("Cookie popup kontrolü yapılıyor...")
        
        # Önce JavaScript ile cookie banner'ı gizlemeyi dene
        try:
            driver.execute_script("""
                // Yaygın cookie banner class'larını gizle
                const cookieSelectors = [
                    '#onetrust-banner-sdk',
                    '.onetrust-pc-dark-filter',
                    '[class*="cookie-banner"]',
                    '[class*="cookie-consent"]',
                    '[id*="cookie"]',
                    '.cc-window',
                    '#CybotCookiebotDialog'
                ];
                
                cookieSelectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        if (el) el.style.display = 'none';
                    });
                });
                
                // Body overflow'u düzelt
                document.body.style.overflow = 'auto';
            """)
            logger.success("JavaScript ile cookie banner'lar gizlendi")
            return True
        except:
            pass
        
        # Yaygın cookie popup selektörleri
        cookie_selectors = [
            # Science Direct / Elsevier spesifik
            "button#onetrust-accept-btn-handler",
            "button.ot-sdk-show-settings",
            "button[aria-label='Accept Cookies']",
            
            # OneTrust (Science Direct kullanıyor)
            "button.accept-cookies-button",
            "button.onetrust-close-btn-handler",
            
            # Genel selektörler
            "button.cc-accept",
            "button.cookie-accept",
            "a.cc-btn-accept",
            "#accept-cookies",
            ".accept-cookies-button",
            "button[aria-label*='Accept']",
            "button[aria-label*='accept']",
            "button[title*='Accept']",
            
            # Text içeren butonlar için XPath
            "//button[contains(text(), 'Accept')]",
            "//button[contains(text(), 'Accept All')]",
            "//button[contains(text(), 'I Accept')]",
            "//a[contains(text(), 'Accept')]",
        ]
        
        # Her selektörü dene
        for selector in cookie_selectors:
            try:
                # XPath mi CSS selector mı kontrol et
                if selector.startswith('//'):
                    button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                else:
                    button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                
                button.click()
                logger.success(f"Cookie popup kapatıldı: {selector}")
                time.sleep(1)
                return True
                
            except TimeoutException:
                continue
        
        logger.info("Cookie popup bulunamadı (zaten kapalı olabilir)")
        return False
        
    except Exception as e:
        logger.warning(f"Cookie popup kapatma hatası: {e}")
        return False


def print_article_summary(article: dict, index: int):
    """Makale özetini yazdırır (debug için)"""
    logger.subsection(f"MAKALE #{index} ÖZETİ")
    logger.info(f"Journal: {article.get('journal_name', 'N/A')}")
    logger.url(article.get('url', 'N/A'), "URL")
    logger.info(f"PDF: {article.get('pdf_url', 'YOK')}")
    logger.info(f"DOI: {article.get('doi', 'YOK')}")
    logger.info(f"Yazarlar ({len(article.get('authors', []))}): {', '.join(article.get('authors', [])[:3])}{'...' if len(article.get('authors', [])) > 3 else ''}")
    
    if article.get('abstract'):
        abstract_preview = article['abstract'][:200] + '...' if len(article['abstract']) > 200 else article['abstract']
        logger.info(f"Abstract: {abstract_preview}")
    else:
        logger.info("Abstract: YOK")
    
    if article.get('introduction'):
        intro_preview = article['introduction'][:200] + '...' if len(article['introduction']) > 200 else article['introduction']
        logger.info(f"Introduction: {intro_preview}")
    else:
        logger.info("Introduction: YOK")
    
    logger.separator()