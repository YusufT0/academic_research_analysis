"""
Article Repository
Makale CRUD operasyonları
"""

from typing import Optional, List
from beanie import PydanticObjectId

from .base import BaseRepository
from ..models import Article


class ArticleRepository(BaseRepository[Article]):
    """
    Article Repository
    
    Makale koleksiyonu için CRUD ve özel sorgular
    """
    
    def __init__(self):
        super().__init__(Article)
    
    async def find_by_doi(self, doi: str) -> Optional[Article]:
        """DOI'ye göre makale bul"""
        return await Article.find_one({"doi": doi})
    
    async def find_by_url(self, url: str) -> Optional[Article]:
        """URL'ye göre makale bul"""
        return await Article.find_one({"url": url})
    
    async def find_by_doi_or_url(
        self,
        doi: Optional[str],
        url: str
    ) -> Optional[Article]:
        """DOI veya URL'ye göre makale bul"""
        if doi:
            article = await self.find_by_doi(doi)
            if article:
                return article
        return await self.find_by_url(url)
    
    async def find_or_create(
        self,
        url: str,
        title: str,
        journal_id: PydanticObjectId,
        journal_name: str,
        issue_id: PydanticObjectId,
        source_website: str,
        doi: Optional[str] = None,
        **kwargs
    ) -> tuple[Article, bool]:
        """
        Makale bul veya oluştur
        
        Returns:
            tuple: (Article, created: bool)
        """
        existing = await self.find_by_doi_or_url(doi, url)
        if existing:
            return existing, False
        
        article = Article(
            url=url,
            title=title,
            journal_id=journal_id,
            journal_name=journal_name,
            issue_id=issue_id,
            source_website=source_website,
            doi=doi,
            **kwargs
        )
        article.parse_publication_year()
        await article.insert()
        return article, True
    
    async def find_by_issue(self, issue_id: PydanticObjectId) -> List[Article]:
        """Sayıya göre tüm makaleleri bul"""
        return await Article.find({"issue_id": issue_id}).to_list()
    
    async def find_by_journal(self, journal_id: PydanticObjectId) -> List[Article]:
        """Dergiye göre tüm makaleleri bul"""
        return await Article.find({"journal_id": journal_id}).to_list()
    
    async def search_by_title(self, search_term: str, limit: int = 100) -> List[Article]:
        """Başlıkta arama yap"""
        return await Article.find({
            "title": {"$regex": search_term, "$options": "i"}
        }).limit(limit).to_list()
    
    async def search_by_keyword(self, keyword: str, limit: int = 100) -> List[Article]:
        """Anahtar kelimeye göre ara"""
        return await Article.find({
            "keywords": {"$in": [keyword]}
        }).limit(limit).to_list()
    
    async def search_by_keywords(self, keywords: List[str], limit: int = 100) -> List[Article]:
        """Birden fazla anahtar kelimeye göre ara"""
        return await Article.find({
            "keywords": {"$in": keywords}
        }).limit(limit).to_list()
    
    async def search_by_author(self, author: str, limit: int = 100) -> List[Article]:
        """Yazara göre ara"""
        return await Article.find({
            "authors": {"$regex": author, "$options": "i"}
        }).limit(limit).to_list()
    
    async def text_search(self, query: str, limit: int = 100) -> List[Article]:
        """Full-text arama (title ve abstract'ta)"""
        return await Article.find({
            "$text": {"$search": query}
        }).limit(limit).to_list()
    
    async def find_by_year(
        self,
        year: int,
        source_website: Optional[str] = None
    ) -> List[Article]:
        """Yayın yılına göre bul"""
        query = {"publication_year": year}
        if source_website:
            query["source_website"] = source_website
        return await Article.find(query).to_list()
    
    async def find_by_year_range(
        self,
        start_year: int,
        end_year: int,
        source_website: Optional[str] = None
    ) -> List[Article]:
        """Yıl aralığına göre bul"""
        query = {
            "publication_year": {"$gte": start_year, "$lte": end_year}
        }
        if source_website:
            query["source_website"] = source_website
        return await Article.find(query).to_list()
    
    async def get_count_by_issue(self, issue_id: PydanticObjectId) -> int:
        """Sayıdaki makale adedini getir"""
        return await Article.find({"issue_id": issue_id}).count()
    
    async def get_count_by_journal(self, journal_id: PydanticObjectId) -> int:
        """Dergideki makale adedini getir"""
        return await Article.find({"journal_id": journal_id}).count()
    
    async def get_statistics_by_source(self) -> List[dict]:
        """Kaynak site bazlı istatistikler"""
        pipeline = [
            {
                "$group": {
                    "_id": "$source_website",
                    "total_articles": {"$sum": 1},
                    "with_abstract": {
                        "$sum": {"$cond": [{"$ne": ["$abstract", None]}, 1, 0]}
                    },
                    "with_doi": {
                        "$sum": {"$cond": [{"$ne": ["$doi", None]}, 1, 0]}
                    },
                    "with_keywords": {
                        "$sum": {"$cond": [{"$gt": [{"$size": "$keywords"}, 0]}, 1, 0]}
                    },
                    "total_citations": {"$sum": "$citation_count"},
                    "avg_authors": {"$avg": {"$size": "$authors"}}
                }
            },
            {"$sort": {"total_articles": -1}}
        ]
        collection = Article.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
    
    async def get_top_keywords(
        self,
        limit: int = 20,
        source_website: Optional[str] = None
    ) -> List[dict]:
        """En çok kullanılan anahtar kelimeleri getir"""
        match_stage = {}
        if source_website:
            match_stage = {"$match": {"source_website": source_website}}
        
        pipeline = [
            {"$unwind": "$keywords"},
            {
                "$group": {
                    "_id": "$keywords",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        if match_stage:
            pipeline.insert(0, match_stage)
        
        collection = Article.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
    
    async def get_top_authors(
        self,
        limit: int = 20,
        source_website: Optional[str] = None
    ) -> List[dict]:
        """En çok makale yazan yazarları getir"""
        match_stage = {}
        if source_website:
            match_stage = {"$match": {"source_website": source_website}}
        
        pipeline = [
            {"$unwind": "$authors"},
            {
                "$group": {
                    "_id": "$authors",
                    "article_count": {"$sum": 1}
                }
            },
            {"$sort": {"article_count": -1}},
            {"$limit": limit}
        ]
        
        if match_stage:
            pipeline.insert(0, match_stage)
        
        collection = Article.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
    
    async def upsert(
        self,
        url: str,
        title: str,
        journal_id: PydanticObjectId,
        journal_name: str,
        issue_id: PydanticObjectId,
        source_website: str,
        doi: Optional[str] = None,
        **kwargs
    ) -> tuple[Article, bool]:
        """
        Makale güncelle veya oluştur
        
        Returns:
            tuple: (Article, created: bool)
        """
        existing = await self.find_by_doi_or_url(doi, url)
        
        if existing:
            # Güncelle
            for key, value in kwargs.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            existing.touch()
            await existing.save()
            return existing, False
        
        # Yeni oluştur
        article = Article(
            url=url,
            title=title,
            journal_id=journal_id,
            journal_name=journal_name,
            issue_id=issue_id,
            source_website=source_website,
            doi=doi,
            **kwargs
        )
        article.parse_publication_year()
        await article.insert()
        return article, True
    
    async def bulk_create(self, articles_data: List[dict]) -> int:
        """
        Toplu makale oluştur (duplicate kontrolü ile)
        
        Returns:
            int: Oluşturulan makale sayısı
        """
        created_count = 0
        for data in articles_data:
            doi = data.get('doi')
            url = data.get('url')
            
            if not url:
                continue
            
            existing = await self.find_by_doi_or_url(doi, url)
            if not existing:
                article = Article(**data)
                article.parse_publication_year()
                await article.insert()
                created_count += 1
        
        return created_count
    
    async def delete_by_issue(self, issue_id: PydanticObjectId) -> int:
        """Sayıya ait tüm makaleleri sil"""
        result = await Article.find({"issue_id": issue_id}).delete()
        return result.deleted_count if result else 0
    
    async def delete_by_journal(self, journal_id: PydanticObjectId) -> int:
        """Dergiye ait tüm makaleleri sil"""
        result = await Article.find({"journal_id": journal_id}).delete()
        return result.deleted_count if result else 0
