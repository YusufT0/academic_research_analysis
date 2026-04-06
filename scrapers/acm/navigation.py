"""
Navigation functions for ACM scraper
"""

import sys
import time

sys.path.insert(0, str(__file__).rsplit('acm', 1)[0])
from utils.logger import get_logger
logger = get_logger('acm')


class PageNavigator:
    """ACM sayfa navigasyonunu yöneten sınıf"""
    
    ACM_BASE = "https://dl.acm.org"
    
    @staticmethod
    def navigate_to_journal(selenium_driver, journal: dict, wait_after: int = 3) -> bool:
        """
        Belirtilen journal sayfasına git
        
        Args:
            selenium_driver: SeleniumDriver wrapper instance
            journal: Journal dict ({'code': ..., 'url': ..., ...})
            wait_after: Sayfa yüklendikten sonra bekleme süresi
            
        Returns:
            bool: Başarılı mı
        """
        journal_url = journal.get('url', '')
        journal_name = journal.get('name', 'Unknown')
        
        if not journal_url:
            logger.warning(f"{journal_name}: URL bulunamadı")
            return False
        
        # Relative URL ise full URL yap
        if journal_url.startswith('/'):
            journal_url = f"{PageNavigator.ACM_BASE}{journal_url}"
        
        try:
            logger.url(journal_url, f"{journal_name} sayfasına gidiliyor")
            if not selenium_driver.get(journal_url, wait_after=wait_after):
                logger.failed(f"{journal_name} sayfasına gidilemedi")
                return False
            
            # Sayfa yüklenmesini bekle
            selenium_driver.wait_for_page_load(30)
            
            logger.success(f"{journal_name} sayfası yüklendi")
            return True
            
        except Exception as e:
            logger.failed(f"{journal_name} sayfasına gidilemedi", e)
            return False
    
    @staticmethod
    def navigate_to_loi(selenium_driver, journal_code: str, wait_after: int = 3) -> bool:
        """
        Journal'ın LOI (List of Issues / Archive) sayfasına git.
        URL: https://dl.acm.org/loi/{journal_code}
        """
        loi_url = f"{PageNavigator.ACM_BASE}/loi/{journal_code}"
        try:
            logger.url(loi_url, f"{journal_code} LOI sayfasına gidiliyor")
            if not selenium_driver.get(loi_url, wait_after=wait_after):
                logger.warning(f"LOI sayfası yüklenemedi: {loi_url}")
                return False
            selenium_driver.wait_for_page_load(30)
            logger.success(f"LOI sayfası yüklendi")
            return True
        except Exception as e:
            logger.failed(f"LOI sayfasına gidilemedi ({journal_code})", e)
            return False

    @staticmethod
    def navigate_to_latest_issue(selenium_driver, journal: dict, wait_after: int = 3) -> bool:
        """
        Journal sayfasından "View latest issue" butonuna tıklayarak 
        veya doğrudan /toc/CODE/current URL'sine giderek issue sayfasına git
        
        Args:
            selenium_driver: SeleniumDriver wrapper instance
            journal: Journal dict ({'code': ..., 'url': ..., ...})
            wait_after: Tıklamadan sonra bekleme süresi
            
        Returns:
            bool: Başarılı mı
        """
        journal_code = journal.get('code', '')
        journal_name = journal.get('name', 'Unknown')
        
        # Doğrudan /toc/CODE/current URL'sine git (en güvenilir yol)
        if journal_code:
            current_issue_url = f"{PageNavigator.ACM_BASE}/toc/{journal_code}/current"
            try:
                logger.url(current_issue_url, f"{journal_name} latest issue")
                if not selenium_driver.get(current_issue_url, wait_after=wait_after):
                    logger.warning(f"Doğrudan URL ile gidilemedi")
                else:
                    selenium_driver.wait_for_page_load(30)
                    logger.success(f"{journal_name} latest issue sayfası yüklendi")
                    return True
            except Exception as e:
                logger.warning(f"Doğrudan URL ile gidilemedi: {e}")
        
        # Fallback: Sayfadaki "View latest issue" linkini bul ve tıkla
        try:
            logger.info("View latest issue butonu aranıyor...")
            
            if selenium_driver._cdp_active and selenium_driver._sb:
                # CDP modunda: CSS selector ile click
                cdp_selectors = [
                    "a[href*='/toc/'][href*='/current']",
                    "a.btn--latest-issue",
                ]
                for selector in cdp_selectors:
                    try:
                        selenium_driver._sb.cdp.click_if_visible(selector)
                        time.sleep(wait_after)
                        selenium_driver.wait_for_page_load(30)
                        logger.success("View latest issue butonu tıklandı (CDP)")
                        return True
                    except Exception:
                        continue
            else:
                # Selenium modunda: WebDriverWait ile
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                driver = selenium_driver.driver
                
                selectors = [
                    (By.LINK_TEXT, "View latest issue"),
                    (By.PARTIAL_LINK_TEXT, "latest issue"),
                    (By.PARTIAL_LINK_TEXT, "Latest Issue"),
                    (By.CSS_SELECTOR, "a[href*='/toc/'][href*='/current']"),
                    (By.CSS_SELECTOR, "a.btn--latest-issue"),
                ]
                
                for by, selector in selectors:
                    try:
                        element = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((by, selector))
                        )
                        element.click()
                        time.sleep(wait_after)
                        selenium_driver.wait_for_page_load(30)
                        logger.success("View latest issue butonu tıklandı")
                        return True
                    except Exception:
                        continue
            logger.warning(f"{journal_name}: View latest issue butonu bulunamadı")
            return False
            
        except Exception as e:
            logger.failed(f"{journal_name}: Latest issue navigasyonu başarısız", e)
            return False
