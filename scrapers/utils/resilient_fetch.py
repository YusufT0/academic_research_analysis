"""
Dayanıklı sayfa getirme — yavaş/dengesiz internet için tek nokta.

Ayrımlar:
- transient (yavaş timeout)  → aynı driver'da artan timeout + backoff, RESTART YOK
- fatal (net::ERR_/session death) → driver_obj.restart() sonra tekrar dene
- hard (retry edilemez)      → hemen başarısız dön

TimeoutException'da window.stop() + beklenen selector/readyState kontrolü ile
KISMİ sayfa kurtarılır (settings.partial_page_recovery_enabled).

Mevcut altyapı yeniden kullanılır: backend.core.circuit_breaker.get_circuit_breaker.
Yeni bir şey icat edilmez.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from selenium.common.exceptions import TimeoutException, WebDriverException

from backend.core.config import settings
from backend.core.circuit_breaker import get_circuit_breaker
from utils.logger import get_logger

logger = get_logger("resilient_fetch")

# Driver/session ölümü = restart gerektiren fatal hatalar
_FATAL_SUBSTR = (
    "net::err_",
    "session deleted",
    "invalid session id",
    "disconnected",
    "chrome not reachable",
    "tab crashed",
    "no such window",
    "web view not found",
    "renderer",
)

_TRANSFER_JS = (
    "try{return performance.getEntriesByType('resource')"
    ".reduce((a,r)=>a+(r.transferSize||0),0);}catch(e){return -1;}"
)


@dataclass
class FetchResult:
    """resilient_get sonucu."""
    ok: bool = False
    partial: bool = False           # kısmi sayfa (timeout sonrası kurtarıldı)
    recovered: bool = False         # timeout_but_recovered
    attempts: int = 0
    duration_s: float = 0.0
    transfer_bytes: int = -1
    error: Optional[str] = None
    error_kind: Optional[str] = None  # transient|fatal|hard|circuit_open

    def __bool__(self) -> bool:  # `if driver.get(...)` geriye dönük uyum
        return self.ok


def classify_selenium_error(exc: Exception) -> str:
    """Hata türünü belirle: 'transient' | 'fatal' | 'hard'."""
    if isinstance(exc, TimeoutException):
        return "transient"
    msg = (str(exc) or "").lower()
    if any(s in msg for s in _FATAL_SUBSTR):
        return "fatal"
    if isinstance(exc, WebDriverException):
        # Bilinmeyen WebDriver hatası — temkinli davran, fatal say (restart)
        return "fatal"
    return "hard"


def _read_transfer_bytes(wd) -> int:
    try:
        return int(wd.execute_script(_TRANSFER_JS))
    except Exception:
        return -1


def _dom_usable(wd, expected_selector: Optional[str]) -> bool:
    """Kısmi sayfa kullanılabilir mi? Beklenen selector varsa onu, yoksa
    readyState'i kontrol et."""
    try:
        if expected_selector:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            WebDriverWait(wd, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, expected_selector))
            )
            return True
        state = wd.execute_script("return document.readyState")
        return state in ("interactive", "complete")
    except Exception:
        return False


def _wait_ready(wd, timeout: float) -> None:
    """readyState complete bekle (best-effort)."""
    try:
        from selenium.webdriver.support.ui import WebDriverWait

        WebDriverWait(wd, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass


def resilient_get(
    driver_obj,
    url: str,
    *,
    expected_selector: Optional[str] = None,
    wait_after: int = 3,
    scraper_name: str = "scraper",
    base_timeout: Optional[int] = None,
) -> FetchResult:
    """
    Dayanıklı sayfa getirme.

    Args:
        driver_obj: SeleniumDriver wrapper (.driver, .restart(), .start())
        url: gidilecek URL
        expected_selector: kısmi-kurtarma için beklenen CSS selector (opsiyonel)
        wait_after: readyState beklemesi için taban (sn)
        scraper_name: circuit breaker / log anahtarı (ieee, sciencedirect, ...)
        base_timeout: taban page-load timeout (None → driver'daki mevcut)
    """
    breaker = get_circuit_breaker(
        scraper_name,
        failure_threshold=settings.cb_failure_threshold,
        recovery_timeout=settings.cb_recovery_timeout,
    )

    if not breaker.can_execute():
        logger.warning(
            "fetch_skipped_circuit_open",
            scraper=scraper_name,
            url=url,
            retry_after=round(breaker.time_until_recovery, 1),
        )
        return FetchResult(ok=False, error="circuit_open", error_kind="circuit_open")

    max_attempts = max(1, settings.retry_max)
    backoff_base = settings.retry_backoff_base
    backoff_cap = settings.retry_backoff_cap
    base_to = base_timeout or settings.max_page_load_timeout_cap
    started = time.perf_counter()

    result = FetchResult()

    for attempt in range(max_attempts):
        result.attempts = attempt + 1

        # Driver yoksa başlat (start() ailesine göre bool veya driver döner /
        # exception fırlatabilir — hepsini güvenli ele al)
        if getattr(driver_obj, "driver", None) is None:
            try:
                driver_obj.start()
            except Exception as e:
                logger.failed("driver_start_failed", e)
            if getattr(driver_obj, "driver", None) is None:
                result.error = "driver_start_failed"
                result.error_kind = "fatal"
                break
        wd = driver_obj.driver

        # Denemeye göre artan timeout (restart YOK, sadece daha sabırlı)
        per_attempt_timeout = min(
            int(base_to * (backoff_base ** attempt)),
            settings.max_page_load_timeout_cap,
        )
        try:
            wd.set_page_load_timeout(per_attempt_timeout)
        except Exception:
            pass

        try:
            if attempt > 0:
                logger.info("fetch_retry", scraper=scraper_name, url=url,
                            attempt=attempt + 1, timeout=per_attempt_timeout)
            wd.get(url)
            _wait_ready(wd, max(wait_after * 5, 15))
            # Safety net: stop any leftover resource loads so the browser tab
            # doesn't spin indefinitely. No-op when readyState is already complete.
            # Called AFTER _wait_ready so async redirect scripts have time to run.
            try:
                wd.execute_script("window.stop();")
            except Exception:
                pass
            time.sleep(0.3)  # kısa DOM render buffer

            result.ok = True
            result.transfer_bytes = _read_transfer_bytes(wd)
            result.duration_s = round(time.perf_counter() - started, 2)
            breaker.record_success()
            logger.info(
                "fetch_complete", scraper=scraper_name, url=url,
                duration_s=result.duration_s, attempts=result.attempts,
                transfer_bytes=result.transfer_bytes, partial=False, recovered=False,
            )
            return result

        except Exception as e:
            kind = classify_selenium_error(e)
            result.error = str(e)[:300]
            result.error_kind = kind

            if kind == "transient":
                # Kısmi sayfa kurtarma denemesi
                if settings.partial_page_recovery_enabled:
                    try:
                        wd.execute_script("window.stop();")
                    except Exception:
                        pass
                    if _dom_usable(wd, expected_selector):
                        result.ok = True
                        result.partial = True
                        result.recovered = True
                        result.transfer_bytes = _read_transfer_bytes(wd)
                        result.duration_s = round(time.perf_counter() - started, 2)
                        breaker.record_success()
                        logger.info(
                            "fetch_complete", scraper=scraper_name, url=url,
                            duration_s=result.duration_s, attempts=result.attempts,
                            transfer_bytes=result.transfer_bytes,
                            partial=True, recovered=True,
                            timeout_but_recovered=True,
                        )
                        return result
                # Kurtarılamadı → backoff + aynı driver'da tekrar (RESTART YOK)
                if attempt < max_attempts - 1:
                    wait = min(backoff_base ** (attempt + 1), backoff_cap)
                    logger.warning("fetch_timeout_retry", scraper=scraper_name,
                                   url=url, attempt=attempt + 1, backoff_s=round(wait, 1))
                    time.sleep(wait)
                    continue

            elif kind == "fatal":
                logger.failed("fetch_fatal_error", e)
                if attempt < max_attempts - 1:
                    logger.warning("driver_restart", scraper=scraper_name, url=url,
                                    attempt=attempt + 1)
                    if not driver_obj.restart():
                        result.error = "driver_restart_failed"
                        break
                    time.sleep(min(backoff_base ** (attempt + 1), backoff_cap))
                    continue

            else:  # hard — retry edilemez
                logger.failed("fetch_hard_error", e)
                break

    # Tüm denemeler tükendi / kırıldı
    result.ok = False
    result.duration_s = round(time.perf_counter() - started, 2)
    breaker.record_failure()
    logger.error(
        "fetch_failed", scraper=scraper_name, url=url,
        attempts=result.attempts, duration_s=result.duration_s,
        error_kind=result.error_kind, error=result.error,
    )
    return result
