"""
Database Connection Manager
Async MongoDB bağlantı yönetimi
"""

import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from .config import get_database_settings, DatabaseSettings
from .models import Journal, Issue, Article

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

logger = get_logger('database')


class DatabaseConnection:
    """
    MongoDB bağlantı yöneticisi
    
    Singleton pattern ile tek bağlantı instance'ı sağlar.
    Async context manager olarak kullanılabilir.
    """
    
    _instance: Optional["DatabaseConnection"] = None
    _client: Optional[AsyncIOMotorClient] = None
    _initialized: bool = False
    _lock: asyncio.Lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.settings: DatabaseSettings = get_database_settings()
    
    @property
    def client(self) -> Optional[AsyncIOMotorClient]:
        """Motor client instance"""
        return self._client
    
    @property
    def database(self):
        """Database instance"""
        if self._client:
            return self._client[self.settings.mongodb_database]
        return None
    
    @property
    def is_connected(self) -> bool:
        """Bağlantı durumu"""
        return self._client is not None and self._initialized
    
    async def connect(self) -> bool:
        """
        MongoDB'ye bağlan ve Beanie'yi initialize et
        
        Returns:
            bool: Bağlantı başarılı ise True
        """
        async with self._lock:
            if self._initialized:
                logger.info("Database zaten bağlı")
                return True
            
            try:
                logger.section("MongoDB Bağlantısı")
                logger.info(f"URI: {self._mask_uri(self.settings.connection_string)}")
                logger.info(f"Database: {self.settings.mongodb_database}")
                
                # Motor client oluştur
                self._client = AsyncIOMotorClient(
                    self.settings.connection_string,
                    minPoolSize=self.settings.mongodb_min_pool_size,
                    maxPoolSize=self.settings.mongodb_max_pool_size,
                    connectTimeoutMS=self.settings.mongodb_connect_timeout_ms,
                    serverSelectionTimeoutMS=self.settings.mongodb_server_selection_timeout_ms,
                )
                
                # Bağlantıyı test et
                await self._client.admin.command('ping')
                logger.success("MongoDB bağlantısı başarılı")
                
                # Beanie'yi initialize et
                try:
                    await init_beanie(
                        database=self._client[self.settings.mongodb_database],
                        document_models=[Journal, Issue, Article]
                    )
                    logger.success("Beanie ODM initialize edildi")
                except Exception as beanie_error:
                    # Index conflict gibi kritik olmayan hataları yoksay
                    if "IndexOptionsConflict" in str(beanie_error) or "IndexKeySpecsConflict" in str(beanie_error):
                        logger.warning(f"Index conflict (yoksayıldı): {beanie_error}")
                    else:
                        raise beanie_error
                
                self._initialized = True
                return True
                
            except Exception as e:
                logger.error(f"MongoDB bağlantı hatası: {e}")
                self._client = None
                self._initialized = False
                return False
    
    async def disconnect(self):
        """MongoDB bağlantısını kapat"""
        async with self._lock:
            if self._client:
                self._client.close()
                self._client = None
                self._initialized = False
                logger.info("MongoDB bağlantısı kapatıldı")
    
    async def ping(self) -> bool:
        """Bağlantıyı test et"""
        try:
            if self._client:
                await self._client.admin.command('ping')
                return True
        except Exception:
            pass
        return False
    
    async def get_server_info(self) -> dict:
        """Server bilgilerini getir"""
        if self._client:
            return await self._client.server_info()
        return {}
    
    async def list_collections(self) -> List[str]:
        """Koleksiyonları listele"""
        if self.database:
            return await self.database.list_collection_names()
        return []
    
    async def drop_database(self, confirm: bool = False):
        """
        Database'i sil (DİKKAT!)
        
        Args:
            confirm: True olmalı, güvenlik için
        """
        if not confirm:
            logger.warning("Database silme onaylanmadı!")
            return
        
        if self._client:
            await self._client.drop_database(self.settings.mongodb_database)
            logger.warning(f"Database silindi: {self.settings.mongodb_database}")
    
    async def get_statistics(self) -> dict:
        """Database istatistiklerini getir"""
        if self.database is None:
            return {}
        
        stats = await self.database.command("dbstats")
        
        # Koleksiyon bazlı sayılar - Beanie 2.x syntax
        journal_count = await Journal.find().count()
        issue_count = await Issue.find().count()
        article_count = await Article.find().count()
        
        return {
            "database": self.settings.mongodb_database,
            "collections": stats.get("collections", 0),
            "data_size_mb": round(stats.get("dataSize", 0) / (1024 * 1024), 2),
            "storage_size_mb": round(stats.get("storageSize", 0) / (1024 * 1024), 2),
            "indexes": stats.get("indexes", 0),
            "journal_count": journal_count,
            "issue_count": issue_count,
            "article_count": article_count,
        }
    
    def _mask_uri(self, uri: str) -> str:
        """URI'deki şifreyi maskele"""
        import re
        return re.sub(r':([^:@]+)@', ':****@', uri)


# Global instance
_db_connection: Optional[DatabaseConnection] = None


def get_database() -> DatabaseConnection:
    """Database connection singleton'ı getir"""
    global _db_connection
    if _db_connection is None:
        _db_connection = DatabaseConnection()
    return _db_connection


@asynccontextmanager
async def database_context():
    """
    Database context manager
    
    Kullanım:
        async with database_context() as db:
            # db işlemleri
    """
    db = get_database()
    try:
        await db.connect()
        yield db
    finally:
        await db.disconnect()


async def init_database() -> bool:
    """
    Database'i initialize et
    
    Returns:
        bool: Başarılı ise True
    """
    db = get_database()
    return await db.connect()


async def close_database():
    """Database bağlantısını kapat"""
    db = get_database()
    await db.disconnect()
