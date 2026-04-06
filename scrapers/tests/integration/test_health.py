"""
Health Endpoint Integration Tests
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_health_live(async_client):
    """Liveness probe should always return 200"""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    """Root endpoint should return API info"""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "health" in data


@pytest.mark.asyncio
async def test_api_info_endpoint(async_client):
    """API v1 info endpoint should list available routes"""
    response = await async_client.get("/api/v1")
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data
    assert "journals" in data["endpoints"]
    assert "articles" in data["endpoints"]
