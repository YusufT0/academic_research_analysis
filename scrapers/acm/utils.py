"""
Utility functions for ACM scraper

Functions accept a SeleniumDriver instance and use CDP or Selenium APIs
depending on the active mode.
"""

import sys
import time

sys.path.insert(0, str(__file__).rsplit('acm', 1)[0])
from utils.logger import get_logger
logger = get_logger('acm')


def handle_cookie_consent(selenium_driver, timeout: int = 5) -> bool:
    """
    ACM cookie consent popup'ını kapat
    
    Args:
        selenium_driver: SeleniumDriver instance
        timeout: Popup bekleme süresi (saniye)
        
    Returns:
        bool: Cookie popup bulundu ve kapatıldıysa True
    """
    try:
        logger.info("Cookie consent kontrol ediliyor...")
        selector = "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"
        
        if selenium_driver._cdp_active and selenium_driver._sb:
            # CDP modunda: click_if_visible ile dene
            try:
                selenium_driver._sb.cdp.click_if_visible(selector)
                logger.success("Cookie popup kapatıldı (CDP)")
                time.sleep(0.3)
                return True
            except Exception:
                logger.info("Cookie popup bulunamadı (zaten kabul edilmiş veya yok)")
                return False
        else:
            # Selenium modunda: WebDriverWait ile dene
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            try:
                element = WebDriverWait(selenium_driver.driver, timeout).until(
                    EC.element_to_be_clickable((By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"))
                )
                element.click()
                logger.success("Cookie popup kapatıldı")
                time.sleep(0.3)
                return True
            except Exception:
                logger.info("Cookie popup bulunamadı (zaten kabul edilmiş veya yok)")
                return False
            
    except Exception as e:
        logger.warning(f"Cookie consent hatası: {e}")
        return False
        
        
def handle_open_access_modal(selenium_driver, timeout: int = 5) -> bool:
    """
    ACM sayfasına girişte çıkan Open Access modal'ını kapat
    
    Args:
        selenium_driver: SeleniumDriver instance
        timeout: Popup bekleme süresi (saniye)
        
    Returns:
        bool: Modal bulundu ve kapatıldıysa True
    """
    try:
        logger.info("Open Access Modal kontrol ediliyor...")
        selector = "#closeModalBtn"
        
        if selenium_driver._cdp_active and selenium_driver._sb:
            try:
                selenium_driver._sb.cdp.click_if_visible(selector)
                logger.success("Open Access modal kapatıldı (CDP)")
                time.sleep(0.3)
                return True
            except Exception:
                logger.info("Open Access modal bulunamadı.")
                return False
        else:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            try:
                element = WebDriverWait(selenium_driver.driver, timeout).until(
                    EC.element_to_be_clickable((By.ID, "closeModalBtn"))
                )
                element.click()
                logger.success("Open Access modal kapatıldı")
                time.sleep(0.3)
                return True
            except Exception:
                logger.info("Open Access modal bulunamadı.")
                return False
            
    except Exception as e:
        logger.warning(f"Open Access modal hatası: {e}")
        return False


def wait_for_page_load(selenium_driver, timeout: int = 30) -> bool:
    """
    Sayfanın tamamen yüklenmesini bekle.
    SeleniumDriver.wait_for_page_load() metoduna delege eder.
    
    Args:
        selenium_driver: SeleniumDriver instance
        timeout: Maksimum bekleme süresi (saniye)
        
    Returns:
        bool: Sayfa yüklendiyse True
    """
    return selenium_driver.wait_for_page_load(timeout)


def scroll_to_bottom(selenium_driver, pause_time: float = 1.0) -> None:
    """
    Sayfayı en alta kadar scroll et
    
    Args:
        selenium_driver: SeleniumDriver instance
        pause_time: Her scroll arasında bekleme süresi
    """
    last_height = selenium_driver.execute_script("return document.body.scrollHeight")
    
    while True:
        selenium_driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)
        new_height = selenium_driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
