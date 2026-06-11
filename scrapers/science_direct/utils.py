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


def handle_cookie_consent(driver, max_rounds: int = 3, round_wait: float = 0.5):
    """
    Cookie onay popup'larını kapatır.

    Strateji (sırayla):
    1. Spesifik ID/selector ile direkt tıkla — JS visibility check yok, hata toleranslı
    2. Metin tabanlı XPath ile tıkla
    3. JS ile banner'ı DOM'dan gizle (son çare)
    Visibility check için execute_script'e bağlı kalmaz; find_elements yeterli.
    """
    # Tıklanacak butonlar — en spesifikten genele
    ACCEPT_CSS = [
        "#onetrust-accept-btn-handler",       # SD/Elsevier "Accept all cookies"
        "#onetrust-reject-all-handler",        # SD/Elsevier "Accept only necessary"
        "button[id*='onetrust'][id*='accept']",
        "button[id*='accept-btn']",
        "button[aria-label='Accept Cookies']",
        "button.accept-cookies-button",
        "button.cc-accept",
        "button.cookie-accept",
        "#accept-cookies",
        ".accept-cookies-button",
        "a.cc-btn-accept",
    ]

    ACCEPT_XPATH = [
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept all')]",
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept cookies')]",
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'i accept')]",
        "//button[normalize-space()='Accept']",
        "//a[normalize-space()='Accept']",
    ]

    # Banner varlık kontrolü için — sadece element bul, JS lazım değil
    BANNER_IDS = [
        "onetrust-banner-sdk",
        "CybotCookiebotDialog",
        "cc-window",
    ]

    def _try_click(el) -> bool:
        """Elemente tıklamayı dene; başarısızsa JS click."""
        try:
            el.click()
            return True
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            pass
        return False

    def _banner_exists() -> bool:
        for bid in BANNER_IDS:
            try:
                if driver.find_elements(By.ID, bid):
                    return True
            except Exception:
                pass
        return False

    try:
        for attempt in range(max_rounds):
            # --- CSS selectors ---
            for sel in ACCEPT_CSS:
                try:
                    for el in driver.find_elements(By.CSS_SELECTOR, sel):
                        if _try_click(el):
                            logger.success(f"Cookie popup kapatıldı: {sel}")
                            time.sleep(0.3)
                            return True
                except Exception:
                    continue

            # --- XPath selectors ---
            for xpath in ACCEPT_XPATH:
                try:
                    for el in driver.find_elements(By.XPATH, xpath):
                        if _try_click(el):
                            logger.success("Cookie popup kapatıldı (XPath)")
                            time.sleep(0.3)
                            return True
                except Exception:
                    continue

            # --- Banner var mı kontrol ---
            if not _banner_exists():
                if attempt == 0:
                    logger.info("Cookie popup bulunamadı (zaten kapalı olabilir)")
                return False

            # --- JS fallback: banner'ı gizle ---
            try:
                driver.execute_script("""
                    ['onetrust-banner-sdk','onetrust-pc-dark-filter',
                     'CybotCookiebotDialog','cc-window'].forEach(function(id){
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                    if (document.body) document.body.style.overflow = 'auto';
                """)
                logger.success("Cookie banner JS fallback ile gizlendi")
                return True
            except Exception:
                pass

            if attempt < max_rounds - 1:
                time.sleep(round_wait)

        logger.warning("Cookie popup kapatılamadı")
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