"""
Global Error Handlers

Tüm exception'ları standart JSON response formatına dönüştürür.
RequestIdMiddleware ile birlikte çalışarak her hata response'una request_id ekler.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exceptions import AppException


def _get_request_id(request: Request) -> Optional[str]:
    """Request state veya header'dan request_id al"""
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        request_id = request.headers.get("x-request-id")
    return request_id


def _build_error_response(
    status_code: int,
    error_code: str,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> JSONResponse:
    """Standart JSON error response oluştur"""
    body = {
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    if request_id:
        body["error"]["request_id"] = request_id
    if details:
        body["error"]["details"] = details
    
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    """Tüm global error handler'ları FastAPI app'e kaydet"""
    
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """Custom AppException handler"""
        return _build_error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            request_id=_get_request_id(request),
            details=exc.details if exc.details else None,
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Pydantic validation error handler"""
        errors = []
        for error in exc.errors():
            errors.append({
                "field": " → ".join(str(loc) for loc in error.get("loc", [])),
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            })
        
        return _build_error_response(
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            request_id=_get_request_id(request),
            details={"errors": errors},
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Starlette HTTP exception handler (404, 405, etc.)"""
        error_code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            429: "TOO_MANY_REQUESTS",
            500: "INTERNAL_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
        }
        
        return _build_error_response(
            status_code=exc.status_code,
            error_code=error_code_map.get(exc.status_code, "HTTP_ERROR"),
            message=str(exc.detail) if exc.detail else "An error occurred",
            request_id=_get_request_id(request),
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Yakalanmamış tüm exception'lar için fallback handler"""
        # Production'da detay vermemek daha güvenli
        return _build_error_response(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            request_id=_get_request_id(request),
        )
