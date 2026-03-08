"""
Database Configuration
Backend settings üzerinden konfigürasyon yönetimi
"""

from typing import Optional
from backend.core.config import settings

class DatabaseSettings:
    """MongoDB bağlantı ayarları - Backend Settings wrapper'ı"""
    
    @property
    def mongodb_uri(self) -> str:
        return settings.mongodb_uri
        
    @property
    def mongodb_database(self) -> str:
        return settings.mongodb_database
        
    @property
    def mongodb_username(self) -> Optional[str]:
        return settings.mongodb_username if hasattr(settings, 'mongodb_username') else None
        
    @property
    def mongodb_password(self) -> Optional[str]:
        return settings.mongodb_password if hasattr(settings, 'mongodb_password') else None
    
    # Connection Pool
    @property
    def mongodb_min_pool_size(self) -> int:
        return 1
        
    @property
    def mongodb_max_pool_size(self) -> int:
        return 10
    
    # Timeouts (ms)
    @property
    def mongodb_connect_timeout_ms(self) -> int:
        return 5000
        
    @property
    def mongodb_server_selection_timeout_ms(self) -> int:
        return 5000
    
    @property
    def connection_string(self) -> str:
        """Tam connection string oluştur"""
        if self.mongodb_username and self.mongodb_password:
            # URI'den protocol ve host'u ayır
            uri = self.mongodb_uri
            if "://" in uri:
                protocol, rest = uri.split("://", 1)
                return f"{protocol}://{self.mongodb_username}:{self.mongodb_password}@{rest}"
        return self.mongodb_uri

# Singleton instance
_settings: Optional[DatabaseSettings] = None

def get_database_settings() -> DatabaseSettings:
    """Database settings singleton'ı getir"""
    global _settings
    if _settings is None:
        _settings = DatabaseSettings()
    return _settings
