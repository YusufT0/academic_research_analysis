"""
Journal Schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class JournalFilter(BaseModel):
    """Journal filtreleme parametreleri"""
    source_website: Optional[str] = Field(None, description="Kaynak site: ieeexplore, sciencedirect")
    publisher: Optional[str] = Field(None, description="Yayıncı")
    open_access: Optional[bool] = Field(None, description="Açık erişim mi")
    letter_group: Optional[str] = Field(None, description="Alfabetik grup (A, B, C...)")
    search: Optional[str] = Field(None, description="İsim araması")
    
    # Sorting
    sort_by: str = Field(default="name", description="Sıralama alanı")
    sort_order: str = Field(default="asc", description="Sıralama yönü: asc, desc")


class JournalResponse(BaseModel):
    """Journal response schema"""
    id: str = Field(..., description="MongoDB ID")
    name: str = Field(..., description="Dergi adı")
    url: Optional[str] = Field(None, description="Dergi URL'si")
    source_website: str = Field(..., description="Kaynak site")
    
    type: str = Field(default="Journal", description="Yayın tipi")
    open_access: bool = Field(default=False, description="Açık erişim")
    letter_group: Optional[str] = Field(None, description="Alfabetik grup")
    publisher: Optional[str] = Field(None, description="Yayıncı")
    
    issue_count: int = Field(default=0, description="Sayı adedi")
    article_count: int = Field(default=0, description="Makale adedi")
    
    issn: Optional[str] = None
    eissn: Optional[str] = None
    impact_factor: Optional[float] = None
    subjects: List[str] = Field(default_factory=list)
    
    openalex_id: Optional[str] = None
    h_index: Optional[int] = None
    i10_index: Optional[int] = None
    average_citation_count: Optional[float] = None
    total_citation_count: int = 0
    historical_citation_data: dict = Field(default_factory=dict)
    last_citation_update_date: Optional[datetime] = None
    aims_and_scope: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JournalListResponse(BaseModel):
    """Journal listesi response"""
    items: List[JournalResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class JournalStatsResponse(BaseModel):
    """Journal istatistikleri"""
    total_journals: int
    by_source: dict
    by_publisher: dict
    open_access_count: int

class JournalCitationMetricsResponse(BaseModel):
    """Dergi Atıf ve Etki Metrikleri Response"""
    id: str
    name: str
    openalex_id: Optional[str] = None
    h_index: Optional[int] = None
    i10_index: Optional[int] = None
    average_citation_count: Optional[float] = None
    total_citation_count: int = 0
    historical_citation_data: dict = Field(default_factory=dict, description="Yıllara göre atıf sayıları {2023: 10}")
    last_citation_update_date: Optional[datetime] = None
    
    class Config:
        from_attributes = True
