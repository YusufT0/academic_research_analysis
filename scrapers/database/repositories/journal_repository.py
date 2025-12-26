"""
Journal Repository
Dergi CRUD operasyonları
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
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
    
    async def check_exists(self, name: str, source_website: str) -> bool:
        """
        Derginin veritabanında olup olmadığını kontrol et
        
        Args:
            name: Dergi adı
            source_website: Kaynak site
            
        Returns:
            bool: Varsa True, yoksa False
        """
        existing = await self.find_by_name(name, source_website)
        return existing is not None
    
    async def get_journal_priority_info(
        self,
        name: str,
        source_website: str
    ) -> dict:
        """
        Dergi için öncelik bilgisi al
        
        Args:
            name: Dergi adı
            source_website: Kaynak site
            
        Returns:
            dict: {'exists': bool, 'last_scraped_at': datetime or None}
        """
        existing = await self.find_by_name(name, source_website)
        if existing:
            return {
                'exists': True,
                'last_scraped_at': existing.last_scraped_at,
                'scrape_count': existing.scrape_count
            }
        return {
            'exists': False,
            'last_scraped_at': None,
            'scrape_count': 0
        }
    
    async def get_bulk_priority_info(
        self,
        journal_names: List[str],
        source_website: str
    ) -> dict:
        """
        Birden fazla dergi için öncelik bilgilerini toplu al
        
        Args:
            journal_names: Dergi adları listesi
            source_website: Kaynak site
            
        Returns:
            dict: {journal_name: {'exists': bool, 'last_scraped_at': datetime}}
        """
        # Veritabanındaki eşleşen dergileri bul
        journals = await Journal.find({
            "name": {"$in": journal_names},
            "source_website": source_website
        }).to_list()
        
        # Dict'e çevir
        db_journals = {j.name: j for j in journals}
        
        # Sonuç dict'i oluştur
        result = {}
        for name in journal_names:
            if name in db_journals:
                j = db_journals[name]
                result[name] = {
                    'exists': True,
                    'last_scraped_at': j.last_scraped_at,
                    'scrape_count': j.scrape_count
                }
            else:
                result[name] = {
                    'exists': False,
                    'last_scraped_at': None,
                    'scrape_count': 0
                }
        
        return result
    
    @staticmethod
    def prioritize_journals(
        journals: List[Dict[str, Any]],
        priority_info: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """
        Dergileri öncelik sistemine göre sırala
        
        Öncelik Sırası:
        1. Veritabanında bulunmayan dergiler (yeni dergiler)
        2. Veritabanında olan dergiler - last_scraped_at tarihine göre (en eski önce)
        
        Args:
            journals: Dergi listesi
            priority_info: Her dergi için öncelik bilgisi dict'i
            
        Returns:
            Sıralanmış dergi listesi
        """
        # Dergileri iki gruba ayır: yeni ve mevcut
        new_journals = []  # Veritabanında olmayanlar
        existing_journals = []  # Veritabanında olanlar
        
        for journal in journals:
            name = journal.get('name', '')
            info = priority_info.get(name, {'exists': False, 'last_scraped_at': None})
            
            if not info['exists']:
                new_journals.append(journal)
            else:
                # last_scraped_at bilgisini journal dict'ine ekle (sıralama için)
                journal['_last_scraped_at'] = info['last_scraped_at']
                journal['_scrape_count'] = info.get('scrape_count', 0)
                existing_journals.append(journal)
        
        # Mevcut dergileri last_scraped_at'e göre sırala (en eski önce)
        # None değerler en başta olsun (hiç scrape edilmemiş)
        existing_journals.sort(
            key=lambda x: (
                x.get('_last_scraped_at') is not None,  # None olanlar önce
                x.get('_last_scraped_at') or datetime.min  # Sonra tarihe göre (en eski önce)
            )
        )
        
        # Önce yeni dergiler, sonra eskiye göre sıralanmış mevcut dergiler
        prioritized = new_journals + existing_journals
        
        return prioritized
