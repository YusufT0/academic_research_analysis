"""
Circuit Breaker Unit Tests
"""

import pytest
from backend.core.circuit_breaker import (
    ScraperCircuitBreaker,
    CircuitState,
    CircuitOpenError,
)


class TestCircuitBreaker:
    """Circuit breaker state transitions"""
    
    def test_initial_state_is_closed(self):
        cb = ScraperCircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute()
    
    def test_stays_closed_under_threshold(self):
        cb = ScraperCircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute()
    
    def test_opens_at_threshold(self):
        cb = ScraperCircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.can_execute()
    
    def test_success_resets_failure_count(self):
        cb = ScraperCircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED
    
    def test_manual_reset(self):
        cb = ScraperCircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.can_execute()
    
    def test_get_status_returns_dict(self):
        cb = ScraperCircuitBreaker("test_status", failure_threshold=5)
        status = cb.get_status()
        
        assert status["name"] == "test_status"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 5
    
    def test_time_until_recovery_when_closed(self):
        cb = ScraperCircuitBreaker("test", failure_threshold=3)
        assert cb.time_until_recovery == 0
