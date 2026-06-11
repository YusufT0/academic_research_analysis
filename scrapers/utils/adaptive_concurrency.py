"""
Adaptif eşzamanlılık — yavaş/dengesiz hatta worker (tab) havuzunu küçült,
sağlıklıyken talep edilen tavana kadar büyüt (AIMD + cooldown).

Yavaş hatta N ağır Chrome sekmesi hattı doyurup hepsi birden timeout olur
(congestion collapse). Bu controller hata oranına göre worker sayısını
multiplicative-decrease / additive-increase ile ayarlar.

Worker'lar issue başında bir kez spawn edildiğinden değişiklik bir SONRAKİ
issue'da etkilidir (basit ve yeterli; mid-issue resize takip işi).
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict

from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger("adaptive_concurrency")


@dataclass
class _ScraperState:
    requested: int = 3                       # son talep edilen tavan
    current: int = 0                         # mevcut efektif worker sayısı
    window: Deque[bool] = field(default_factory=lambda: deque())  # True=ok
    fetches_since_resize: int = 0


class ConcurrencyController:
    """Scraper adına göre tekil (singleton), thread-safe."""

    _instance: "ConcurrencyController" = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._states = {}
                    cls._instance._lock = threading.Lock()
        return cls._instance

    def _state(self, scraper: str) -> _ScraperState:
        st = self._states.get(scraper)
        if st is None:
            st = _ScraperState()
            self._states[scraper] = st
        return st

    def effective_max_tabs(self, scraper: str, requested: int) -> int:
        """Bu issue için kullanılacak worker sayısı."""
        if not settings.adaptive_concurrency_enabled:
            return requested

        ceiling = min(requested, settings.adaptive_max_tabs)
        floor = settings.adaptive_min_tabs

        with self._lock:
            st = self._state(scraper)
            st.requested = requested
            if st.current <= 0:
                st.current = ceiling
            # Tavan/zemin sınırlarına kelepçele
            st.current = max(floor, min(st.current, ceiling))
            eff = st.current

        logger.info(
            "concurrency_effective",
            scraper=scraper, requested=requested, effective=eff,
        )
        return eff

    def record(self, scraper: str, ok: bool, duration_s: float = 0.0,
               recovered: bool = False) -> None:
        """Tek bir fetch sonucunu kaydet; gerekirse worker sayısını ayarla."""
        if not settings.adaptive_concurrency_enabled:
            return

        with self._lock:
            st = self._state(scraper)
            win = st.window
            win.append(bool(ok))
            while len(win) > settings.adaptive_window:
                win.popleft()
            st.fetches_since_resize += 1

            if (len(win) < settings.adaptive_window
                    or st.fetches_since_resize < settings.adaptive_cooldown_fetches):
                return

            errors = sum(1 for v in win if not v)
            error_rate = errors / len(win)
            ceiling = min(st.requested, settings.adaptive_max_tabs)
            floor = settings.adaptive_min_tabs
            old = st.current
            reason = None

            if error_rate > settings.adaptive_error_hi and st.current > floor:
                # Multiplicative decrease
                st.current = max(floor, st.current // 2)
                reason = "high_error_rate"
            elif error_rate < settings.adaptive_error_lo and st.current < ceiling:
                # Additive increase
                st.current = min(ceiling, st.current + 1)
                reason = "healthy"

            if reason:
                st.fetches_since_resize = 0
                logger.warning(
                    "concurrency_adjusted",
                    scraper=scraper, previous=old, effective=st.current,
                    error_rate=round(error_rate, 2), reason=reason,
                )


# Modül seviyesi tekil erişim
controller = ConcurrencyController()
