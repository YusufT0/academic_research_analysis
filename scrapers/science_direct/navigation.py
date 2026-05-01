"""
Page navigation functions for Science Direct scraper
"""

import sys
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')

from .utils import handle_cookie_consent


class PageNavigator:
    """Sayfa navigasyon işlemlerini yöneten sınıf"""
    
    def __init__(self, driver, selenium_driver=None):
        """
        Args:
            driver: Selenium WebDriver instance
            selenium_driver: SeleniumDriver instance (screenshot için)
        """
        self.driver = driver
        self.selenium_driver = selenium_driver
    
    def get_current_page_info(self) -> dict:
        """Mevcut sayfa bilgilerini alır (sayfa numarası ve toplam sayfa)"""
        try:
            page_label = self.driver.find_element(By.CSS_SELECTOR, "span.pagination-pages-label")
            page_text = page_label.text.strip()  # "Page 1 of 4"
            
            # "Page X of Y" formatını parse et
            match = re.search(r'Page (\d+) of (\d+)', page_text)
            if match:
                current_page = int(match.group(1))
                total_pages = int(match.group(2))
                return {
                    'current_page': current_page,
                    'total_pages': total_pages,
                    'has_next': current_page < total_pages,
                    'has_previous': current_page > 1
                }
            
            return {'current_page': 1, 'total_pages': 1, 'has_next': False, 'has_previous': False}
            
        except Exception as e:
            logger.warning(f"Sayfa bilgisi alınamadı: {e}")
            
            # Element bulunamadığında screenshot al
            if self.selenium_driver:
                self.selenium_driver.take_screenshot("pagination_not_found")
            
            return {'current_page': 1, 'total_pages': 1, 'has_next': False, 'has_previous': False}
    
    def go_to_next_page(self) -> bool:
        """Sonraki sayfaya gider"""
        try:
            logger.info("Sonraki sayfaya gidiliyor...")
            previous_info = self.get_current_page_info()
            expected_page = previous_info.get('current_page', 1) + 1

            # Tıklamadan önce banner varsa kapat
            handle_cookie_consent(self.driver, max_rounds=4, round_wait=0.35)

            # Next butonunu bul
            next_button = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button[aria-label='Next page']:not([disabled])"
                ))
            )

            try:
                next_button.click()
            except ElementClickInterceptedException:
                # Banner tıklamayı kesti — kapat ve tekrar dene
                logger.warning("Tıklama engellendi (cookie banner), kapatılıyor...")
                handle_cookie_consent(self.driver, max_rounds=6, round_wait=0.4)
                next_button = WebDriverWait(self.driver, 6).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        "button[aria-label='Next page']:not([disabled])"
                    ))
                )
                next_button.click()

            # Liste yüklenmesini bekle: aktif sayfa etiketinin hedef sayfaya gelmesini bekle
            try:
                WebDriverWait(self.driver, 8, poll_frequency=0.2).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, "span.pagination-pages-label").text.strip().startswith(f"Page {expected_page} ")
                )
            except TimeoutException:
                # Fallback: en azından pagination label görünür olsun
                WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "span.pagination-pages-label"))
                )
            
            logger.success("Sonraki sayfaya geçildi")
            handle_cookie_consent(self.driver, max_rounds=4, round_wait=0.35)
            return True
            
        except TimeoutException:
            logger.info("Sonraki sayfa bulunamadı (son sayfada olabilirsiniz)")
            return False
        except Exception as e:
            logger.failed("Sonraki sayfaya geçiş hatası", e)
            return False
    
    def go_to_previous_page(self) -> bool:
        """Önceki sayfaya gider"""
        try:
            logger.info("Önceki sayfaya gidiliyor...")
            previous_info = self.get_current_page_info()
            expected_page = max(1, previous_info.get('current_page', 1) - 1)

            # Tıklamadan önce banner varsa kapat
            handle_cookie_consent(self.driver, max_rounds=4, round_wait=0.35)

            # Previous butonunu bul
            prev_button = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button[aria-label='Previous page']:not([disabled])"
                ))
            )

            try:
                prev_button.click()
            except ElementClickInterceptedException:
                logger.warning("Tıklama engellendi (cookie banner), kapatılıyor...")
                handle_cookie_consent(self.driver, max_rounds=6, round_wait=0.4)
                prev_button = WebDriverWait(self.driver, 6).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        "button[aria-label='Previous page']:not([disabled])"
                    ))
                )
                prev_button.click()

            # Liste yüklenmesini bekle: aktif sayfa etiketinin hedef sayfaya gelmesini bekle
            try:
                WebDriverWait(self.driver, 8, poll_frequency=0.2).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, "span.pagination-pages-label").text.strip().startswith(f"Page {expected_page} ")
                )
            except TimeoutException:
                # Fallback: en azından pagination label görünür olsun
                WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "span.pagination-pages-label"))
                )
            
            logger.success("Önceki sayfaya geçildi")
            handle_cookie_consent(self.driver, max_rounds=4, round_wait=0.35)
            return True
            
        except TimeoutException:
            logger.info("Önceki sayfa bulunamadı (ilk sayfada olabilirsiniz)")
            return False
        except Exception as e:
            logger.failed("Önceki sayfaya geçiş hatası", e)
            return False
