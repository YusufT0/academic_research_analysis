"""
Issue Schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class IssueFilter(BaseModel):
    """Issue filtreleme parametreleri"""
    journal_id: Optional[str] = Field(None, description="Dergi ID'si")
    journal_name: Optional[str] = Field(None, description="Dergi adı")
    source_website: Optional[str] = Field(None, description="Kaynak site")
    year: Optional[int] = Field(None, description="Yayın yılı")
    status: Optional[str] = Field(None, description="Durum")
    
    # Sorting
    sort_by: str = Field(default="year", description="Sıralama alanı")
    sort_order: str = Field(default="desc", description="Sıralama yönü")


class IssueResponse(BaseModel):
    """Issue response schema"""
    id: str = Field(..., description="MongoDB ID")
    journal_id: str = Field(..., description="Dergi ID'si")
    journal_name: str = Field(..., description="Dergi adı")
    source_website: str = Field(..., description="Kaynak site")
    
    issue_number: Optional[str] = Field(None, description="Sayı numarası")
    volume: Optional[str] = None
    number: Optional[str] = None
    
    date: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    
    url: Optional[str] = None
    status: Optional[str] = None
    
    article_count: int = Field(default=0)
    pages: Optional[str] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class IssueListResponse(BaseModel):
    """Issue listesi response"""
    items: List[IssueResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
