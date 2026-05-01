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


def handle_cookie_consent(driver, max_rounds: int = 6, round_wait: float = 0.4):
    """
    Cookie onay popup'larını kapatır.

    Not:
    - Banner bazı sayfalarda gecikmeli geldiği için kısa aralıklı çoklu tur dener.
    - Banner görünmüyorsa ilk turda hızlıca çıkar (ekstra bekleme yok).
    """
    try:
        logger.info("Cookie popup kontrolü yapılıyor...")

        # Eski, daha güvenli (spesifik) selector seti
        banner_selectors = [
            "#onetrust-banner-sdk",
            ".onetrust-pc-dark-filter",
            ".cc-window",
            "#CybotCookiebotDialog",
            "[class*='cookie-banner']",
            "[class*='cookie-consent']",
        ]

        click_css_selectors = [
            # Science Direct / Elsevier spesifik
            "button#onetrust-accept-btn-handler",
            "button[aria-label='Accept Cookies']",
            "button.accept-cookies-button",
            "button.onetrust-close-btn-handler",

            # Genel ama kontrollü
            "button.cc-accept",
            "button.cookie-accept",
            "a.cc-btn-accept",
            "#accept-cookies",
            ".accept-cookies-button",
        ]

        click_xpath_selectors = [
            "//button[normalize-space()='Accept']",
            "//button[contains(normalize-space(), 'Accept All')]",
            "//button[contains(normalize-space(), 'I Accept')]",
            "//a[normalize-space()='Accept']",
        ]

        dismissed = False

        for attempt in range(max_rounds):
            # 1) Banner görünür mü hızlı kontrol
            # Not: position:fixed elementlerde offsetParent=null olur, bu yüzden
            # getBoundingClientRect ve computedStyle ile kontrol ediyoruz
            try:
                banner_visible = bool(driver.execute_script("""
                    const selectors = arguments[0];
                    return selectors.some(selector =>
                        Array.from(document.querySelectorAll(selector)).some(el => {
                            if (!el) return false;
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        })
                    );
                """, banner_selectors))
            except Exception:
                banner_visible = False

            # 2) Banner yoksa bu turu atla
            if not banner_visible:
                if dismissed:
                    logger.success("Cookie popup kapatıldı/gizlendi")
                    return True
                if attempt == 0:
                    logger.info("Cookie popup bulunamadı (zaten kapalı olabilir)")
                    return False
                return dismissed

            # 3) Accept butonlarına hızlı tıklama denemeleri
            clicked_this_round = False
            for selector in click_css_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if not el.is_displayed():
                            continue
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        logger.success(f"Cookie popup kapatıldı: {selector}")
                        # Tıklama başarılı — banner kapanana kadar kısa bekle, hemen dön
                        time.sleep(0.5)
                        logger.success("Cookie popup kapatıldı/gizlendi")
                        return True
                except Exception:
                    continue

            for selector in click_xpath_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for el in elements:
                        if not el.is_displayed():
                            continue
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        logger.success(f"Cookie popup kapatıldı: {selector}")
                        time.sleep(0.5)
                        logger.success("Cookie popup kapatıldı/gizlendi")
                        return True
                except Exception:
                    continue

            # 4) Son çare: sadece bilinen banner/overlay'i JS ile gizle
            # (geniş id/class wildcard kaldırıldı, yanlış eleman gizlemeyi önler)
            if not clicked_this_round and banner_visible:
                try:
                    hidden_count = int(driver.execute_script("""
                        const selectors = arguments[0];
                        let hidden = 0;
                        selectors.forEach(selector => {
                            document.querySelectorAll(selector).forEach(el => {
                                const style = window.getComputedStyle(el);
                                const rect = el.getBoundingClientRect();
                                const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0;
                                if (visible) {
                                    el.style.display = 'none';
                                    hidden += 1;
                                }
                            });
                        });
                        if (document.body) document.body.style.overflow = 'auto';
                        return hidden;
                    """, ["#onetrust-banner-sdk", ".onetrust-pc-dark-filter", ".cc-window", "#CybotCookiebotDialog"]))
                    if hidden_count > 0:
                        dismissed = True
                        logger.success("Cookie banner JS fallback ile gizlendi")
                        return True
                except Exception:
                    pass

            # Geç render edilen banner için kısa aralıklı yeniden dene
            if attempt < max_rounds - 1:
                time.sleep(round_wait)

        logger.warning("Cookie popup görünür kalmış olabilir")
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