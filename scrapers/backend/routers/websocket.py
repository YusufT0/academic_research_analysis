"""
WebSocket Router

Scraper ilerleme, tamamlanma ve hata event'lerini gerçek zamanlı push eder.

Faz 1: In-memory callback ile beslenir (ScraperManager'dan direkt). -> IPTAL (Enterprise Mode devrede)
Faz 6: Redis Pub/Sub ile beslenir.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Set, Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.utils.redis_pubsub import redis_pubsub, SCRAPER_EVENTS_CHANNEL

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """
    WebSocket bağlantı yöneticisi.
    
    Tüm aktif client'lara broadcast yapar.
    Heartbeat mekanizması ile ghost connection'ları temizler.
    """
    
    def __init__(self):
        # WebSocket object -> Last Pong Timestamp
        self._active_connections: Dict[WebSocket, float] = {}
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._prune_task: Optional[asyncio.Task] = None
        self._listen_redis_task: Optional[asyncio.Task] = None
        
        # Reset the global Prometheus gauge on startup to clear any phantom connections from hot-reloads
        try:
            from backend.core.metrics import WS_CONNECTIONS
            WS_CONNECTIONS.set(0)
        except ImportError:
            pass
    
    @property
    def connection_count(self) -> int:
        return len(self._active_connections)
    
    async def connect(self, websocket: WebSocket):
        """Yeni WebSocket bağlantısı kabul et"""
        await websocket.accept()
        async with self._lock:
            self._active_connections[websocket] = time.time()
            if self._loop is None:
                self._loop = asyncio.get_event_loop()
            
            try:
                from backend.core.metrics import WS_CONNECTIONS
                WS_CONNECTIONS.inc()
            except ImportError:
                pass
                
        # Start pruning task if not already started
        if not self._prune_task or self._prune_task.done():
            self._prune_task = asyncio.create_task(self._prune_ghost_connections())
            
        # Start listening to Redis if not already started
        if not self._listen_redis_task or self._listen_redis_task.done():
            self._listen_redis_task = asyncio.create_task(self._start_redis_consumer())
            
    async def _start_redis_consumer(self):
        """Redis'e bağlanır ve haber bekler."""
        await redis_pubsub.connect()
        # Bind the broadcast method to receive events (only once)
        if self.broadcast not in redis_pubsub._handlers:
            redis_pubsub.add_handler(self.broadcast)
        # Start listening in background
        await redis_pubsub.start_listening(SCRAPER_EVENTS_CHANNEL)
    
    async def disconnect(self, websocket: WebSocket):
        """WebSocket bağlantısını kaldır"""
        async with self._lock:
            if websocket in self._active_connections:
                del self._active_connections[websocket]
                try:
                    from backend.core.metrics import WS_CONNECTIONS
                    WS_CONNECTIONS.dec()
                except ImportError:
                    pass
                    
    def update_pong(self, websocket: WebSocket):
        """Gelen pong ile son görülme zamanını günceller"""
        if websocket in self._active_connections:
            self._active_connections[websocket] = time.time()
            
    async def _prune_ghost_connections(self):
        """
        Background task: Her 30 saniyede bir kontrol edip
        Ping atmamış veya ölü görünüyorsa ghost connection'ları düşürür.
        """
        while True:
            await asyncio.sleep(30)
            now = time.time()
            to_remove = []
            
            async with self._lock:
                for ws, last_pong in self._active_connections.items():
                    # Eğer 45 saniyeden uzun süredir ping gelmediyse kopar
                    if now - last_pong > 45:
                        to_remove.append(ws)
            
            for ws in to_remove:
                try:
                    await ws.close()
                except Exception:
                    pass
                finally:
                    await self.disconnect(ws)
    
    async def _send_to_connection(self, websocket: WebSocket, message: str):
        """Tek bağlantıya mesaj gönder, hata olursa bağlantıyı kaldır"""
        try:
            await websocket.send_text(message)
        except Exception:
            await self.disconnect(websocket)
    
    async def broadcast(self, event: Dict[str, Any]):
        """Tüm aktif bağlantılara event broadcast et (Redis handler buradan çağrılacak)"""
        if not self._active_connections:
            return
        
        message = json.dumps(event, default=str)
        
        async with self._lock:
            connections = list(self._active_connections.keys())
        
        tasks = [self._send_to_connection(ws, message) for ws in connections]
        await asyncio.gather(*tasks, return_exceptions=True)


# Global instance
ws_manager = ConnectionManager()


def emit_scraper_event(
    event_type: str,
    scraper_type: str,
    data: Optional[Dict[str, Any]] = None,
):
    """
    Scraper event'i broadcast et (thread-safe, sync veya async destekler).
    
    ScraperManager tarafından çağrılır ve yerel WebSockets yerine
    tüm sunuculara dağılması için Redis Pub/Sub üzerinden publish eder.
    """
    event = {
        "type": event_type,
        "scraper_type": scraper_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    
    # Send directly to Redis stream channel (fire & forget from sync mode)
    redis_pubsub.publish_event_sync(SCRAPER_EVENTS_CHANNEL, event)


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws/scrapers/events")
async def scraper_events_ws(websocket: WebSocket):
    """
    Scraper event stream.
    
    Event types:
    - progress: İlerleme güncellemesi (journal_index, article_count, percent)
    - completed: Scraping tamamlandı
    - error: Hata oluştu
    - status_change: Durum değişimi (idle→running, running→paused, etc.)
    """
    await ws_manager.connect(websocket)
    
    try:
        # Bağlantı onay mesajı
        await websocket.send_json({
            "type": "connected",
            "message": "Scraper event stream connected via Redis Pub/Sub",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Client bağlı kaldığı sürece bekle
        while True:
            try:
                # Olası bir 'receive_text' takılmasını önlemek için küçük timeoutlar kullanılabilir
                # ama FastAPI WebSockets natively exception atar.
                data = await websocket.receive_text()
                
                # Ping'e pong ile cevap ver ve son online time'ı güncelle
                if data == "ping":
                    ws_manager.update_pong(websocket)
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(websocket)
