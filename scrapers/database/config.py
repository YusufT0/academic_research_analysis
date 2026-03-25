"""
Database Configuration
"""

import os
from typing import Optional
from dotenv import load_dotenv

# dotenv'ı manuel yükle (döngüsel importu önlemek için Backend ayarlarına bağımlı kalmak istemiyorsak)
load_dotenv()

class DatabaseSettings:
    """MongoDB bağlantı ayarları"""
    
    @property
    def mongodb_uri(self) -> str:
        return os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        
    @property
    def mongodb_database(self) -> str:
        return os.getenv("MONGODB_DATABASE", "academic_research")
        
    @property
    def mongodb_username(self) -> Optional[str]:
        return os.getenv("MONGODB_USERNAME")
        
    @property
    def mongodb_password(self) -> Optional[str]:
        return os.getenv("MONGODB_PASSWORD")

    
    # Connection Pool — env override olarak MONGODB_MIN_POOL_SIZE / MONGODB_MAX_POOL_SIZE ayarlayın
    @property
    def mongodb_min_pool_size(self) -> int:
        return int(os.getenv("MONGODB_MIN_POOL_SIZE", "5"))

    @property
    def mongodb_max_pool_size(self) -> int:
        return int(os.getenv("MONGODB_MAX_POOL_SIZE", "50"))
    
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
