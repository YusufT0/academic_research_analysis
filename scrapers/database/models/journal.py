"""
Database Models - Journal
Akademik dergi modeli
"""

from datetime import datetime
from typing import Optional, List, Annotated
from beanie import Document, Indexed
from pydantic import Field

from .base import TimestampMixin, ScrapingMetaMixin


class Journal(Document, TimestampMixin, ScrapingMetaMixin):
    """
    Akademik Dergi Modeli
    
    Her dergi benzersiz bir name + source_website kombinasyonuna sahiptir.
    """
    
    # Temel bilgiler
    name: Annotated[str, Indexed()] = Field(..., description="Dergi adı")
    url: Optional[str] = Field(None, description="Dergi URL'si")
    
    # Sınıflandırma
    type: str = Field(default="Journal", description="Yayın tipi: Journal, Magazine, etc.")
    open_access: bool = Field(default=False, description="Açık erişim mi?")
    letter_group: Optional[str] = Field(None, description="Alfabetik grup (A, B, C...) - ScienceDirect için")
    
    # Yayıncı bilgisi
    publisher: Optional[str] = Field(None, description="Yayıncı: IEEE, Elsevier, etc.")
    
    # İstatistikler (denormalize - hızlı erişim için)
    issue_count: int = Field(default=0, description="Toplam sayı/cilt sayısı")
    article_count: int = Field(default=0, description="Toplam makale sayısı")
    
    # Ek metadata
    issn: Optional[str] = Field(None, description="ISSN numarası")
    eissn: Optional[str] = Field(None, description="e-ISSN numarası")
    impact_factor: Optional[float] = Field(None, description="Impact factor")
    subjects: List[str] = Field(default_factory=list, description="Konu alanları")
    
    # OpenAlex ve Denormalize Atıf Metadata
    openalex_id: Optional[str] = Field(None, description="OpenAlex üzerindeki Dergi/Source ID'si")
    h_index: Optional[int] = Field(None, description="Derginin H-index değeri")
    i10_index: Optional[int] = Field(None, description="Derginin i10-index değeri (En az 10 atıf alan makale sayısı)")
    average_citation_count: Optional[float] = Field(None, description="Ortalama atıf sayısı (OpenAlex verilerinden)")
    total_citation_count: int = Field(default=0, description="Dergideki makalelerin toplam atıf sayısı")
    historical_citation_data: dict = Field(default_factory=dict, description="Derginin yıllara göre toplam atıf performansı")
    last_citation_update_date: Optional[datetime] = Field(None, description="Atıf metriklerinin son güncellenme tarihi")
    
    class Settings:
        name = "journals"
        indexes = [
            [("name", 1), ("source_website", 1)],  # Compound unique index
            [("publisher", 1)],
            [("source_website", 1)],
            [("open_access", 1)],
        ]
    
    def increment_issue_count(self, count: int = 1):
        """Issue sayısını artır"""
        self.issue_count += count
        self.touch()
    
    def increment_article_count(self, count: int = 1):
        """Makale sayısını artır"""
        self.article_count += count
        self.touch()
    
    def update_counts(self, issue_count: int, article_count: int):
        """Sayıları güncelle"""
        self.issue_count = issue_count
        self.article_count = article_count
        self.touch()
    
    @classmethod
    async def find_by_name_and_source(cls, name: str, source_website: str) -> Optional["Journal"]:
        """İsim ve kaynak siteye göre dergi bul"""
        return await cls.find_one({"name": name, "source_website": source_website})
    
    @classmethod
    async def find_by_source(cls, source_website: str) -> List["Journal"]:
        """Kaynak siteye göre tüm dergileri bul"""
        return await cls.find({"source_website": source_website}).to_list()
    
    @classmethod
    async def get_statistics(cls, source_website: Optional[str] = None) -> dict:
        """İstatistikleri getir"""
        query = {"source_website": source_website} if source_website else {}
        
        pipeline = [
            {"$match": query},
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
            }
        ]
        
        collection = cls.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return results[0] if results else {}
