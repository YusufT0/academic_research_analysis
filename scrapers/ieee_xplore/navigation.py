"""
Page navigation functions for IEEE Xplore scraper
"""

import sys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

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
            # Not: Driver'da implicit_wait(10) açık olduğu için opsiyonel elementler
            # (ör. ilk sayfada prev-btn) find_element ile sorgulanırsa her seferinde
            # 10 sn gecikme yaratır. Bu yüzden tek seferde JS ile anlık DOM okuyoruz.
            dom_info = self.driver.execute_script("""
                const ul = document.querySelector('div.pagination-bar ul');
                if (!ul) {
                    return { current_page: 1, total_pages: 1, has_next: false, has_previous: false };
                }

                const active = ul.querySelector('button.active');
                const current = parseInt((active?.textContent || '1').trim(), 10) || 1;

                const pageButtons = Array.from(
                    ul.querySelectorAll('li:not(.prev-btn):not(.next-btn) button')
                );
                const pages = pageButtons
                    .map(btn => parseInt((btn.textContent || '').trim(), 10))
                    .filter(Number.isFinite);
                const total = pages.length ? Math.max(...pages) : current;

                return {
                    current_page: current,
                    total_pages: total,
                    has_previous: !!ul.querySelector('li.prev-btn'),
                    has_next: !!ul.querySelector('li.next-btn')
                };
            """)

            current_page = int(dom_info.get('current_page', 1))
            total_pages = int(dom_info.get('total_pages', current_page))
            has_previous = bool(dom_info.get('has_previous', False))
            has_next = bool(dom_info.get('has_next', False))
            
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

    def _get_current_page_number_fast(self) -> int:
        """Log üretmeden mevcut aktif sayfa numarasını döner."""
        try:
            return int(self.driver.execute_script("""
                const active = document.querySelector('div.pagination-bar ul button.active');
                return parseInt((active?.textContent || '1').trim(), 10) || 1;
            """))
        except Exception:
            return 1

    def _get_first_result_key_fast(self) -> str:
        """İlk sonuç kartını tanımlamak için hızlı bir anahtar üretir."""
        try:
            return str(self.driver.execute_script("""
                const a = document.querySelector('xpl-browse-results-item h2 a');
                if (!a) return '';
                const href = (a.getAttribute('href') || '').trim();
                const text = (a.textContent || '').trim();
                return `${href}|${text}`;
            """))
        except Exception:
            return ""
    
    def _wait_for_page_load(self, expected_page: int = None, previous_first_key: str = "", timeout: int = 12):
        """
        Tıklama sonrası sayfanın tamamen yüklenmesini bekler.
        Strateji:
          Tek bir birleşik koşulda bekleyerek timeout birikmesini engeller.
        """
        def _page_ready(_driver):
            state = _driver.execute_script("""
                const active = document.querySelector('div.pagination-bar ul button.active');
                const currentPage = parseInt((active?.textContent || '1').trim(), 10) || 1;

                // Only check content-area spinners; AI-search and generic spinners
                // can remain active in the background after content has loaded.
                const spinner = document.querySelector(
                    'xpl-browse-results-list .List-results-message i.fa-spinner.fa-spin, ' +
                    '.progress-spinner-container-normal .fa-spinner.fa-spin, ' +
                    '.progress-spinner-container-small .fa-spinner.fa-spin'
                );
                const spinnerVisible = !!(spinner && spinner.offsetParent !== null);

                const first = document.querySelector('xpl-browse-results-item h2 a');
                const firstKey = first
                    ? `${(first.getAttribute('href') || '').trim()}|${(first.textContent || '').trim()}`
                    : '';

                const hasResults = !!document.querySelector('xpl-browse-results-item');

                return {
                    currentPage,
                    spinnerVisible,
                    hasResults,
                    firstKey
                };
            """)

            page_ok = (expected_page is None) or (int(state.get('currentPage', 1)) == expected_page)
            spinner_ok = not bool(state.get('spinnerVisible', False))
            results_ok = bool(state.get('hasResults', False))

            if previous_first_key and expected_page is None:
                first_changed = str(state.get('firstKey', '')) and str(state.get('firstKey', '')) != previous_first_key
                return results_ok and first_changed

            # Content is ready when we're on the correct page and results are present.
            # Don't block on background spinners that persist after content loads.
            if page_ok and results_ok:
                return True
            return page_ok and spinner_ok and results_ok

        try:
            WebDriverWait(self.driver, timeout, poll_frequency=0.2).until(_page_ready)
        except TimeoutException:
            # Fallback: en azından sonuçlar ve pagination görünür olsun
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'xpl-browse-results-item'))
                )
            except TimeoutException:
                pass

    def go_to_next_page(self) -> bool:
        """
        Sonraki sayfaya gider
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.info("Sonraki sayfaya gidiliyor...")
            current_page = self._get_current_page_number_fast()
            expected_page = current_page + 1
            previous_first_key = self._get_first_result_key_fast()
            
            # Next butonunu bul (li.next-btn içindeki button)
            next_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 
                    "li.next-btn button"
                ))
            )
            
            # Butona tıkla
            next_button.click()
            
            # Sayfa tamamen yüklenene kadar bekle
            self._wait_for_page_load(
                expected_page=expected_page,
                previous_first_key=previous_first_key,
            )
            
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
            current_page = self._get_current_page_number_fast()
            expected_page = max(1, current_page - 1)
            previous_first_key = self._get_first_result_key_fast()
            
            # Previous butonunu bul (li.prev-btn içindeki button)
            prev_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, 
                    "li.prev-btn button"
                ))
            )
            
            # Butona tıkla
            prev_button.click()
            
            # Sayfa tamamen yüklenene kadar bekle
            self._wait_for_page_load(
                expected_page=expected_page,
                previous_first_key=previous_first_key,
            )
            
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
            previous_first_key = self._get_first_result_key_fast()
            
            # İlgili sayfa butonunu bul
            page_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH, 
                    f"//button[contains(@aria-label, 'Page {page_number}')]"
                ))
            )
            
            # Butona tıkla
            page_button.click()
            
            # Sayfa tamamen yüklenene kadar bekle
            self._wait_for_page_load(
                expected_page=page_number,
                previous_first_key=previous_first_key,
            )
            
            logger.success(f"Sayfa {page_number}'e geçildi")
            return True
            
        except TimeoutException:
            logger.error(f"Sayfa {page_number} butonu bulunamadı")
            return False
        except Exception as e:
            logger.error(f"Sayfa {page_number}'e geçiş hatası: {e}")
            return False
