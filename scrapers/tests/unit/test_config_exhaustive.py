import os
import pytest
from pydantic import ValidationError

from backend.core.config import Settings

def test_settings_default_values(monkeypatch):
    """Test that default values are loaded correctly when no env variables are provided."""
    # Ensure no environment variables are loaded
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("SCRAPER_HEADLESS", raising=False)
    
    # We must clear the environment for deterministic testing
    for key in list(os.environ.keys()):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)
    
    # Check default string and alias
    assert settings.app_name == "Academic Research Scraper API"
    assert settings.app_version == "1.0.0"
    
    # Check default boolean
    assert settings.debug is False
    assert settings.scraper_headless is True
    assert settings.run_tests_on_startup is False
    
    # Check default int/float
    assert settings.ieee_min_wait == 4
    assert settings.ieee_max_wait == 10
    assert settings.ieee_page_load_timeout == 90
    assert settings.sd_timeout == 90
    assert settings.sd_implicit_wait == 90
    assert settings.pdf_download_timeout == 60
    assert settings.pdf_download_chunk_size == 8192
    assert settings.nlp_umap_n_neighbors == 15
    
    # Check properties
    assert settings.ieee_enabled is True
    assert settings.sciencedirect_enabled is True

def test_settings_override_via_env(monkeypatch):
    """Test that environment variables successfully override default settings."""
    monkeypatch.setenv("APP_NAME", "Custom Scraper")
    monkeypatch.setenv("APP_VERSION", "2.0.0")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SCRAPER_HEADLESS", "false")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27018")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/0")
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9201")
    monkeypatch.setenv("ENABLED_SCRAPERS", "ieee")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Custom Scraper"
    assert settings.app_version == "2.0.0"
    assert settings.debug is True
    assert settings.scraper_headless is False
    assert settings.mongodb_uri == "mongodb://localhost:27018"
    assert settings.redis_url == "redis://localhost:6380/0"
    assert settings.elasticsearch_url == "http://localhost:9201"
    
    # Verify properties re-evaluated based on overridden setings
    assert settings.ieee_enabled is True
    assert settings.sciencedirect_enabled is False

def test_type_conversion_and_validation(monkeypatch):
    """Test that pydantic properly casts environment values into appropriate Python types."""
    # Test numeric casting
    monkeypatch.setenv("IEEE_MAX_ARTICLES", "500")
    monkeypatch.setenv("IEEE_MIN_WAIT", "15")
    
    settings = Settings(_env_file=None)
    
    assert settings.ieee_max_articles == 500
    assert settings.ieee_min_wait == 15

def test_invalid_type_conversion(monkeypatch):
    """Test that pydantic throws errors for fundamentally bad inputs."""
    monkeypatch.setenv("IEEE_MAX_ARTICLES", "not-a-number")
    
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

def test_redis_stream_configs(monkeypatch):
    """Test redis stream new config overrides."""
    monkeypatch.setenv("REDIS_STREAMS_ENABLED", "false")
    monkeypatch.setenv("REDIS_STREAMS_CONSUMER_GROUP", "custom-group")
    monkeypatch.setenv("REDIS_STREAMS_DLQ_RETRY_INTERVAL", "600")

    settings = Settings(_env_file=None)
    
    assert settings.redis_streams_enabled is False
    assert settings.redis_streams_consumer_group == "custom-group"
    assert settings.redis_streams_dlq_retry_interval == 600

def test_db_wrapper_reads_central_db():
    from database.config import get_database_settings
    
    db_config = get_database_settings()
    # It queries central settings dynamically
    assert db_config.mongodb_min_pool_size == 1
    assert db_config.mongodb_max_pool_size == 10
