"""
Configuration management for ACM scraper
"""

import os
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


class ACMConfig:
    """ACM scraper için genel ayarlar"""
    
    def __init__(self):
        """ACM ayarlarını yükle"""
        self.base_url = getattr(settings, 'acm_base_url', 'https://dl.acm.org/journals')
        
        # Rate limiting ayarları
        self.min_wait = getattr(settings, 'acm_min_wait', 4)
        self.max_wait = getattr(settings, 'acm_max_wait', 10)
        self.page_load_timeout = getattr(settings, 'acm_page_load_timeout', 90)
        self.max_articles = getattr(settings, 'acm_max_articles', 100)
