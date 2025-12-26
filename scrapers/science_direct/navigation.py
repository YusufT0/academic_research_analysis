"""
Page navigation functions for Science Direct scraper
"""

import sys
import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')


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
            
            # Next butonunu bul
            next_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 
                    "button[aria-label='Next page']:not([disabled])"
                ))
            )
            
            next_button.click()
            time.sleep(2)  # Sayfanın yüklenmesini bekle
            
            logger.success("Sonraki sayfaya geçildi")
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
            
            # Previous butonunu bul
            prev_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 
                    "button[aria-label='Previous page']:not([disabled])"
                ))
            )
            
            prev_button.click()
            time.sleep(2)  # Sayfanın yüklenmesini bekle
            
            logger.success("Önceki sayfaya geçildi")
            return True
            
        except TimeoutException:
            logger.info("Önceki sayfa bulunamadı (ilk sayfada olabilirsiniz)")
            return False
        except Exception as e:
            logger.failed("Önceki sayfaya geçiş hatası", e)
            return False
