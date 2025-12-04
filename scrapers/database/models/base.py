"""
Database Models - Base
Tüm modellerin paylaştığı ortak yapılar
"""

from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import BaseModel, Field


class TimestampMixin(BaseModel):
    """Timestamp alanları için mixin"""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def touch(self):
        """updated_at alanını güncelle"""
        self.updated_at = datetime.utcnow()


class ScrapingMetaMixin(BaseModel):
    """Scraping metadata için mixin"""
    source_website: str = Field(..., description="Kaynak site: ieeexplore, sciencedirect")
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    last_scraped_at: Optional[datetime] = None
    scrape_count: int = Field(default=1, description="Kaç kez tarandığı")
    
    def mark_scraped(self):
        """Scraping işlemini işaretle"""
        self.last_scraped_at = datetime.utcnow()
        self.scrape_count += 1
