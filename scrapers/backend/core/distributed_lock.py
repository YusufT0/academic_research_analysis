"""
Distributed Scraper Lock

Redis SET NX EX tabanlı dağıtık kilit mekanizması.
Birden fazla backend instance çalışırken aynı scraper'ın iki kez başlatılmasını engeller.

Kullanım:
    acquired = await DistributedScraperLock.acquire("ieee")
    if not acquired:
        raise AlreadyRunningError("IEEE scraper başka bir instance tarafından çalıştırılıyor")
    try:
        ...run scraper...
    finally:
        await DistributedScraperLock.release("ieee")
"""

import uuid
from utils.logger import get_logger

logger = get_logger("distributed_lock")

# 3 saat — en uzun beklenen scrape süresinden fazla
SCRAPER_LOCK_TTL = 10800

# Her process için benzersiz kimlik (LUA script aracılığıyla başkasının kilidini bırakmayı önler)
_INSTANCE_ID = str(uuid.uuid4())[:12]


class DistributedScraperLock:
    """
    Scraper'lar için Redis tabanlı dağıtık kilit.

    SET key value NX EX ttl   — atomik: yalnızca key yoksa ayarlar
    LUA eval                  — atomik: yalnızca sahibi silebilir
    EXPIRE                    — TTL yenileme (uzun çalışan scraper'lar için)
    """

    @classmethod
    def _get_client(cls):
        """Cache service'ten Redis client'ını al."""
        from backend.services.cache_service import get_cache_service
        cache = get_cache_service()
        if not cache.is_connected:
            return None, None
        key_prefix = cache._make_key("lock", "scraper")
        return cache._client, key_prefix

    @classmethod
    async def acquire(cls, scraper_type: str, ttl: int = SCRAPER_LOCK_TTL) -> bool:
        """
        Kilit almayı dene. Başarılıysa True döner.

        Redis erişilemezse True döner (fail-open: Redis down olduğunda scraping'i bloklama).
        """
        client, prefix = cls._get_client()
        if client is None:
            return True  # fail-open

        key = f"{prefix}:{scraper_type}"
        try:
            acquired = await client.set(key, _INSTANCE_ID, nx=True, ex=ttl)
            if acquired:
                logger.info(
                    f"Distributed lock acquired",
                    scraper=scraper_type,
                    instance=_INSTANCE_ID,
                    ttl=ttl,
                )
            else:
                owner = await client.get(key)
                logger.warning(
                    f"Distributed lock BUSY — scraper already running on another instance",
                    scraper=scraper_type,
                    owner=owner,
                )
            return bool(acquired)
        except Exception as e:
            logger.error(f"Lock acquire error [{scraper_type}]: {e}")
            return True  # fail-open

    @classmethod
    async def release(cls, scraper_type: str) -> bool:
        """
        Kilidi bırak (yalnızca bu instance'a aitse).
        Başka instance'ın kilidini bırakmaz.
        """
        client, prefix = cls._get_client()
        if client is None:
            return True

        key = f"{prefix}:{scraper_type}"
        # Atomik kontrol + silme
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            result = await client.eval(lua, 1, key, _INSTANCE_ID)
            if result:
                logger.info(f"Distributed lock released", scraper=scraper_type)
            else:
                logger.debug(f"Lock not released (not owner or already expired)", scraper=scraper_type)
            return bool(result)
        except Exception as e:
            logger.error(f"Lock release error [{scraper_type}]: {e}")
            return False

    @classmethod
    async def refresh(cls, scraper_type: str, ttl: int = SCRAPER_LOCK_TTL) -> bool:
        """TTL'yi yenile (uzun süren scraper'lar için periyodik çağrılır)."""
        client, prefix = cls._get_client()
        if client is None:
            return True

        key = f"{prefix}:{scraper_type}"
        try:
            owner = await client.get(key)
            if owner == _INSTANCE_ID:
                await client.expire(key, ttl)
                logger.debug(f"Lock TTL refreshed", scraper=scraper_type, ttl=ttl)
                return True
            return False
        except Exception as e:
            logger.error(f"Lock refresh error [{scraper_type}]: {e}")
            return False

    @classmethod
    async def is_locked_by_other(cls, scraper_type: str) -> bool:
        """Başka bir instance tarafından kilitlenmiş mi?"""
        client, prefix = cls._get_client()
        if client is None:
            return False

        key = f"{prefix}:{scraper_type}"
        try:
            owner = await client.get(key)
            return owner is not None and owner != _INSTANCE_ID
        except Exception:
            return False
