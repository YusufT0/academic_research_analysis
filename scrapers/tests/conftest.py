"""
Test Configuration — pytest fixtures

Tüm testler için ortak fixture'lar.
"""

import sys
from pathlib import Path

# scrapers/ dizinini sys.path'e ekle (backend, database, utils paketleri için)
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client():
    """
    Async HTTP test client.
    
    Database bağlantısı mock'lanmış halde app'i test eder.
    """
    from httpx import AsyncClient, ASGITransport
    
    # Database initialization'ı mock'la
    with patch("backend.main.init_database", new_callable=AsyncMock), \
         patch("backend.main.close_database", new_callable=AsyncMock), \
         patch("backend.main.ScraperManager") as mock_manager_cls:
        
        # ScraperManager mock
        mock_manager = MagicMock()
        mock_manager.get_all_status.return_value = {
            "ieee": {"status": "idle", "progress_percent": 0,
                     "journals_scraped": 0, "issues_scraped": 0,
                     "articles_scraped": 0, "articles_updated": 0,
                     "errors_count": 0, "elapsed_seconds": 0,
                     "current_journal": None},
            "sciencedirect": {"status": "idle", "progress_percent": 0,
                              "journals_scraped": 0, "issues_scraped": 0,
                              "articles_scraped": 0, "articles_updated": 0,
                              "errors_count": 0, "elapsed_seconds": 0,
                              "current_journal": None},
            "any_running": False,
        }
        mock_manager_cls.return_value = mock_manager
        
        from backend.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def mock_redis():
    """Fake Redis instance"""
    try:
        import fakeredis.aioredis
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        yield redis
        await redis.close()
    except ImportError:
        pytest.skip("fakeredis not installed")


@pytest.fixture
def sample_article():
    """Örnek makale verisi"""
    return {
        "id": "507f1f77bcf86cd799439011",
        "title": "Deep Learning for Natural Language Processing",
        "journal_name": "IEEE Access",
        "journal_id": "507f1f77bcf86cd799439012",
        "issue_id": "507f1f77bcf86cd799439013",
        "source_website": "ieeexplore",
        "url": "https://ieeexplore.ieee.org/document/12345",
        "doi": "10.1109/ACCESS.2024.12345",
        "abstract": "This paper presents a comprehensive survey of deep learning methods...",
        "keywords": ["deep learning", "NLP", "transformers"],
        "authors": ["John Doe", "Jane Smith"],
        "publication_year": 2024,
        "article_type": "Research Article",
        "open_access": True,
        "citation_count": 42,
    }
