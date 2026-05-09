"""Utility helpers for Springer scraper."""

import re
import sys
import time

sys.path.insert(0, str(__file__).rsplit("springer", 1)[0])
from utils.logger import get_logger

logger = get_logger("springer")


def handle_cookie_consent(selenium_driver, timeout: int = 5) -> bool:
    logger.info("Cookie consent kontrol ediliyor...")

    selectors = [
        # Springer consent banner (provided by user)
        "button[data-cc-action='reject']",
        "button[data-cc-action='accept']",
        ".cc-banner__button-reject",
        ".cc-banner__button-accept",
        # Generic / other CMP fallbacks
        "#onetrust-accept-btn-handler",
        "button[class*='accept']",
        "button[class*='reject']",
        "button[aria-label*='accept' i]",
        "button[aria-label*='reject' i]",
    ]

    try:
        if selenium_driver._cdp_active and selenium_driver._sb:
            for selector in selectors:
                try:
                    clicked = selenium_driver._sb.cdp.click_if_visible(selector)
                    if not clicked:
                        continue
                    logger.success(f"Cookie popup kapatildi (CDP) [{selector}]")
                    time.sleep(0.4)
                    return True
                except Exception:
                    continue

            # Text-based fallback for consent buttons
            try:
                clicked_by_text = selenium_driver.execute_script(
                    """
                    return (function() {
                        const btns = Array.from(document.querySelectorAll('button'));
                        const targets = ['reject optional cookies', 'accept all cookies'];
                        for (const b of btns) {
                            const txt = (b.innerText || b.textContent || '').toLowerCase().trim();
                            if (targets.includes(txt)) {
                                b.click();
                                return txt;
                            }
                        }
                        return '';
                    })();
                    """
                )
                if clicked_by_text:
                    logger.success(f"Cookie popup kapatildi (CDP-text) [{clicked_by_text}]")
                    time.sleep(0.4)
                    return True
            except Exception:
                pass

            logger.info("Cookie popup bulunamadi (CDP)")
            return False

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        for selector in selectors:
            try:
                element = WebDriverWait(selenium_driver.driver, timeout).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                element.click()
                logger.success(f"Cookie popup kapatildi [{selector}]")
                time.sleep(0.4)
                return True
            except Exception:
                continue

        # Selenium fallback by visible text
        for button_text in ["Reject optional cookies", "Accept all cookies"]:
            try:
                element = WebDriverWait(selenium_driver.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, f"//button[normalize-space()='{button_text}']"))
                )
                element.click()
                logger.success(f"Cookie popup kapatildi [text={button_text}]")
                time.sleep(0.4)
                return True
            except Exception:
                continue

        logger.info("Cookie popup bulunamadi")
        return False
    except Exception as exc:
        logger.warning(f"Cookie consent hatasi: {exc}")
        return False


def wait_for_page_load(selenium_driver, timeout: int = 30) -> bool:
    return selenium_driver.wait_for_page_load(timeout)


def extract_journal_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/journal/(\d+)", url)
    return match.group(1) if match else ""


def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
