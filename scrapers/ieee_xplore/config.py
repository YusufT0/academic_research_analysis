"""
Configuration management for IEEE Xplore scraper
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasının yolunu belirle (scrapers klasöründe)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


class ProxyConfig:
    """Proxy ayarlarını yöneten sınıf"""
    
    def __init__(self):
        """Environment variables'dan proxy ayarlarını yükle"""
        # .env zaten modül yüklenirken okundu
        
        self.use_proxy = os.getenv('USE_PROXY', 'false').lower() in ('true', '1', 'yes', 'on')
        self.user = os.getenv('proxy_user', '')
        self.password = os.getenv('proxy_pass', '')
        self.host = os.getenv('proxy_host', '')
        self.port = os.getenv('proxy_port', '')
    
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
        # .env zaten modül yüklenirken okundu
        
        self.base_url = os.getenv(
            'IEEEXPLORE_BASE_URL',
            'https://ieeexplore.ieee.org/browse/periodicals/title?contentType=periodicals&showActiveTitlesOnly=true&refinements=ContentType:Journals'
        )
        
        # Rate limiting ayarları
        self.min_wait = 4  # minimum bekleme süresi (saniye)
        self.max_wait = 10  # maksimum bekleme süresi (saniye)
        self.page_load_timeout = 90  # sayfa yükleme timeout (saniye)
