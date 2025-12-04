"""
Repository Base Class
Tüm repository'ler için temel sınıf
"""

from typing import TypeVar, Generic, Optional, List, Type
from beanie import Document, PydanticObjectId

T = TypeVar('T', bound=Document)


class BaseRepository(Generic[T]):
    """
    Generic Repository Base Class
    
    CRUD operasyonlarının temel implementasyonu
    """
    
    model: Type[T]
    
    def __init__(self, model: Type[T]):
        self.model = model
    
    async def create(self, document: T) -> T:
        """Yeni kayıt oluştur"""
        await document.insert()
        return document
    
    async def create_many(self, documents: List[T]) -> List[T]:
        """Toplu kayıt oluştur"""
        if documents:
            await self.model.insert_many(documents)
        return documents
    
    async def get_by_id(self, id: PydanticObjectId) -> Optional[T]:
        """ID'ye göre kayıt getir"""
        return await self.model.get(id)
    
    async def get_all(self, limit: int = 100, skip: int = 0) -> List[T]:
        """Tüm kayıtları getir (sayfalama ile)"""
        return await self.model.find_all().skip(skip).limit(limit).to_list()
    
    async def update(self, document: T) -> T:
        """Kayıt güncelle"""
        await document.save()
        return document
    
    async def delete(self, document: T) -> bool:
        """Kayıt sil"""
        await document.delete()
        return True
    
    async def delete_by_id(self, id: PydanticObjectId) -> bool:
        """ID'ye göre kayıt sil"""
        document = await self.get_by_id(id)
        if document:
            await document.delete()
            return True
        return False
    
    async def count(self) -> int:
        """Toplam kayıt sayısı"""
        return await self.model.count()
    
    async def exists(self, id: PydanticObjectId) -> bool:
        """Kayıt var mı?"""
        return await self.get_by_id(id) is not None
    
    async def find_one(self, query: dict) -> Optional[T]:
        """Query ile tek kayıt bul"""
        return await self.model.find_one(query)
    
    async def find_many(self, query: dict, limit: int = 100) -> List[T]:
        """Query ile birden fazla kayıt bul"""
        return await self.model.find(query).limit(limit).to_list()
