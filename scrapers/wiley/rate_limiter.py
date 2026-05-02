"""
Rate limiting and retry logic for Wiley Online Library scraper.

Handles:
- Cloudflare challenge detection (429, 503, "Just a moment" title)
- HTTP rate limit responses
- Exponential backoff on consecutive failures
- Adaptive wait increases when errors pile up
"""

import time
import sys
from typing import Optional

sys.path.insert(0, str(__file__).rsplit('wiley', 1)[0])
from utils.logger import get_logger

logger = get_logger('wiley')


class RateLimitException(Exception):
    """Rate limit aşıldığında ve devam edilemediğinde fırlatılır"""
    pass


class WileyRateLimiter:
    """Wiley Online Library rate limiting ve retry yönetimi sınıfı"""

    # HTTP 429 / 503 yanıt metni
    RATE_LIMIT_KEYWORDS = [
        "too many requests",
        "rate limit",
        "service unavailable",
        "access denied",
        "403 forbidden",
    ]

    def __init__(self, driver, min_wait: float = 4, max_wait: float = 10):
        """
        Args:
            driver: SeleniumDriver instance
            min_wait: Minimum bekleme süresi (saniye)
            max_wait: Maksimum bekleme süresi (saniye)
        """
        self.driver = driver
        self.min_wait = min_wait
        self.max_wait = max_wait

        self.consecutive_errors = 0
        self.rate_limit_detected = False
        self.cloudflare_detected = False
        self.retry_count = 0
        self.max_retries = 3

        # Adaptive backoff
        self._current_backoff = min_wait

    # ------------------------------------------------------------------ #
    #  Detection
    # ------------------------------------------------------------------ #

    def check_cloudflare(self) -> bool:
        """Cloudflare challenge sayfası mı kontrol et"""
        try:
            # Title check — reliable indicator (driver._solve_cloudflare uses same approach)
            title = ""
            try:
                title = (
                    self.driver.execute_script("return document.title") or ""
                ).lower()
            except Exception:
                pass

            title_keywords = ["just a moment", "checking your browser", "lütfen bekleyin"]
            if any(kw in title for kw in title_keywords):
                self.cloudflare_detected = True
                logger.warning("Cloudflare challenge tespit edildi!")
                return True

            # DOM element check — specific CF challenge elements only
            # Avoids false positives from "cloudflare" / "please wait" in normal page HTML
            cf_element_js = (
                "return !!(document.getElementById('cf-challenge-running') || "
                "document.querySelector('.cf-browser-verification') || "
                "document.querySelector('[data-cf-challenge]') || "
                "document.querySelector('div.cf-challenge-container'))"
            )
            try:
                if self.driver.execute_script(cf_element_js):
                    self.cloudflare_detected = True
                    logger.warning("Cloudflare challenge tespit edildi!")
                    return True
            except Exception:
                pass

            return False
        except Exception as e:
            logger.warning(f"Cloudflare kontrol hatası: {e}")
            return False

    def check_rate_limit(self) -> bool:
        """HTTP rate limit mesajı var mı kontrol et"""
        try:
            page_text = (self.driver.page_source or "").lower()
            detected = any(kw in page_text for kw in self.RATE_LIMIT_KEYWORDS)

            if detected:
                self.rate_limit_detected = True
                logger.warning("Rate limit yanıtı tespit edildi!")

            return detected
        except Exception as e:
            logger.warning(f"Rate limit kontrol hatası: {e}")
            return False

    def check_page_blocked(self) -> bool:
        """Sayfa erişim engeli var mı (Cloudflare veya rate limit)"""
        return self.check_cloudflare() or self.check_rate_limit()

    # ------------------------------------------------------------------ #
    #  Backoff / wait
    # ------------------------------------------------------------------ #

    def record_success(self):
        """Başarılı istek sonrası sayaçları sıfırla"""
        self.consecutive_errors = 0
        self.retry_count = 0
        self.rate_limit_detected = False
        self.cloudflare_detected = False
        self._current_backoff = self.min_wait

    def record_failure(self):
        """Başarısız istek sonrası sayaçları artır ve backoff güncelle"""
        self.consecutive_errors += 1
        self.retry_count += 1
        # Her hatada backoff %50 artır, max_wait * 3 ile kırp
        self._current_backoff = min(
            self._current_backoff * 1.5,
            self.max_wait * 3
        )

    def wait_after_failure(self, extra_seconds: float = 0) -> None:
        """Hata sonrası adaptif bekleme"""
        wait = self._current_backoff + extra_seconds
        logger.info(f"Hata sonrası bekleme: {wait:.1f}s (ardışık hata: {self.consecutive_errors})")
        time.sleep(wait)

    def wait_for_cloudflare(self, seconds: float = 12) -> None:
        """Cloudflare challenge için bekleme"""
        logger.info(f"Cloudflare için {seconds}s bekleniyor...")
        time.sleep(seconds)

    # ------------------------------------------------------------------ #
    #  Handle
    # ------------------------------------------------------------------ #

    def handle_cloudflare(self) -> bool:
        """
        Cloudflare challenge yönetimi.

        Returns:
            bool: Challenge geçildiyse True
        Raises:
            RateLimitException: Maksimum deneme aşıldıysa
        """
        if self.retry_count >= self.max_retries:
            raise RateLimitException(
                f"Wiley Cloudflare challenge {self.max_retries} denemede aşılamadı."
            )

        self.retry_count += 1
        logger.warning(f"Cloudflare challenge (deneme {self.retry_count}/{self.max_retries})...")

        # Kısa bekle — Cloudflare otomatik çözülebilir
        self.wait_for_cloudflare(seconds=12)

        # Tekrar kontrol
        if not self.check_cloudflare():
            logger.success("Cloudflare challenge geçildi!")
            self.cloudflare_detected = False
            return True

        # SeleniumBase captcha çözücü dene (driver'da _sb varsa)
        sb = getattr(self.driver, '_sb', None)
        if sb:
            try:
                logger.info("solve_captcha() deneniyor...")
                sb.solve_captcha()
                time.sleep(3)
                if not self.check_cloudflare():
                    logger.success("Cloudflare solve_captcha() ile çözüldü!")
                    return True
            except Exception as e:
                logger.warning(f"solve_captcha() hatası: {e}")

            try:
                logger.info("uc_gui_click_captcha() deneniyor...")
                sb.uc_gui_click_captcha()
                time.sleep(5)
                if not self.check_cloudflare():
                    logger.success("Cloudflare uc_gui_click_captcha() ile çözüldü!")
                    return True
            except Exception as e:
                logger.warning(f"uc_gui_click_captcha() hatası: {e}")

        logger.warning("Cloudflare geçilemedi, devam ediliyor...")
        return False

    def reset(self):
        """Rate limiter durumunu sıfırla"""
        self.consecutive_errors = 0
        self.rate_limit_detected = False
        self.cloudflare_detected = False
        self.retry_count = 0
        self._current_backoff = self.min_wait
