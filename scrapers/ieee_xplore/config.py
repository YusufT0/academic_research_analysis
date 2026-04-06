"""
Configuration management for IEEE Xplore scraper
"""

import os
from pathlib import Path
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
        """Selenium-wire için proxy string oluştur"""
        if not self.is_configured():
            return ""
        return f"http://{self.user}:{self.password}@{self.host}:{self.port}"


class IEEEXploreConfig:
    """IEEE Xplore scraper için genel ayarlar"""
    
    def __init__(self):
        """Environment variables'dan IEEE Xplore ayarlarını yükle"""
        self.base_url = settings.ieeexplore_base_url
        
        # Rate limiting ayarları
        self.min_wait = settings.ieee_min_wait
        self.max_wait = settings.ieee_max_wait
        self.page_load_timeout = settings.ieee_page_load_timeout
