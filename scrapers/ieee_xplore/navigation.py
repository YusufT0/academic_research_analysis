"""
Page navigation functions for IEEE Xplore scraper
"""

import sys
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

sys.path.insert(0, str(__file__).rsplit('ieee_xplore', 1)[0])
from utils.logger import get_logger
logger = get_logger('ieee_xplore')


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
        """
        Mevcut sayfa bilgilerini alır
        
        Returns:
            dict: {
                'current_page': int,
                'total_pages': int,
                'has_next': bool,
                'has_previous': bool
            }
        """
        try:
            # Pagination bar'ı bul
            pagination_div = self.driver.find_element(
                By.CSS_SELECTOR, 
                "div.pagination-bar ul"
            )
            
            # Aktif sayfa numarasını bul (class="active" olan button)
            active_button = pagination_div.find_element(
                By.CSS_SELECTOR, 
                "button.active"
            )
            current_page = int(active_button.text.strip())
            
            # Tüm sayfa butonlarını bul
            page_buttons = pagination_div.find_elements(
                By.CSS_SELECTOR, 
                "li:not(.prev-btn):not(.next-btn) button"
            )
            
            # Toplam sayfa sayısını bul (en büyük sayfa numarası)
            total_pages = current_page
            for button in page_buttons:
                try:
                    page_num = int(button.text.strip())
                    if page_num > total_pages:
                        total_pages = page_num
                except ValueError:
                    continue
            
            # Previous button var mı kontrol et
            has_previous = False
            try:
                prev_btn = pagination_div.find_element(By.CSS_SELECTOR, "li.prev-btn")
                has_previous = True
            except NoSuchElementException:
                has_previous = False
            
            # Next button var mı kontrol et
            has_next = False
            try:
                next_btn = pagination_div.find_element(By.CSS_SELECTOR, "li.next-btn")
                has_next = True
            except NoSuchElementException:
                has_next = False
            
            page_info = {
                'current_page': current_page,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_previous': has_previous
            }
            
            # Sayfa bilgisini yazdır
            logger.section("Sayfa Bilgisi")
            logger.info(f"Mevcut Sayfa: {current_page}/{total_pages}")
            logger.info(f"Önceki Sayfa: {'✓ Var' if has_previous else '✗ Yok (İlk sayfa)'}")
            logger.info(f"Sonraki Sayfa: {'✓ Var' if has_next else '✗ Yok (Son sayfa)'}")
            
            return page_info
            
        except Exception as e:
            logger.warning(f"Sayfa bilgisi alınamadı: {e}")
            
            # Element bulunamadığında screenshot al
            if self.selenium_driver:
                self.selenium_driver.take_screenshot("pagination_not_found")
            
            return {
                'current_page': 1, 
                'total_pages': 1, 
                'has_next': False, 
                'has_previous': False
            }
    
    def go_to_next_page(self) -> bool:
        """
        Sonraki sayfaya gider
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.info("Sonraki sayfaya gidiliyor...")
            
            # Next butonunu bul (li.next-btn içindeki button)
            next_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 
                    "li.next-btn button"
                ))
            )
            
            # Butona tıkla
            next_button.click()
            
            # Sayfanın yüklenmesini bekle
            time.sleep(3)
            
            logger.success("Sonraki sayfaya geçildi")
            return True
            
        except TimeoutException:
            logger.info("Sonraki sayfa butonu bulunamadı (son sayfadasınız)")
            return False
        except Exception as e:
            logger.error(f"Sonraki sayfaya geçiş hatası: {e}")
            return False
    
    def go_to_previous_page(self) -> bool:
        """
        Önceki sayfaya gider
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.info("Önceki sayfaya gidiliyor...")
            
            # Previous butonunu bul (li.prev-btn içindeki button)
            prev_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 
                    "li.prev-btn button"
                ))
            )
            
            # Butona tıkla
            prev_button.click()
            
            # Sayfanın yüklenmesini bekle
            time.sleep(3)
            
            logger.success("Önceki sayfaya geçildi")
            return True
            
        except TimeoutException:
            logger.info("Önceki sayfa butonu bulunamadı (ilk sayfadasınız)")
            return False
        except Exception as e:
            logger.error(f"Önceki sayfaya geçiş hatası: {e}")
            return False
    
    def go_to_page(self, page_number: int) -> bool:
        """
        Belirli bir sayfaya gider
        
        Args:
            page_number: Gidilecek sayfa numarası
            
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.info(f"Sayfa {page_number}'e gidiliyor...")
            
            # İlgili sayfa butonunu bul
            page_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH, 
                    f"//button[contains(@aria-label, 'Page {page_number}')]"
                ))
            )
            
            # Butona tıkla
            page_button.click()
            
            # Sayfanın yüklenmesini bekle
            time.sleep(3)
            
            logger.success(f"Sayfa {page_number}'e geçildi")
            return True
            
        except TimeoutException:
            logger.error(f"Sayfa {page_number} butonu bulunamadı")
            return False
        except Exception as e:
            logger.error(f"Sayfa {page_number}'e geçiş hatası: {e}")
            return False
