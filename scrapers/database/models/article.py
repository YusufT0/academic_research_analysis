"""
Database Models - Article
Akademik makale modeli
"""

from datetime import datetime
from typing import Optional, List
from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field

from .base import TimestampMixin


class Article(Document, TimestampMixin):
    """
    Akademik Makale Modeli
    
    Her makale bir Issue'ya ve Journal'a bağlıdır.
    DOI veya URL benzersiz tanımlayıcı olarak kullanılır.
    """
    
    # İlişkiler
    journal_id: PydanticObjectId = Field(..., description="Bağlı olduğu dergi ID'si")
    journal_name: str = Field(..., description="Dergi adı (denormalize)")
    issue_id: PydanticObjectId = Field(..., description="Bağlı olduğu sayı ID'si")
    issue_number: Optional[str] = Field(None, description="Sayı numarası (denormalize)")
    source_website: str = Field(..., description="Kaynak site")
    
    # Temel bilgiler
    title: str = Field(..., description="Makale başlığı")
    url: str = Field(..., description="Makale URL'si")
    doi: Optional[str] = Field(None, description="DOI numarası")
    
    # İçerik
    abstract: Optional[str] = Field(None, description="Özet")
    introduction: Optional[str] = Field(None, description="Giriş bölümü")
    keywords: List[str] = Field(default_factory=list, description="Anahtar kelimeler")
    
    # Yazarlar
    authors: List[str] = Field(default_factory=list, description="Yazar listesi")
    
    # Yayın bilgileri
    publication_date: Optional[str] = Field(None, description="Yayın tarihi string")
    publication_year: Optional[int] = Field(None, description="Yayın yılı")
    pages: Optional[str] = Field(None, description="Sayfa aralığı")
    publisher: Optional[str] = Field(None, description="Yayıncı")
    
    # Makale tipi ve erişim
    article_type: Optional[str] = Field(None, description="Makale tipi: Research article, Review, etc.")
    open_access: bool = Field(default=False, description="Açık erişim mi?")
    
    # PDF ve referanslar
    pdf_url: Optional[str] = Field(None, description="PDF URL'si")
    citation_count: int = Field(default=0, description="Atıf sayısı")
    references: List[str] = Field(default_factory=list, description="Referanslar")
    
    # OpenAlex ve Atıf Meta Verileri
    openalex_id: Optional[str] = Field(None, description="OpenAlex API üzerindeki ID'si")
    is_openalex_indexed: bool = Field(default=False, description="OpenAlex tarafında bulundu mu?")
    historical_citation_data: dict = Field(default_factory=dict, description="Yıllara göre atıf sayıları {2023: 10, 2024: 15}")
    citation_percentile: Optional[float] = Field(None, description="Aynı yıl yayınlanan makalelere göre atıf yüzdelik dilimi (Örn: 95.5)")
    fwci: Optional[float] = Field(None, description="Field-Weighted Citation Impact (Alana göre normalize edilmiş atıf etki değeri)")
    last_citation_update_date: Optional[datetime] = Field(None, description="Atıf verisinin son güncellenme tarihi")
    
    # Scraping metadata
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    content_hash: Optional[str] = Field(None, description="İçerik hash'i - değişiklik tespiti için")
    
    class Settings:
        name = "articles"
        indexes = [
            [("doi", 1)],  # Sparse unique - DOI varsa benzersiz olmalı
            [("url", 1)],  # Unique
            [("journal_id", 1)],
            [("issue_id", 1)],
            [("source_website", 1)],
            [("publication_year", -1)],
            [("keywords", 1)],
            [("authors", 1)],
            [("title", "text"), ("abstract", "text")],  # Text search index
        ]
    
    def parse_publication_year(self):
        """Publication date'den yıl çıkar"""
        if self.publication_date:
            import re
            year_match = re.search(r'(\d{4})', self.publication_date)
            if year_match:
                self.publication_year = int(year_match.group(1))
    
    def calculate_content_hash(self) -> str:
        """İçerik hash'i hesapla"""
        import hashlib
        content = f"{self.title}|{self.abstract or ''}|{','.join(self.authors)}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    @classmethod
    async def find_by_doi(cls, doi: str) -> Optional["Article"]:
        """DOI'ye göre makale bul"""
        return await cls.find_one({"doi": doi})
    
    @classmethod
    async def find_by_url(cls, url: str) -> Optional["Article"]:
        """URL'ye göre makale bul"""
        return await cls.find_one({"url": url})
    
    @classmethod
    async def find_by_doi_or_url(cls, doi: Optional[str], url: str) -> Optional["Article"]:
        """DOI veya URL'ye göre makale bul"""
        if doi:
            article = await cls.find_by_doi(doi)
            if article:
                return article
        return await cls.find_by_url(url)
    
    @classmethod
    async def find_by_issue(cls, issue_id: PydanticObjectId) -> List["Article"]:
        """Sayıya göre tüm makaleleri bul"""
        return await cls.find({"issue_id": issue_id}).to_list()
    
    @classmethod
    async def find_by_journal(cls, journal_id: PydanticObjectId) -> List["Article"]:
        """Dergiye göre tüm makaleleri bul"""
        return await cls.find({"journal_id": journal_id}).to_list()
    
    @classmethod
    async def search_by_keyword(cls, keyword: str, limit: int = 100) -> List["Article"]:
        """Anahtar kelimeye göre ara"""
        return await cls.find({"keywords": {"$in": [keyword]}}).limit(limit).to_list()
    
    @classmethod
    async def search_by_author(cls, author: str, limit: int = 100) -> List["Article"]:
        """Yazara göre ara"""
        return await cls.find({"authors": {"$regex": author, "$options": "i"}}).limit(limit).to_list()
    
    @classmethod
    async def text_search(cls, query: str, limit: int = 100) -> List["Article"]:
        """Full-text arama"""
        return await cls.find({"$text": {"$search": query}}).limit(limit).to_list()
    
    @classmethod
    async def get_count_by_issue(cls, issue_id: PydanticObjectId) -> int:
        """Sayıdaki makale adedini getir"""
        return await cls.find({"issue_id": issue_id}).count()
    
    @classmethod
    async def get_count_by_journal(cls, journal_id: PydanticObjectId) -> int:
        """Dergideki makale adedini getir"""
        return await cls.find({"journal_id": journal_id}).count()
    
    @classmethod
    async def get_statistics(cls, source_website: Optional[str] = None) -> dict:
        """İstatistikleri getir"""
        query = {"source_website": source_website} if source_website else {}
        
        pipeline = [
            {"$match": query},
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
                    "total_citations": {"$sum": "$citation_count"},
                    "avg_authors": {"$avg": {"$size": "$authors"}}
                }
            }
        ]
        
        collection = cls.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return results[0] if results else {}
