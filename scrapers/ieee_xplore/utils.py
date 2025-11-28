"""
Utility functions for IEEE Xplore scraper
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def handle_cookie_consent(driver, timeout: int = 5) -> bool:
    """
    IEEE Xplore cookie consent popup'ını kapat
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Popup bekleme süresi (saniye) - kısa tutulur
        
    Returns:
        bool: Cookie popup bulundu ve kapatıldıysa True
    """
    try:
        print("🍪 Cookie consent kontrol ediliyor...")
        
        # IEEE Xplore'da farklı cookie popup selektörleri deneyeceğiz
        cookie_selectors = [
            # OneTrust (en yaygın)
            (By.ID, "onetrust-accept-btn-handler"),
            (By.CLASS_NAME, "onetrust-close-btn-handler"),
            # Genel accept butonları
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]"),
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"),
        ]
        
        # Kısa timeout ile dene - yoksa hızlıca devam et
        for by, selector in cookie_selectors:
            print(f"  → Cookie popup aranıyor: {selector}")
            try:
                # Kısa süre bekle, bulamazsan bir sonraki selektöre geç
                element = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((by, selector))
                )

                if not element:
                    continue

                print(f"  → Cookie popup bulundu: {selector}")
                
                # Elementi tıkla
                element.click()
                print(f"  ✓ Cookie popup kapatıldı")
                time.sleep(1)
                return True
                    
            except:
                # Bu selektör bulunamadı, bir sonrakine geç
                continue
        
        print("  ℹ Cookie popup bulunamadı (zaten kabul edilmiş veya yok)")
        return False
        
    except Exception as e:
        print(f"  ⚠ Cookie consent hatası: {e}")
        return False


def wait_for_page_load(driver, timeout: int = 30) -> bool:
    """
    Sayfanın tamamen yüklenmesini bekle
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Maksimum bekleme süresi (saniye)
        
    Returns:
        bool: Sayfa yüklendiyse True
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        return True
    except Exception as e:
        print(f"  ⚠ Sayfa yükleme timeout: {e}")
        return False


def scroll_to_bottom(driver, pause_time: float = 1.0) -> None:
    """
    Sayfayı en alta kadar scroll et
    
    Args:
        driver: Selenium WebDriver instance
        pause_time: Her scroll arasında bekleme süresi
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        # Wait to load page
        time.sleep(pause_time)
        
        # Calculate new scroll height and compare with last scroll height
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
