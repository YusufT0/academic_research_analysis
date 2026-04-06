"""
Custom Exception Hierarchy

Tüm uygulama hatalarını standart JSON formatına dönüştürmek için
hiyerarşik exception sınıfları.
"""

from typing import Optional, Dict, Any


class AppException(Exception):
    """Base application exception"""
    
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    
    def __init__(
        self,
        message: str = "An unexpected error occurred",
        details: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        super().__init__(self.message)


# ==================== 4xx Errors ====================

class NotFoundError(AppException):
    """Kaynak bulunamadı (404)"""
    status_code = 404
    error_code = "NOT_FOUND"
    
    def __init__(self, resource: str = "Resource", resource_id: str = ""):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} '{resource_id}' not found"
        super().__init__(message=message, details={"resource": resource, "id": resource_id})


class ValidationError(AppException):
    """Doğrulama hatası (422)"""
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ConflictError(AppException):
    """Kaynak çakışması (409)"""
    status_code = 409
    error_code = "CONFLICT"


# ==================== 5xx Errors ====================

class ScraperError(AppException):
    """Scraper hatası (500)"""
    status_code = 500
    error_code = "SCRAPER_ERROR"


class ScraperTimeoutError(ScraperError):
    """Scraper zaman aşımı"""
    error_code = "SCRAPER_TIMEOUT"
    
    def __init__(self, scraper_type: str, timeout_seconds: int):
        super().__init__(
            message=f"{scraper_type} scraper {timeout_seconds}s timeout exceeded",
            details={"scraper_type": scraper_type, "timeout_seconds": timeout_seconds},
        )


class ScraperConnectionError(ScraperError):
    """Scraper bağlantı hatası"""
    error_code = "SCRAPER_CONNECTION_ERROR"
    
    def __init__(self, scraper_type: str, target_url: str = ""):
        super().__init__(
            message=f"{scraper_type} scraper connection failed",
            details={"scraper_type": scraper_type, "target_url": target_url},
        )


class DatabaseError(AppException):
    """Database erişim hatası (503)"""
    status_code = 503
    error_code = "DATABASE_ERROR"
    
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict] = None):
        super().__init__(message=message, details=details or {})


class ExternalServiceError(AppException):
    """Harici servis hatası (502)"""
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"
    
    def __init__(self, service_name: str, message: str = ""):
        msg = f"{service_name} service error"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(message=msg, details={"service": service_name})
