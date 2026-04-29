"""
Request Middleware

3 middleware zinciri:
1. RequestIdMiddleware: UUID tabanlı X-Request-ID header
2. TimingMiddleware: X-Process-Time header (ms)
3. RequestLoggingMiddleware: Structured JSON log per request
"""

import time
import uuid
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("middleware")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Her request'e unique X-Request-ID ekler.
    
    Client gönderirse onu kullanır, yoksa UUID üretir.
    Request state'e de ekler (error handler'lar için).
    """
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Client tarafından gönderilen request_id varsa kullan
        request_id = request.headers.get("x-request-id")
        if not request_id:
            request_id = str(uuid.uuid4())[:12]
        
        # Request state'e ekle (error handler ve diğer middleware'ler için)
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        # Response header'a ekle
        response.headers["X-Request-ID"] = request_id
        
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Her endpoint'in response süresini ölçer ve X-Process-Time header'ında döner.
    """
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Process-Time"] = f"{process_time_ms}ms"
        
        # Request state'e süreyi ekle (logging middleware için)
        request.state.process_time_ms = process_time_ms
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Her request/response çiftini structured log olarak yazar.
    
    Health check ve metrics gibi yüksek frekanslı endpoint'leri filtreler.
    """
    
    # Loglanmayacak path'ler (noise azaltma)
    SKIP_PATHS = {
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/favicon.ico",
    }
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip noisy endpoints
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)
        
        response = await call_next(request)
        
        # Structured log
        request_id = getattr(request.state, "request_id", "-")
        process_time = getattr(request.state, "process_time_ms", 0)
        
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time_ms": process_time,
                "client_ip": request.client.host if request.client else "-",
            },
        )
        
        return response
