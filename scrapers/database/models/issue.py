"""
Database Models - Issue
Dergi sayısı/cildi modeli
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, Annotated
from beanie import Document, Indexed, Link, PydanticObjectId
from pydantic import Field

from .base import TimestampMixin

if TYPE_CHECKING:
    from .journal import Journal


class Issue(Document, TimestampMixin):
    """
    Dergi Sayısı/Cildi Modeli
    
    Her issue bir Journal'a bağlıdır.
    """
    
    # İlişki
    journal_id: Annotated[PydanticObjectId, Indexed()] = Field(..., description="Bağlı olduğu dergi ID'si")
    journal_name: str = Field(..., description="Dergi adı (denormalize)")
    source_website: Annotated[str, Indexed()] = Field(..., description="Kaynak site")
    
    # Sayı bilgileri
    issue_number: Optional[str] = Field(None, description="Sayı numarası: Volume 13, Issue 5")
    volume: Optional[str] = Field(None, description="Cilt numarası")
    number: Optional[str] = Field(None, description="Sayı numarası")
    
    # Tarih bilgileri
    date: Optional[str] = Field(None, description="Yayın tarihi string: 2025, 2025-10, January 2025")
    year: Optional[int] = Field(None, description="Yayın yılı")
    month: Optional[int] = Field(None, description="Yayın ayı")
    
    # URL ve durum
    url: Optional[str] = Field(None, description="Issue sayfası URL'si")
    status: Optional[str] = Field(None, description="Durum: In progress, Published")
    
    # İstatistikler
    article_count: int = Field(default=0, description="Bu sayıdaki makale sayısı")
    pages: Optional[str] = Field(None, description="Sayfa aralığı: 1-164")
    
    # Scraping metadata
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "issues"
        indexes = [
            [("journal_id", 1)],
            [("journal_id", 1), ("issue_number", 1)],  # Compound index
            [("source_website", 1)],
            [("year", -1)],
        ]
    
    def increment_article_count(self, count: int = 1):
        """Makale sayısını artır"""
        self.article_count += count
        self.touch()
    
    def parse_date(self):
        """Date stringinden year ve month çıkar"""
        if self.date:
            import re
            # Yıl çıkarma
            year_match = re.search(r'(\d{4})', self.date)
            if year_match:
                self.year = int(year_match.group(1))
            
            # Ay çıkarma (2025-10 formatı)
            month_match = re.search(r'\d{4}-(\d{2})', self.date)
            if month_match:
                self.month = int(month_match.group(1))
    
    @classmethod
    async def find_by_journal(cls, journal_id: PydanticObjectId) -> List["Issue"]:
        """Dergiye göre tüm sayıları bul"""
        return await cls.find({"journal_id": journal_id}).sort("-year", "-month").to_list()
    
    @classmethod
    async def find_by_journal_and_number(
        cls, 
        journal_id: PydanticObjectId, 
        issue_number: str
    ) -> Optional["Issue"]:
        """Dergi ve sayı numarasına göre bul"""
        return await cls.find_one({
            "journal_id": journal_id, 
            "issue_number": issue_number
        })
    
    @classmethod
    async def find_latest_by_journal(cls, journal_id: PydanticObjectId) -> Optional["Issue"]:
        """Derginin en son sayısını bul"""
        issues = await cls.find({"journal_id": journal_id}).sort("-year", "-month").limit(1).to_list()
        return issues[0] if issues else None
    
    @classmethod
    async def get_count_by_journal(cls, journal_id: PydanticObjectId) -> int:
        """Derginin sayı adedini getir"""
        return await cls.find({"journal_id": journal_id}).count()
