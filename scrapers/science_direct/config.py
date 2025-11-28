"""
Configuration classes for Science Direct scraper
"""

import os
from dotenv import load_dotenv


class ProxyConfig:
    """Proxy yapılandırma sınıfı"""
    
    def __init__(self):
        """Proxy bilgilerini .env dosyasından yükler"""
        load_dotenv()
        self.proxy_user = os.getenv('proxy_user')
        self.proxy_pass = os.getenv('proxy_pass')
        self.proxy_host = os.getenv('proxy_host', 'proxy.gazi.edu.tr')
        self.proxy_port = os.getenv('proxy_port', '8080')
    
    def get_proxy_string(self) -> str:
        """Proxy bağlantı string'ini döndürür"""
        if self.proxy_user and self.proxy_pass:
            print(f"http://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}")
            return f"http://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}"
        return None
    
    def is_configured(self) -> bool:
        """Proxy yapılandırılmış mı kontrol eder"""
        return bool(self.proxy_user and self.proxy_pass)


class ScienceDirectConfig:
    """Science Direct yapılandırma sınıfı"""
    
    def __init__(self):
        """URL'leri ve ayarları .env dosyasından yükler"""
        load_dotenv()
        self.base_url = os.getenv(
            'SCIENCEDIRECT_BASE_URL',
            'https://www.sciencedirect.com/browse/journals-and-books?contentType=JL&subject=computer-science'
        )
        self.timeout = 30  # Sayfa yükleme timeout süresi (saniye)
        self.implicit_wait = 10  # Implicit wait süresi (saniye)
