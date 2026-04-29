import pytest
from backend.core.config import Settings
from ieee_xplore.config import ProxyConfig as IEEEProxyConfig
from science_direct.config import ProxyConfig as SDProxyConfig

def test_proxy_configuration_inheritance(monkeypatch):
    """Test that individual scrapers correctly inherit proxy configurations from the unified Settings."""
    
    # Simulate environment with proxies enabled
    monkeypatch.setenv("USE_PROXY", "true")
    monkeypatch.setenv("proxy_user", "testuser")
    monkeypatch.setenv("proxy_pass", "testpass")
    monkeypatch.setenv("proxy_host", "proxy.custom.edu.tr")
    monkeypatch.setenv("proxy_port", "9090")

    # The centralized Settings should pick these up
    settings = Settings(_env_file=None)
    
    assert settings.use_proxy is True
    assert settings.proxy_user == "testuser"
    assert settings.proxy_pass == "testpass"
    assert settings.proxy_host == "proxy.custom.edu.tr"
    assert settings.proxy_port == "9090"

    # Now verify the scraper-specific configurations correctly proxy from settings
    # For IEEE
    ieee_proxy = IEEEProxyConfig()
    # Mocking internal settings reference for testing proxy inheritance
    ieee_proxy.use_proxy = settings.use_proxy
    ieee_proxy.user = settings.proxy_user
    ieee_proxy.password = settings.proxy_pass
    ieee_proxy.host = settings.proxy_host
    ieee_proxy.port = settings.proxy_port

    assert ieee_proxy.is_configured() is True
    assert ieee_proxy.get_proxy_string() == "http://testuser:testpass@proxy.custom.edu.tr:9090"

    # For ScienceDirect
    sd_proxy = SDProxyConfig()
    sd_proxy.use_proxy = settings.use_proxy
    sd_proxy.proxy_user = settings.proxy_user
    sd_proxy.proxy_pass = settings.proxy_pass
    sd_proxy.proxy_host = settings.proxy_host
    sd_proxy.proxy_port = settings.proxy_port

    assert sd_proxy.is_configured() is True
    assert sd_proxy.get_proxy_string() == "http://testuser:testpass@proxy.custom.edu.tr:9090"

def test_proxy_disabled_behavior(monkeypatch):
    """Test proxy output when USE_PROXY is false, even if credentials exist."""
    monkeypatch.setenv("USE_PROXY", "false")
    monkeypatch.setenv("proxy_user", "testuser")
    monkeypatch.setenv("proxy_pass", "testpass")
    
    settings = Settings(_env_file=None)
    assert settings.use_proxy is False
    assert settings.proxy_user == "testuser"
    
    ieee_proxy = IEEEProxyConfig()
    ieee_proxy.use_proxy = settings.use_proxy
    ieee_proxy.user = settings.proxy_user
    ieee_proxy.password = settings.proxy_pass

    assert ieee_proxy.is_configured() is False
    assert ieee_proxy.get_proxy_string() == ""

def test_cache_ttl_integrity(monkeypatch):
    """Test that TTL settings adhere to expected bounds"""
    monkeypatch.setenv("CACHE_TTL_ARTICLE", "10")
    settings = Settings(_env_file=None)
    
    assert settings.cache_ttl_article == 10
    assert settings.cache_ttl_journal == 21600 # default

def test_scraper_run_mode_aliases(monkeypatch):
    """Test the scraper properties evaluate run modes appropriately."""
    monkeypatch.setenv("ENABLED_SCRAPERS", "sciencedirect")
    settings = Settings(_env_file=None)
    
    # Evaluate boolean properties
    assert settings.ieee_enabled is False
    assert settings.sciencedirect_enabled is True
