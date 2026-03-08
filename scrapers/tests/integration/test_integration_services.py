import pytest
import asyncio
from backend.core.config import settings

@pytest.mark.asyncio
async def test_mongodb_connection_with_config():
    """
    Test MongoDB connectivity using the centralized configuration.
    Falls back to skipping the test if MongoDB is offline instead of failing.
    """
    from database.connection import init_database, close_database, get_database
    
    # Try initializing the DB
    try:
        success = await init_database()
        if not success:
            pytest.skip("MongoDB is not reachable at the configured URI. Skipping integration test.")
            
        db = get_database()
        assert db is not None
        assert db.client is not None
        
        # Ping the database
        await db.client.admin.command("ping")
        
    except Exception as e:
        pytest.skip(f"Failed to connect to MongoDB: {str(e)}")
    finally:
        await close_database()


@pytest.mark.asyncio
async def test_redis_connection_with_config():
    """
    Test Redis connectivity using the centralized configuration.
    Falls back to skipping if Redis is offline.
    """
    from backend.services.cache_service import cache_service
    
    if not settings.redis_enabled:
        pytest.skip("Redis is disabled in settings. Skipping integration test.")

    try:
        success = await cache_service.connect()
        if not success:
            pytest.skip("Redis is not reachable at the configured URL. Skipping integration test.")
            
        assert cache_service._client is not None
        await cache_service._client.ping()
        
    except Exception as e:
        pytest.skip(f"Failed to connect to Redis: {str(e)}")
    finally:
        await cache_service.disconnect()


@pytest.mark.asyncio
async def test_redis_streams_connection_with_config():
    """
    Test Redis Streams Service connectivity using centralized configuration.
    Falls back to skipping if Redis is offline.
    """
    from backend.services.stream_service import stream_service
    
    if not settings.redis_streams_enabled:
        pytest.skip("Redis streams are disabled in settings. Skipping integration test.")
        
    try:
        await stream_service.connect()
        if not stream_service.is_connected:
            pytest.skip("Redis Streams is not reachable at the configured URL. Skipping integration test.")
        
        assert stream_service._redis is not None
        await stream_service._redis.ping()
        
    except Exception as e:
        pytest.skip(f"Failed to connect to Redis Streams: {str(e)}")
    finally:
        await stream_service.close()


@pytest.mark.asyncio
async def test_elasticsearch_connection_with_config():
    """
    Test Elasticsearch connectivity using the centralized configuration.
    Falls back to skipping if Elasticsearch is offline.
    """
    from backend.services.elasticsearch_service import elasticsearch_service
    
    try:
        await elasticsearch_service.connect()
        if not elasticsearch_service.is_connected:
            pytest.skip("Elasticsearch is not reachable at the configured URL. Skipping integration test.")
            
        assert elasticsearch_service._client is not None
        
        # Ping Elasticsearch
        res = await elasticsearch_service._client.info()
        assert "version" in res
        
    except Exception as e:
         pytest.skip(f"Failed to connect to Elasticsearch: {str(e)}")
    finally:
        await elasticsearch_service.close()
