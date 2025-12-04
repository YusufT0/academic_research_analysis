"""
Database Configuration
Pydantic Settings ile konfigürasyon yönetimi
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class DatabaseSettings(BaseSettings):
    """MongoDB bağlantı ayarları"""
    
    # Connection
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI"
    )
    mongodb_database: str = Field(
        default="academic_research",
        description="Database adı"
    )
    
    # Authentication (opsiyonel)
    mongodb_username: Optional[str] = Field(default=None)
    mongodb_password: Optional[str] = Field(default=None)
    
    # Connection Pool
    mongodb_min_pool_size: int = Field(default=1)
    mongodb_max_pool_size: int = Field(default=10)
    
    # Timeouts (ms)
    mongodb_connect_timeout_ms: int = Field(default=5000)
    mongodb_server_selection_timeout_ms: int = Field(default=5000)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Diğer env değişkenlerini yoksay
    
    @property
    def connection_string(self) -> str:
        """Tam connection string oluştur"""
        if self.mongodb_username and self.mongodb_password:
            # URI'den protocol ve host'u ayır
            if "://" in self.mongodb_uri:
                protocol, rest = self.mongodb_uri.split("://", 1)
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
