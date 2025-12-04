"""
Issue Repository
Dergi sayısı CRUD operasyonları
"""

from typing import Optional, List
from beanie import PydanticObjectId

from .base import BaseRepository
from ..models import Issue


class IssueRepository(BaseRepository[Issue]):
    """
    Issue Repository
    
    Dergi sayısı koleksiyonu için CRUD ve özel sorgular
    """
    
    def __init__(self):
        super().__init__(Issue)
    
    async def find_by_journal(self, journal_id: PydanticObjectId) -> List[Issue]:
        """Dergiye göre tüm sayıları bul"""
        return await Issue.find(
            {"journal_id": journal_id}
        ).sort("-year", "-month").to_list()
    
    async def find_by_journal_and_number(
        self,
        journal_id: PydanticObjectId,
        issue_number: str
    ) -> Optional[Issue]:
        """Dergi ve sayı numarasına göre bul"""
        return await Issue.find_one({
            "journal_id": journal_id,
            "issue_number": issue_number
        })
    
    async def find_or_create(
        self,
        journal_id: PydanticObjectId,
        journal_name: str,
        source_website: str,
        issue_number: Optional[str] = None,
        **kwargs
    ) -> tuple[Issue, bool]:
        """
        Sayı bul veya oluştur
        
        Returns:
            tuple: (Issue, created: bool)
        """
        if issue_number:
            existing = await self.find_by_journal_and_number(journal_id, issue_number)
            if existing:
                return existing, False
        
        issue = Issue(
            journal_id=journal_id,
            journal_name=journal_name,
            source_website=source_website,
            issue_number=issue_number,
            **kwargs
        )
        issue.parse_date()  # Tarih bilgilerini parse et
        await issue.insert()
        return issue, True
    
    async def find_latest_by_journal(self, journal_id: PydanticObjectId) -> Optional[Issue]:
        """Derginin en son sayısını bul"""
        issues = await Issue.find(
            {"journal_id": journal_id}
        ).sort("-year", "-month").limit(1).to_list()
        return issues[0] if issues else None
    
    async def find_by_year(
        self,
        year: int,
        source_website: Optional[str] = None
    ) -> List[Issue]:
        """Yıla göre sayıları bul"""
        query = {"year": year}
        if source_website:
            query["source_website"] = source_website
        return await Issue.find(query).to_list()
    
    async def get_count_by_journal(self, journal_id: PydanticObjectId) -> int:
        """Derginin sayı adedini getir"""
        return await Issue.find({"journal_id": journal_id}).count()
    
    async def get_years_range(self, journal_id: PydanticObjectId) -> dict:
        """Derginin yıl aralığını getir"""
        pipeline = [
            {"$match": {"journal_id": journal_id, "year": {"$ne": None}}},
            {
                "$group": {
                    "_id": None,
                    "min_year": {"$min": "$year"},
                    "max_year": {"$max": "$year"},
                    "years": {"$addToSet": "$year"}
                }
            }
        ]
        collection = Issue.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        if results:
            return {
                "min_year": results[0].get("min_year"),
                "max_year": results[0].get("max_year"),
                "years": sorted(results[0].get("years", []))
            }
        return {"min_year": None, "max_year": None, "years": []}
    
    async def update_article_count(
        self,
        issue_id: PydanticObjectId,
        count: int
    ) -> Optional[Issue]:
        """Sayının makale sayısını güncelle"""
        issue = await self.get_by_id(issue_id)
        if not issue:
            return None
        
        issue.article_count = count
        issue.touch()
        await issue.save()
        return issue
    
    async def increment_article_count(
        self,
        issue_id: PydanticObjectId,
        increment: int = 1
    ) -> Optional[Issue]:
        """Sayının makale sayısını artır"""
        issue = await self.get_by_id(issue_id)
        if not issue:
            return None
        
        issue.article_count += increment
        issue.touch()
        await issue.save()
        return issue
    
    async def upsert(
        self,
        journal_id: PydanticObjectId,
        journal_name: str,
        source_website: str,
        issue_number: Optional[str] = None,
        **kwargs
    ) -> tuple[Issue, bool]:
        """
        Sayı güncelle veya oluştur
        
        Returns:
            tuple: (Issue, created: bool)
        """
        existing = None
        if issue_number:
            existing = await self.find_by_journal_and_number(journal_id, issue_number)
        
        if existing:
            # Güncelle
            for key, value in kwargs.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            existing.touch()
            await existing.save()
            return existing, False
        
        # Yeni oluştur
        issue = Issue(
            journal_id=journal_id,
            journal_name=journal_name,
            source_website=source_website,
            issue_number=issue_number,
            **kwargs
        )
        issue.parse_date()
        await issue.insert()
        return issue, True
    
    async def delete_by_journal(self, journal_id: PydanticObjectId) -> int:
        """Dergiye ait tüm sayıları sil"""
        result = await Issue.find({"journal_id": journal_id}).delete()
        return result.deleted_count if result else 0
