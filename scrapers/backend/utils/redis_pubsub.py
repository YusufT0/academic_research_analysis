import asyncio
import json
from typing import Optional, Callable, Dict, Any, Awaitable
from redis.asyncio import Redis

from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger("redis_pubsub")

# Global Redis kanalı adı
SCRAPER_EVENTS_CHANNEL = "scraper_events_channel"


class RedisPubSubManager:
    """
    Redis Pub/Sub yönlendiricisi.
    Scraper thread'ler logları buraya Publish eder.
    FastAPI / WebSocket consumer burayı (Subscribe) dinleyip, bağlı client'lara gönderir.
    """

    def __init__(self):
        self.redis: Optional[Redis] = None
        self.pubsub = None
        self._listen_task: Optional[asyncio.Task] = None
        self._handlers: list[Callable[[Dict[str, Any]], Awaitable[None]]] = []
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        # Prevents concurrent coroutines from calling connect() simultaneously
        self._connect_lock: Optional[asyncio.Lock] = None

    def _get_connect_lock(self) -> asyncio.Lock:
        """Lazy-init lock so it's always created on the running event loop."""
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        return self._connect_lock

    async def connect(self):
        """Redis'e bağlanır ve PubSub client'ını oluşturur. Idempotent."""
        if not settings.redis_enabled:
            logger.warning("Redis devre dışı. Pub/Sub çalışmayacak.")
            return

        # Fast path: already connected
        if self.redis is not None:
            return

        async with self._get_connect_lock():
            # Re-check inside lock (double-checked locking)
            if self.redis is not None:
                return

            # FastAPI event loop'unu kaydet — sync thread'lerden erişim için
            self._event_loop = asyncio.get_event_loop()

            try:
                self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
                # Test connection
                await self.redis.ping()
                self.pubsub = self.redis.pubsub()
                logger.success("Redis Pub/Sub bağlantısı başarılı.")
            except Exception as e:
                logger.error(f"Redis Pub/Sub bağlantı hatası: {e}")
                self.redis = None

    async def disconnect(self):
        """Bağlantıyı temiz kapatır."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass

        if self.pubsub:
            try:
                await self.pubsub.close()
            except Exception:
                pass

        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass
            self.redis = None
            logger.info("Redis Pub/Sub bağlantısı kapatıldı.")

    async def publish_event(self, channel: str, event_data: dict):
        """Bir kanala JSON event publish eder."""
        if not self.redis:
            return

        try:
            message = json.dumps(event_data, default=str)
            await self.redis.publish(channel, message)
        except Exception as e:
            logger.error(f"Redis Publish hatası: {e}")

    def publish_event_sync(self, channel: str, event_data: dict):
        """
        Thread içinden (sync) publish yapmak için. (ScraperManager için gerekli)
        Kayıtlı FastAPI event loop'una task schedule eder — her seferinde
        yeni TCP bağlantısı açmaktan kaçınır.
        """
        if not self.redis:
            return

        # Önce kayıtlı loop'u dene (en hızlı yol — mevcut async Redis bağlantısını kullanır)
        loop = self._event_loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.publish_event(channel, event_data), loop)
            return

        # Fallback: çağrılan thread'de zaten bir loop varsa (nadiren)
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self.publish_event(channel, event_data), loop)
        except RuntimeError:
            # Hiç loop bulunamadı — geçici sync bağlantı (son çare)
            try:
                import redis as _redis
                sync_redis = _redis.Redis.from_url(settings.redis_url)
                message = json.dumps(event_data, default=str)
                sync_redis.publish(channel, message)
                sync_redis.close()
            except Exception as e:
                logger.error(f"Sync Redis Publish hatası: {e}")

    def add_handler(self, handler: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Mesaja abone olacak callback handler'ları ekler. Tekrar eklemeyi önler."""
        if handler not in self._handlers:
            self._handlers.append(handler)

    async def start_listening(self, channel: str):
        """
        Belirtilen kanalı dinlemeye başlar ve gelen mesajları handler'lara yollar.
        Idempotent: zaten dinleniyorsa ikinci kez başlatmaz.
        """
        if not self.redis or not self.pubsub:
            logger.error("Redis bağlantısı yok, dinleme başlatılamadı.")
            return

        # Already listening — don't create a second loop
        if self._listen_task and not self._listen_task.done():
            return

        await self.pubsub.subscribe(channel)
        logger.info(f"Redis Pub/Sub dinleniyor: {channel}")

        async def listen_loop():
            try:
                async for message in self.pubsub.listen():
                    if message["type"] == "message":
                        try:
                            event_data = json.loads(message["data"])
                            # Tüm observer'ları (callback'leri) paralel çalıştır
                            tasks = [handler(event_data) for handler in self._handlers]
                            if tasks:
                                await asyncio.gather(*tasks, return_exceptions=True)
                        except json.JSONDecodeError:
                            logger.error("Redis mesajı JSON decode edilemedi.")
                        except Exception as e:
                            logger.error(f"Redis mesaj işleme hatası: {e}")
            except asyncio.CancelledError:
                logger.info(f"Redis dinleme iptal edildi: {channel}")
            except Exception as e:
                logger.error(f"Redis listen_loop koptu: {e}")

        # Task'ı başlat
        self._listen_task = asyncio.create_task(listen_loop())


# Global instance
redis_pubsub = RedisPubSubManager()
