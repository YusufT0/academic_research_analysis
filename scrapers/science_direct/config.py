"""
Configuration classes for Science Direct scraper
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasının yolunu belirle (scrapers klasöründe)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')


class ProxyConfig:
    """Proxy yapılandırma sınıfı"""
    
    def __init__(self):
        """Proxy bilgilerini .env dosyasından yükler"""
        # .env zaten modül yüklenirken okundu
        self.use_proxy = os.getenv('USE_PROXY', 'false').lower() in ('true', '1', 'yes', 'on')
        self.proxy_user = os.getenv('proxy_user')
        self.proxy_pass = os.getenv('proxy_pass')
        self.proxy_host = os.getenv('proxy_host', 'proxy.gazi.edu.tr')
        self.proxy_port = os.getenv('proxy_port', '8080')
    
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
        # .env zaten modül yüklenirken okundu
        self.base_url = os.getenv(
            'SCIENCEDIRECT_BASE_URL',
            'https://www.sciencedirect.com/browse/journals-and-books?contentType=JL&subject=computer-science'
        )
        self.timeout = 90  # Sayfa yükleme timeout süresi (saniye)
        self.implicit_wait = 90  # Implicit wait süresi (saniye)
