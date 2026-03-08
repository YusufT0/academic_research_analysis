"""
Redis Streams Event Pipeline

Scraper ve veri işleme pipeline'ı için event-driven mimari.
Redis Streams consumer groups ile at-least-once delivery.

Faz 6: Micro-batching + DLQ + WS bridge.

Streams:
    article:scraped  — Yeni makale scrape edildi
    article:indexed  — ES indexleme tamamlandı
    article:dlq      — Başarısız işlemler
    scraper:events   — Start/stop/error events
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime, timezone

import redis.asyncio as aioredis

from utils.logger import get_logger

logger = get_logger("stream_service")

# Micro-batch ayarları
BATCH_SIZE = 50
BATCH_TIMEOUT_SEC = 2.0


class RedisStreamService:
    """
    Redis Streams event pipeline service.
    
    Producer: XADD ile stream'e event publish
    Consumer: XREADGROUP ile consumer group'tan consume
    DLQ: Başarısız mesajları article:dlq'ya taşı
    """
    
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._consumer_group = "academic-backend"
        self._consumer_name = "worker-1"
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._handlers: Dict[str, List[Callable]] = {}
    
    @property
    def is_connected(self) -> bool:
        return self._redis is not None
    
    async def connect(self, redis_url: Optional[str] = None):
        """Redis'e bağlan ve consumer group'ları oluştur"""
        try:
            from backend.core.config import settings
            url = redis_url or settings.redis_url
            self._redis = aioredis.from_url(url, decode_responses=True)
            await self._redis.ping()
            
            # Stream'ler ve consumer group'ları oluştur
            streams = ["article:scraped", "article:indexed", "article:dlq", "scraper:events"]
            for stream in streams:
                try:
                    await self._redis.xgroup_create(
                        stream, self._consumer_group, id="0", mkstream=True
                    )
                    logger.info("Consumer group created", stream=stream, group=self._consumer_group)
                except Exception:
                    # Grup zaten varsa hata verir, sorun değil
                    pass
            
            logger.info("Redis Streams connected", consumer_group=self._consumer_group)
        except Exception as e:
            logger.error("Redis Streams connection failed", error=str(e))
            self._redis = None
    
    async def close(self):
        """Tüm consumer'ları durdur ve bağlantıyı kapat"""
        self._running = False
        
        # Consumer task'lerini iptal et
        for task in self._tasks:
            task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Redis Streams closed")
    
    async def publish(self, stream: str, data: Dict[str, Any]) -> Optional[str]:
        """Event publish (XADD)"""
        if not self._redis:
            return None
        
        try:
            # Redis Streams flat key-value gerektiriyor
            message = {
                "data": json.dumps(data, default=str),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            msg_id = await self._redis.xadd(stream, message, maxlen=10000)
            
            try:
                from backend.core.metrics import STREAM_MESSAGES_PUBLISHED
                STREAM_MESSAGES_PUBLISHED.labels(stream=stream).inc()
            except ImportError:
                pass
                
            return msg_id
        except Exception as e:
            logger.error("Stream publish failed", stream=stream, error=str(e))
            return None
    
    def register_handler(self, stream: str, handler: Callable[[Dict], Awaitable[None]]):
        """Consumer handler kaydet"""
        if stream not in self._handlers:
            self._handlers[stream] = []
        self._handlers[stream].append(handler)
    
    async def start_consumers(self):
        """Tüm kayıtlı handler'lar için consumer loop başlat"""
        if not self._redis:
            logger.warning("Cannot start consumers: not connected")
            return
        
        self._running = True
        
        for stream, handlers in self._handlers.items():
            task = asyncio.create_task(
                self._consumer_loop(stream, handlers),
                name=f"consumer-{stream}",
            )
            self._tasks.append(task)
            logger.info("Consumer started", stream=stream, handlers=len(handlers))
    
    async def _consumer_loop(self, stream: str, handlers: List[Callable]):
        """
        Tek bir stream için consumer loop.
        
        Micro-batching: BATCH_SIZE kadar mesaj biriktir veya BATCH_TIMEOUT_SEC bekle.
        """
        batch: List[Dict] = []
        last_flush = time.time()
        
        while self._running:
            try:
                # Yeni mesajları oku (timeout: 1 saniye)
                messages = await self._redis.xreadgroup(
                    self._consumer_group,
                    self._consumer_name,
                    {stream: ">"},
                    count=BATCH_SIZE,
                    block=1000,  # 1 saniye block
                )
                
                if messages:
                    for _, msg_list in messages:
                        for msg_id, msg_data in msg_list:
                            try:
                                data = json.loads(msg_data.get("data", "{}"))
                                batch.append({
                                    "id": msg_id,
                                    "data": data,
                                    "stream": stream,
                                })
                            except json.JSONDecodeError:
                                await self._move_to_dlq(stream, msg_id, msg_data, "invalid_json")
                
                # Flush batch: boyut veya zaman aşımı
                now = time.time()
                should_flush = (
                    len(batch) >= BATCH_SIZE or
                    (batch and (now - last_flush) >= BATCH_TIMEOUT_SEC)
                )
                
                if should_flush and batch:
                    await self._process_batch(stream, handlers, batch)
                    batch = []
                    last_flush = now
                
            except asyncio.CancelledError:
                # Flush remaining batch
                if batch:
                    await self._process_batch(stream, handlers, batch)
                break
            except Exception as e:
                logger.error("Consumer loop error", stream=stream, error=str(e))
                await asyncio.sleep(1)
    
    async def _process_batch(
        self,
        stream: str,
        handlers: List[Callable],
        batch: List[Dict],
    ):
        """Batch'i tüm handler'lara gönder ve acknowledge et"""
        for handler in handlers:
            try:
                await handler(batch)
            except Exception as e:
                logger.error(
                    "Handler batch processing failed",
                    stream=stream,
                    handler=handler.__name__,
                    batch_size=len(batch),
                    error=str(e),
                )
                # Başarısız mesajları DLQ'ya taşı
                for msg in batch:
                    await self._move_to_dlq(
                        stream, msg["id"], msg["data"],
                        reason=f"handler_error: {str(e)[:200]}",
                    )
                return
        
        # Tüm handler'lar başarılı → ACK
        for msg in batch:
            try:
                await self._redis.xack(stream, self._consumer_group, msg["id"])
            except Exception:
                pass
                
        try:
            from backend.core.metrics import STREAM_MESSAGES_CONSUMED
            STREAM_MESSAGES_CONSUMED.labels(stream=stream, consumer_group=self._consumer_group).inc(len(batch))
        except ImportError:
            pass
        
        logger.info(
            "Batch processed",
            stream=stream,
            batch_size=len(batch),
        )
    
    async def _move_to_dlq(
        self,
        source_stream: str,
        msg_id: str,
        data: Any,
        reason: str = "unknown",
    ):
        """Başarısız mesajı DLQ'ya taşı"""
        if not self._redis:
            return
        
        try:
            dlq_entry = {
                "source_stream": source_stream,
                "original_id": msg_id,
                "data": json.dumps(data, default=str) if not isinstance(data, str) else data,
                "reason": reason,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._redis.xadd("article:dlq", dlq_entry, maxlen=5000)
            
            # Source stream'den ACK et (tekrar consume edilmemesi için)
            await self._redis.xack(source_stream, self._consumer_group, msg_id)
            
            try:
                from backend.core.metrics import STREAM_DLQ_SIZE
                dlq_len = await self._redis.xlen("article:dlq")
                STREAM_DLQ_SIZE.set(dlq_len)
            except ImportError:
                pass
        except Exception as e:
            logger.error("DLQ move failed", error=str(e))
    
    async def get_stream_info(self) -> Dict[str, Any]:
        """Tüm stream'lerin bilgisi"""
        if not self._redis:
            return {}
        
        info = {}
        streams = ["article:scraped", "article:indexed", "article:dlq", "scraper:events"]
        
        for stream in streams:
            try:
                length = await self._redis.xlen(stream)
                info[stream] = {"length": length}
            except Exception:
                info[stream] = {"length": 0, "error": "not_found"}
        
        return info


# Global instance
stream_service = RedisStreamService()
