"""
Journal Repository
Dergi CRUD operasyonları
"""

from typing import Optional, List
from beanie import PydanticObjectId

from .base import BaseRepository
from ..models import Journal


class JournalRepository(BaseRepository[Journal]):
    """
    Journal Repository
    
    Dergi koleksiyonu için CRUD ve özel sorgular
    """
    
    def __init__(self):
        super().__init__(Journal)
    
    async def find_by_name(self, name: str, source_website: str) -> Optional[Journal]:
        """
        İsim ve kaynak siteye göre dergi bul
        
        Args:
            name: Dergi adı
            source_website: Kaynak site (ieeexplore, sciencedirect)
        """
        return await Journal.find_one({
            "name": name,
            "source_website": source_website
        })
    
    async def find_or_create(
        self,
        name: str,
        source_website: str,
        **kwargs
    ) -> tuple[Journal, bool]:
        """
        Dergi bul veya oluştur
        
        Returns:
            tuple: (Journal, created: bool)
        """
        existing = await self.find_by_name(name, source_website)
        if existing:
            return existing, False
        
        journal = Journal(
            name=name,
            source_website=source_website,
            **kwargs
        )
        await journal.insert()
        return journal, True
    
    async def find_by_source(self, source_website: str) -> List[Journal]:
        """Kaynak siteye göre tüm dergileri bul"""
        return await Journal.find({"source_website": source_website}).to_list()
    
    async def find_by_publisher(self, publisher: str) -> List[Journal]:
        """Yayıncıya göre dergileri bul"""
        return await Journal.find({"publisher": publisher}).to_list()
    
    async def find_open_access(self, source_website: Optional[str] = None) -> List[Journal]:
        """Açık erişim dergileri bul"""
        query = {"open_access": True}
        if source_website:
            query["source_website"] = source_website
        return await Journal.find(query).to_list()
    
    async def search_by_name(self, search_term: str, limit: int = 50) -> List[Journal]:
        """İsimde arama yap"""
        return await Journal.find({
            "name": {"$regex": search_term, "$options": "i"}
        }).limit(limit).to_list()
    
    async def get_statistics_by_source(self) -> List[dict]:
        """Kaynak site bazlı istatistikler"""
        pipeline = [
            {
                "$group": {
                    "_id": "$source_website",
                    "total_journals": {"$sum": 1},
                    "total_issues": {"$sum": "$issue_count"},
                    "total_articles": {"$sum": "$article_count"},
                    "open_access_count": {
                        "$sum": {"$cond": ["$open_access", 1, 0]}
                    }
                }
            },
            {"$sort": {"total_journals": -1}}
        ]
        # PyMongo collection üzerinden aggregate
        collection = Journal.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
    
    async def update_counts(
        self,
        journal_id: PydanticObjectId,
        issue_count: Optional[int] = None,
        article_count: Optional[int] = None
    ) -> Optional[Journal]:
        """Dergi sayılarını güncelle"""
        journal = await self.get_by_id(journal_id)
        if not journal:
            return None
        
        if issue_count is not None:
            journal.issue_count = issue_count
        if article_count is not None:
            journal.article_count = article_count
        
        journal.touch()
        await journal.save()
        return journal
    
    async def increment_counts(
        self,
        journal_id: PydanticObjectId,
        issue_increment: int = 0,
        article_increment: int = 0
    ) -> Optional[Journal]:
        """Dergi sayılarını artır"""
        journal = await self.get_by_id(journal_id)
        if not journal:
            return None
        
        journal.issue_count += issue_increment
        journal.article_count += article_increment
        journal.touch()
        await journal.save()
        return journal
    
    async def upsert(
        self,
        name: str,
        source_website: str,
        **kwargs
    ) -> tuple[Journal, bool]:
        """
        Dergi güncelle veya oluştur
        
        Returns:
            tuple: (Journal, created: bool)
        """
        existing = await self.find_by_name(name, source_website)
        
        if existing:
            # Güncelle
            for key, value in kwargs.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            existing.mark_scraped()
            await existing.save()
            return existing, False
        
        # Yeni oluştur
        journal = Journal(
            name=name,
            source_website=source_website,
            **kwargs
        )
        await journal.insert()
        return journal, True
