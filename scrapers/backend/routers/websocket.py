"""
WebSocket Router

Scraper ilerleme, tamamlanma ve hata event'lerini gerçek zamanlı push eder.
Redis Pub/Sub ile beslenir — scraper thread'ler → Redis → WebSocket clients.

Subscription filtering:
- Her bağlantı için abone olunan scraper seti tutulur (varsayılan: tümü).
- Client, bağlanırken ?scrapers=ieee,acm query param ile filtre belirtebilir.
- Bağlandıktan sonra {"type": "subscribe", "scrapers": ["ieee"]} mesajıyla günceller.
- Yalnızca 'log' type event'ler filtrelenir; diğerleri (progress, status_update vb.) herkese gider.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from backend.utils.redis_pubsub import redis_pubsub, SCRAPER_EVENTS_CHANNEL

router = APIRouter(tags=["WebSocket"])

ALL_SCRAPERS: Set[str] = {"ieee", "sciencedirect", "acm"}


def _parse_scrapers_param(scrapers_str: str) -> Set[str]:
    """Query param / subscribe mesajındaki scraper listesini parse eder."""
    if not scrapers_str or scrapers_str.strip().lower() == "all":
        return set(ALL_SCRAPERS)
    parsed = {s.strip().lower() for s in scrapers_str.split(",")} & ALL_SCRAPERS
    return parsed if parsed else set(ALL_SCRAPERS)


class ConnectionManager:
    """
    WebSocket bağlantı yöneticisi.

    Tüm aktif client'lara broadcast yapar; 'log' type event'leri
    her bağlantının scraper subscription'ına göre filtreler.
    Heartbeat mekanizması ile ghost connection'ları temizler.
    Redis Pub/Sub consumer'ı tek seferlik başlatır (idempotent).
    """

    def __init__(self):
        # WebSocket -> {"last_pong": float, "scrapers": Set[str]}
        self._active_connections: Dict[WebSocket, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._prune_task: Optional[asyncio.Task] = None
        self._listen_redis_task: Optional[asyncio.Task] = None
        self._redis_consumer_lock: Optional[asyncio.Lock] = None

        try:
            from backend.core.metrics import WS_CONNECTIONS
            WS_CONNECTIONS.set(0)
        except ImportError:
            pass

    def _get_redis_consumer_lock(self) -> asyncio.Lock:
        if self._redis_consumer_lock is None:
            self._redis_consumer_lock = asyncio.Lock()
        return self._redis_consumer_lock

    @property
    def connection_count(self) -> int:
        return len(self._active_connections)

    async def startup(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        if not self._listen_redis_task or self._listen_redis_task.done():
            self._listen_redis_task = asyncio.create_task(self._start_redis_consumer())

    async def shutdown(self):
        """WebSocket manager'ı kapat — tüm task'leri iptal et, bağlantıları kapat."""
        for task in (self._listen_redis_task, self._prune_task):
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        # Tüm aktif WS bağlantılarını kapat
        async with self._lock:
            for ws in list(self._active_connections.keys()):
                try:
                    await ws.close()
                except Exception:
                    pass
            self._active_connections.clear()

    async def connect(self, websocket: WebSocket, scrapers: Optional[Set[str]] = None):
        """Yeni WebSocket bağlantısı kabul et. scrapers: ilk subscription seti."""
        await websocket.accept()
        async with self._lock:
            self._active_connections[websocket] = {
                "last_pong": time.time(),
                "scrapers": scrapers if scrapers is not None else set(ALL_SCRAPERS),
            }
            if self._loop is None:
                self._loop = asyncio.get_event_loop()

            try:
                from backend.core.metrics import WS_CONNECTIONS
                WS_CONNECTIONS.inc()
            except ImportError:
                pass

        if not self._prune_task or self._prune_task.done():
            self._prune_task = asyncio.create_task(self._prune_ghost_connections())

        if not self._listen_redis_task or self._listen_redis_task.done():
            self._listen_redis_task = asyncio.create_task(self._start_redis_consumer())

    async def _start_redis_consumer(self):
        async with self._get_redis_consumer_lock():
            if redis_pubsub.redis is not None and redis_pubsub._listen_task and not redis_pubsub._listen_task.done():
                pass
            else:
                await redis_pubsub.connect()
                redis_pubsub.add_handler(self.broadcast)
                await redis_pubsub.start_listening(SCRAPER_EVENTS_CHANNEL)

        if redis_pubsub._listen_task:
            try:
                await redis_pubsub._listen_task
            except (asyncio.CancelledError, Exception):
                pass

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self._active_connections:
                del self._active_connections[websocket]
                try:
                    from backend.core.metrics import WS_CONNECTIONS
                    WS_CONNECTIONS.dec()
                except ImportError:
                    pass

    def update_pong(self, websocket: WebSocket):
        if websocket in self._active_connections:
            self._active_connections[websocket]["last_pong"] = time.time()

    def update_subscription(self, websocket: WebSocket, scrapers: Set[str]):
        """Bağlantının scraper subscription'ını günceller (dinamik filtre değişimi)."""
        if websocket in self._active_connections:
            self._active_connections[websocket]["scrapers"] = scrapers

    def broadcast_from_thread(self, event: Dict[str, Any]):
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)

    async def _prune_ghost_connections(self):
        while True:
            await asyncio.sleep(30)
            now = time.time()
            to_remove = []

            async with self._lock:
                for ws, info in self._active_connections.items():
                    if now - info["last_pong"] > 45:
                        to_remove.append(ws)

            for ws in to_remove:
                try:
                    await ws.close()
                except Exception:
                    pass
                finally:
                    await self.disconnect(ws)

    async def _send_to_connection(self, websocket: WebSocket, message: str):
        try:
            await websocket.send_text(message)
        except Exception:
            await self.disconnect(websocket)

    async def broadcast(self, event: Dict[str, Any]):
        """
        Aktif bağlantılara event gönder.
        'log' type event'ler: yalnızca o scraper'a abone olan bağlantılara.
        Diğer event'ler (progress, status_update, completed, error vb.): herkese.
        """
        if not self._active_connections:
            return

        event_type = event.get("type", "")
        event_scraper = event.get("scraper_type", "")
        # Yalnızca 'log' eventleri subscription'a göre filtrelenir
        should_filter = event_type == "log" and event_scraper in ALL_SCRAPERS

        message = json.dumps(event, default=str)

        async with self._lock:
            connections = list(self._active_connections.items())

        tasks = []
        for ws, info in connections:
            if should_filter and event_scraper not in info["scrapers"]:
                continue
            tasks.append(self._send_to_connection(ws, message))

        await asyncio.gather(*tasks, return_exceptions=True)


# Global instance
ws_manager = ConnectionManager()


SCRAPER_LOG_BUFFER_KEY = "scraper_events_buffer"
SCRAPER_LOG_BUFFER_SIZE = 100


def emit_scraper_event(
    event_type: str,
    scraper_type: str,
    data: Optional[Dict[str, Any]] = None,
):
    """
    Scraper event'i broadcast et (thread-safe, sync veya async destekler).
    Redis Pub/Sub üzerinden publish eder → tüm WS client'lara iletilir.
    Aynı zamanda Redis List'e yazar → yeni bağlanan client'lar son 100 logu replay alır.
    """
    event = {
        "type": event_type,
        "scraper_type": scraper_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }

    redis_pubsub.publish_event_sync(SCRAPER_EVENTS_CHANNEL, event)
    _append_to_log_buffer_sync(event)


def _append_to_log_buffer_sync(event: Dict[str, Any]):
    loop = redis_pubsub._event_loop
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_append_to_log_buffer(event), loop)


async def _append_to_log_buffer(event: Dict[str, Any]):
    if not redis_pubsub.redis:
        return
    try:
        message = json.dumps(event, default=str)
        pipe = redis_pubsub.redis.pipeline()
        pipe.rpush(SCRAPER_LOG_BUFFER_KEY, message)
        pipe.ltrim(SCRAPER_LOG_BUFFER_KEY, -SCRAPER_LOG_BUFFER_SIZE, -1)
        await pipe.execute()
    except Exception:
        pass


async def _replay_log_buffer(websocket: WebSocket, scrapers: Optional[Set[str]] = None):
    """
    Yeni bağlanan client'a son N event'i gönder.
    scrapers: None veya ALL_SCRAPERS ise filtre uygulanmaz;
    aksi hâlde yalnızca o scraper'ların 'log' event'leri gönderilir.
    """
    if not redis_pubsub.redis:
        return

    filter_logs = scrapers is not None and scrapers != ALL_SCRAPERS

    try:
        messages = await redis_pubsub.redis.lrange(SCRAPER_LOG_BUFFER_KEY, 0, -1)
        for raw in messages:
            try:
                event = json.loads(raw)
                # 'log' type event'leri filtrele; diğerlerini (progress, status_update) her zaman gönder
                if filter_logs and event.get("type") == "log":
                    if event.get("scraper_type") not in scrapers:
                        continue
                event["_replayed"] = True
                await websocket.send_text(json.dumps(event, default=str))
            except Exception:
                pass
    except Exception:
        pass


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws/scrapers/events")
async def scraper_events_ws(
    websocket: WebSocket,
    scrapers: str = Query("all", description="Virgülle ayrılmış scraper listesi: ieee,sciencedirect,acm veya all"),
):
    """
    Scraper event stream.

    Query params:
    - scrapers: Hangi scraper'ların log event'lerini alacağınızı belirtir.
                Örn: ?scrapers=ieee,acm  |  ?scrapers=all (varsayılan)

    Dinamik güncelleme (bağlandıktan sonra JSON mesaj gönder):
    {"type": "subscribe", "scrapers": ["ieee", "acm"]}  veya
    {"type": "subscribe", "scrapers": "all"}

    Event types:
    - progress: İlerleme güncellemesi
    - status_update: Durum değişimi
    - log: Scraper log mesajı (subscription'a göre filtrelenir)
    - completed: Scraping tamamlandı
    - error: Hata oluştu
    """
    subscribed = _parse_scrapers_param(scrapers)
    await ws_manager.connect(websocket, subscribed)

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Scraper event stream connected via Redis Pub/Sub",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subscribed_scrapers": list(subscribed),
        })

        # Son N event'i replay et (subscription filtresini uygula)
        await _replay_log_buffer(websocket, subscribed)

        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    ws_manager.update_pong(websocket)
                    await websocket.send_json({"type": "pong"})
                else:
                    # JSON mesaj mı? (subscribe isteği olabilir)
                    try:
                        msg = json.loads(data)
                        if msg.get("type") == "subscribe":
                            raw_scrapers = msg.get("scrapers", "all")
                            if isinstance(raw_scrapers, list):
                                new_subscribed = set(raw_scrapers) & ALL_SCRAPERS
                                if not new_subscribed:
                                    new_subscribed = set(ALL_SCRAPERS)
                            else:
                                new_subscribed = _parse_scrapers_param(str(raw_scrapers))
                            ws_manager.update_subscription(websocket, new_subscribed)
                            # Onay mesajı gönder
                            await websocket.send_json({
                                "type": "subscribed",
                                "subscribed_scrapers": list(new_subscribed),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                    except (json.JSONDecodeError, Exception):
                        pass
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(websocket)
