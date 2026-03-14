"""
WebSocket Router

Scraper ilerleme, tamamlanma ve hata event'lerini gerçek zamanlı push eder.
Redis Pub/Sub ile beslenir — scraper thread'ler → Redis → WebSocket clients.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.utils.redis_pubsub import redis_pubsub, SCRAPER_EVENTS_CHANNEL

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """
    WebSocket bağlantı yöneticisi.

    Tüm aktif client'lara broadcast yapar.
    Heartbeat mekanizması ile ghost connection'ları temizler.
    Redis Pub/Sub consumer'ı tek seferlik başlatır (idempotent).
    """

    def __init__(self):
        # WebSocket object -> Last Pong Timestamp
        self._active_connections: Dict[WebSocket, float] = {}
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._prune_task: Optional[asyncio.Task] = None
        self._listen_redis_task: Optional[asyncio.Task] = None
        # Prevents concurrent WS connects from starting the Redis consumer twice
        self._redis_consumer_lock: Optional[asyncio.Lock] = None

        # Reset the global Prometheus gauge on startup to clear phantom connections from hot-reloads
        try:
            from backend.core.metrics import WS_CONNECTIONS
            WS_CONNECTIONS.set(0)
        except ImportError:
            pass

    def _get_redis_consumer_lock(self) -> asyncio.Lock:
        """Lazy-init lock so it's always created on the running event loop."""
        if self._redis_consumer_lock is None:
            self._redis_consumer_lock = asyncio.Lock()
        return self._redis_consumer_lock

    @property
    def connection_count(self) -> int:
        """Approximate connection count (no lock — for monitoring only)."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket):
        """Yeni WebSocket bağlantısı kabul et."""
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

        # Start pruning task if not already running
        if not self._prune_task or self._prune_task.done():
            self._prune_task = asyncio.create_task(self._prune_ghost_connections())

        # Start Redis consumer if not already running
        # The task stays alive as long as the Redis listen loop runs,
        # so this only fires once per server lifetime.
        if not self._listen_redis_task or self._listen_redis_task.done():
            self._listen_redis_task = asyncio.create_task(self._start_redis_consumer())

    async def _start_redis_consumer(self):
        """
        Redis'e bir kez bağlanır ve listen loop'u başlatır.
        Lock + double-checked guard ile idempotent.
        Coroutine, listen loop bitene kadar canlı kalır → task.done() False kalır
        → sonraki WS bağlantıları bunu yeniden başlatmaz.
        """
        async with self._get_redis_consumer_lock():
            # Double-checked: another coroutine may have connected while we waited
            if redis_pubsub.redis is not None and redis_pubsub._listen_task and not redis_pubsub._listen_task.done():
                # Already fully set up — skip to the await below
                pass
            else:
                await redis_pubsub.connect()
                # add_handler is idempotent (dedup inside)
                redis_pubsub.add_handler(self.broadcast)
                await redis_pubsub.start_listening(SCRAPER_EVENTS_CHANNEL)

        # Keep this coroutine alive so _listen_redis_task.done() stays False.
        # When the Redis listen loop exits (e.g. Redis restart), this returns
        # and the next WS connection will restart the consumer.
        if redis_pubsub._listen_task:
            try:
                await redis_pubsub._listen_task
            except (asyncio.CancelledError, Exception):
                pass

    async def disconnect(self, websocket: WebSocket):
        """WebSocket bağlantısını kaldır."""
        async with self._lock:
            if websocket in self._active_connections:
                del self._active_connections[websocket]
                try:
                    from backend.core.metrics import WS_CONNECTIONS
                    WS_CONNECTIONS.dec()
                except ImportError:
                    pass

    def update_pong(self, websocket: WebSocket):
        """Gelen pong ile son görülme zamanını günceller."""
        # Safe in asyncio single-thread context — no await between check & update
        if websocket in self._active_connections:
            self._active_connections[websocket] = time.time()

    def broadcast_from_thread(self, event: Dict[str, Any]):
        """
        Thread-safe sync broadcast (sync thread'lerden çağrılabilir).
        Kayıtlı asyncio event loop'una task schedule eder.
        """
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)

    async def _prune_ghost_connections(self):
        """
        Background task: Her 30 saniyede bir kontrol edip
        45 saniyedir ping atmayan ghost connection'ları kapatır.
        """
        while True:
            await asyncio.sleep(30)
            now = time.time()
            to_remove = []

            async with self._lock:
                for ws, last_pong in self._active_connections.items():
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
        """Tek bağlantıya mesaj gönder, hata olursa bağlantıyı kaldır."""
        try:
            await websocket.send_text(message)
        except Exception:
            await self.disconnect(websocket)

    async def broadcast(self, event: Dict[str, Any]):
        """Tüm aktif bağlantılara event broadcast et (Redis handler buradan çağrılır)."""
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
    Redis Pub/Sub üzerinden publish eder → tüm WS client'lara iletilir.
    """
    event = {
        "type": event_type,
        "scraper_type": scraper_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }

    redis_pubsub.publish_event_sync(SCRAPER_EVENTS_CHANNEL, event)


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws/scrapers/events")
async def scraper_events_ws(websocket: WebSocket):
    """
    Scraper event stream.

    Event types:
    - progress: İlerleme güncellemesi
    - status_update: Durum değişimi
    - log: Scraper log mesajı
    - completed: Scraping tamamlandı
    - error: Hata oluştu
    """
    await ws_manager.connect(websocket)

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Scraper event stream connected via Redis Pub/Sub",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    ws_manager.update_pong(websocket)
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(websocket)
