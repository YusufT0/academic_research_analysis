"""
Configuration management for Wiley Online Library scraper
"""

from pathlib import Path

# backend ayarlarını import et
from backend.core.config import settings


class ProxyConfig:
    """Proxy ayarlarını yöneten sınıf"""

    def __init__(self):
        """Environment variables'dan proxy ayarlarını yükle"""
        self.use_proxy = settings.use_proxy
        self.user = settings.proxy_user
        self.password = settings.proxy_pass
        self.host = settings.proxy_host
        self.port = settings.proxy_port

    def is_configured(self) -> bool:
        """Proxy kullanılacak mı ve gerekli bilgiler var mı kontrol et"""
        if not self.use_proxy:
            return False
        return bool(self.user and self.password and self.host and self.port)

    def get_proxy_string(self) -> str:
        """SeleniumBase için proxy string oluştur: user:pass@host:port"""
        if not self.is_configured():
            return ""
        return f"{self.user}:{self.password}@{self.host}:{self.port}"


class WileyConfig:
    """Wiley Online Library scraper için genel ayarlar"""

    def __init__(self):
        """Environment variables'dan Wiley ayarlarını yükle"""
        self.base_url = getattr(
            settings,
            'wiley_base_url',
            'https://onlinelibrary.wiley.com/action/showPublications?ConceptID=68&PubType=journal&startPage=0&pageSize=20'
        )
        self.wiley_domain = "https://onlinelibrary.wiley.com"

        # Rate limiting ayarları
        self.min_wait = getattr(settings, 'wiley_min_wait', 4)
        self.max_wait = getattr(settings, 'wiley_max_wait', 10)
        self.page_load_timeout = getattr(settings, 'wiley_page_load_timeout', 90)
        self.max_articles = getattr(settings, 'wiley_max_articles', 100)
