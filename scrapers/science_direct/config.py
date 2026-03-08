"""
Configuration classes for Science Direct scraper
"""

import os
import sys
from pathlib import Path
from pathlib import Path

# backend ayarlarını import et
from backend.core.config import settings

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')


class ProxyConfig:
    """Proxy yapılandırma sınıfı"""
    
    def __init__(self):
        """Proxy bilgilerini .env dosyasından yükler"""
        self.use_proxy = settings.use_proxy
        self.proxy_user = settings.proxy_user
        self.proxy_pass = settings.proxy_pass
        self.proxy_host = settings.proxy_host
        self.proxy_port = settings.proxy_port
    
    def get_proxy_string(self) -> str:
        """Proxy bağlantı string'ini döndürür"""
        if self.proxy_user and self.proxy_pass:
            logger.info(f"http://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}")
            return f"http://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}"
        return None
    
    def is_configured(self) -> bool:
        """Proxy yapılandırılmış mı ve USE_PROXY=true mi kontrol eder"""
        if not self.use_proxy:
            return False
        return bool(self.proxy_user and self.proxy_pass)


class ScienceDirectConfig:
    """Science Direct yapılandırma sınıfı"""
    
    def __init__(self):
        """URL'leri ve ayarları .env dosyasından yükler"""
        self.base_url = settings.sciencedirect_base_url
        self.timeout = settings.sd_timeout
        self.implicit_wait = settings.sd_implicit_wait
