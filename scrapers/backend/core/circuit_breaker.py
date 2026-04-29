"""
Circuit Breaker Pattern

Scraper'lar ardışık hata aldığında otomatik devre kesici.
Durumlar: CLOSED → OPEN → HALF_OPEN → CLOSED

Kullanım:
    breaker = ScraperCircuitBreaker("ieee", failure_threshold=5, recovery_timeout=300)
    
    if breaker.can_execute():
        try:
            result = scrape()
            breaker.record_success()
        except Exception as e:
            breaker.record_failure()
            raise
    else:
        raise CircuitOpenError(breaker)
"""

import time
import threading
from enum import Enum
from typing import Optional, Dict

from utils.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitState(str, Enum):
    """Circuit breaker durumları"""
    CLOSED = "closed"       # Normal çalışma
    OPEN = "open"           # Devre açık, istekler reddedilir
    HALF_OPEN = "half_open" # Test aşaması, sınırlı istek


class CircuitOpenError(Exception):
    """Circuit açık olduğunda fırlatılır"""
    def __init__(self, breaker: "ScraperCircuitBreaker"):
        self.breaker = breaker
        self.retry_after = breaker.time_until_recovery
        super().__init__(
            f"Circuit breaker '{breaker.name}' is OPEN. "
            f"Retry after {self.retry_after:.0f}s"
        )


class ScraperCircuitBreaker:
    """
    Tek bir scraper için circuit breaker.
    
    CLOSED: Normal çalışma. Hata sayısı threshold'a ulaşırsa OPEN'a geç.
    OPEN: İstekler reddedilir. recovery_timeout sonra HALF_OPEN'a geç.
    HALF_OPEN: Tek bir deneme yapılır. Başarılıysa CLOSED, değilse OPEN.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 300,  # 5 dakika
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.time()
        self._lock = threading.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Mevcut durumu kontrol et (OPEN → HALF_OPEN geçişi otomatik)"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_transition_to_half_open():
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state
    
    @property
    def failure_count(self) -> int:
        return self._failure_count
    
    @property
    def time_until_recovery(self) -> float:
        """OPEN durumunda kalan bekleme süresi (saniye)"""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)
    
    def can_execute(self) -> bool:
        """İstek yapılabilir mi?"""
        current_state = self.state  # Otomatik geçiş tetikler
        
        if current_state == CircuitState.CLOSED:
            return True
        
        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
            return False
        
        # OPEN
        return False
    
    def record_success(self):
        """Başarılı işlem kaydet"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN'da başarı → CLOSED'a dön
                self._transition_to(CircuitState.CLOSED)
                logger.info(
                    "Circuit breaker recovered",
                    breaker=self.name,
                    previous_failures=self._failure_count,
                )
            
            self._failure_count = 0
            self._success_count += 1
    
    def record_failure(self):
        """Başarısız işlem kaydet"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN'da hata → tekrar OPEN
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    "Circuit breaker re-opened (half-open test failed)",
                    breaker=self.name,
                    failure_count=self._failure_count,
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.error(
                        "Circuit breaker OPENED",
                        breaker=self.name,
                        failure_count=self._failure_count,
                        threshold=self.failure_threshold,
                        recovery_timeout=self.recovery_timeout,
                    )
    
    def reset(self):
        """Manuel reset — API üzerinden çağrılabilir"""
        with self._lock:
            old_state = self._state
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            logger.info(
                "Circuit breaker manually reset",
                breaker=self.name,
                previous_state=old_state.value,
            )
    
    def get_status(self) -> dict:
        """API response için durum bilgisi"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "time_until_recovery": round(self.time_until_recovery, 1),
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
        }
    
    def _should_transition_to_half_open(self) -> bool:
        """OPEN → HALF_OPEN geçişi yapılmalı mı?"""
        if self._last_failure_time is None:
            return False
        return (time.time() - self._last_failure_time) >= self.recovery_timeout
    
    def _transition_to(self, new_state: CircuitState):
        """Durum geçişi yap"""
        self._state = new_state
        self._last_state_change = time.time()
        self._half_open_calls = 0
        
        # Update Prometheus metrics
        try:
            from backend.core.metrics import CIRCUIT_BREAKER_STATE
            state_val = 0
            if new_state == CircuitState.OPEN:
                state_val = 1
            elif new_state == CircuitState.HALF_OPEN:
                state_val = 2
            CIRCUIT_BREAKER_STATE.labels(breaker=self.name).set(state_val)
        except Exception:
            pass


# ==================== Global Circuit Breaker Registry ====================

_breakers: Dict[str, ScraperCircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 300,
) -> ScraperCircuitBreaker:
    """Circuit breaker instance al veya oluştur"""
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = ScraperCircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _breakers[name]


def get_all_breaker_statuses() -> Dict[str, dict]:
    """Tüm circuit breaker durumlarını döndür"""
    with _breakers_lock:
        return {name: breaker.get_status() for name, breaker in _breakers.items()}
