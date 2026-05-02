"""
Utility functions for Wiley Online Library scraper
"""

import sys
import time

sys.path.insert(0, str(__file__).rsplit('wiley', 1)[0])
from utils.logger import get_logger
logger = get_logger('wiley')


def handle_cookie_consent(selenium_driver, timeout: int = 5) -> bool:
    """
    Wiley cookie consent popup'ını kapat.

    Wiley'de OneTrust cookie banner kullanılır:
    - Accept button: #onetrust-accept-btn-handler
    - Fallback: div.ot-sdk-container button ile kabul

    Args:
        selenium_driver: SeleniumDriver instance
        timeout: Popup bekleme süresi (saniye)

    Returns:
        bool: Cookie popup bulundu ve kapatıldıysa True
    """
    selectors = [
        "#onetrust-accept-btn-handler",
        "button.ot-pc-refuse-all-handler",
        "button[class*='accept']",
        ".cookie-accept",
    ]

    try:
        logger.info("Cookie consent kontrol ediliyor...")

        if selenium_driver._cdp_active and selenium_driver._sb:
            for selector in selectors:
                try:
                    selenium_driver._sb.cdp.click_if_visible(selector)
                    logger.success(f"Cookie popup kapatıldı (CDP) [{selector}]")
                    time.sleep(0.5)
                    return True
                except Exception:
                    continue
            logger.info("Cookie popup bulunamadı (zaten kabul edilmiş veya yok)")
            return False
        else:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            for selector in selectors:
                try:
                    element = WebDriverWait(selenium_driver.driver, timeout).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    element.click()
                    logger.success(f"Cookie popup kapatıldı [{selector}]")
                    time.sleep(0.5)
                    return True
                except Exception:
                    continue
            logger.info("Cookie popup bulunamadı")
            return False

    except Exception as e:
        logger.warning(f"Cookie consent hatası: {e}")
        return False


def wait_for_page_load(selenium_driver, timeout: int = 30) -> bool:
    """
    Sayfanın tamamen yüklenmesini bekle.
    SeleniumDriver.wait_for_page_load() metoduna delege eder.
    """
    return selenium_driver.wait_for_page_load(timeout)


def extract_journal_id_from_url(url: str) -> str:
    """
    Wiley journal URL'sinden journal_id çıkar.

    Örnekler:
    - https://onlinelibrary.wiley.com/journal/15213773  → "15213773"
    - /journal/10969136                                  → "10969136"
    - /loi/15213773                                      → "15213773"
    - /toc/15213773/2024/63/1                            → "15213773"

    Returns:
        str: Journal ID veya boş string
    """
    import re
    # /journal/ID, /loi/ID, /toc/ID, /index/ID pattern
    match = re.search(r'/(?:journal|loi|toc|index)/([a-zA-Z0-9\-\.]+)', url)
    if match:
        return match.group(1)
    # /hub/journal/ID/overview
    match = re.search(r'/hub/journal/([a-zA-Z0-9\-\.]+)', url)
    if match:
        return match.group(1)
    return ""


def build_overview_url(domain: str, journal_id: str) -> str:
    """Aims & Scope URL'si oluştur"""
    return f"{domain}/hub/journal/{journal_id}/overview"


def build_loi_url(domain: str, journal_id: str) -> str:
    """List of Issues URL'si oluştur"""
    return f"{domain}/loi/{journal_id}"


def build_index_url(domain: str, journal_id: str) -> str:
    """Article-based journal index URL'si oluştur"""
    return f"{domain}/index/{journal_id}"


def build_article_url(domain: str, doi: str) -> str:
    """DOI'den makale URL'si oluştur"""
    import urllib.parse
    # DOI zaten encode edilmişse decode edip yeniden kullan
    try:
        decoded_doi = urllib.parse.unquote(doi)
    except Exception:
        decoded_doi = doi
    return f"{domain}/doi/full/{decoded_doi}"


def decode_doi(encoded_doi: str) -> str:
    """URL-encoded DOI'yi decode et"""
    import urllib.parse
    try:
        return urllib.parse.unquote(encoded_doi)
    except Exception:
        return encoded_doi


def normalize_issn(issn_str: str) -> str:
    """ISSN string'ini normalize et: 'XXXX-XXXX' formatına getir"""
    if not issn_str:
        return ""
    import re
    digits = re.sub(r'[^0-9X]', '', issn_str.upper())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:]}"
    return issn_str.strip()


def clean_text(text: str) -> str:
    """Whitespace ve gereksiz karakterleri temizle"""
    if not text:
        return ""
    import re
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Unicode non-breaking space
    text = text.replace('\u00a0', ' ')
    return text.strip()
