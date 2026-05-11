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
        return int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "30000"))
        
    @property
    def mongodb_server_selection_timeout_ms(self) -> int:
        return int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "30000"))

    @property
    def mongodb_socket_timeout_ms(self) -> int:
        return int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "60000"))

    @property
    def mongodb_max_idle_time_ms(self) -> int:
        return int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", "120000"))

    @property
    def mongodb_wait_queue_timeout_ms(self) -> int:
        return int(os.getenv("MONGODB_WAIT_QUEUE_TIMEOUT_MS", "30000"))

    
    @property
    def connection_string(self) -> str:
        """Tam connection string oluştur"""
        # Use .strip() and check truthiness to avoid empty string bugs
        user = (self.mongodb_username or "").strip()
        password = (self.mongodb_password or "").strip()

        if user and password:
            uri = self.mongodb_uri
            if "://" in uri:
                protocol, rest = uri.split("://", 1)
                return f"{protocol}://{user}:{password}@{rest}"
                
        # If no credentials, return the URI as 127.0.0.1 to avoid IPv6 issues
        return self.mongodb_uri.replace("localhost", "127.0.0.1")
# Singleton instance
_settings: Optional[DatabaseSettings] = None

def get_database_settings() -> DatabaseSettings:
    """Database settings singleton'ı getir"""
    global _settings
    if _settings is None:
        _settings = DatabaseSettings()
    return _settings
