"""
Article Schemas
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ArticleFilter(BaseModel):
    """Article filtreleme parametreleri"""
    journal_id: Optional[str] = Field(None, description="Dergi ID'si")
    issue_id: Optional[str] = Field(None, description="Sayı ID'si")
    source_website: Optional[str] = Field(None, description="Kaynak site")
    publication_year: Optional[int] = Field(None, description="Yayın yılı")
    open_access: Optional[bool] = Field(None, description="Açık erişim")
    article_type: Optional[str] = Field(None, description="Makale tipi")
    has_doi: Optional[bool] = Field(None, description="DOI var mı")
    has_abstract: Optional[bool] = Field(None, description="Abstract var mı")
    
    # Sorting
    sort_by: str = Field(default="publication_year", description="Sıralama alanı")
    sort_order: str = Field(default="desc", description="Sıralama yönü")


class ArticleSearchParams(BaseModel):
    """Article arama parametreleri"""
    query: str = Field(..., min_length=2, description="Arama sorgusu")
    search_type: str = Field(
        default="text", 
        description="Arama tipi: text, title, keyword, author"
    )
    limit: int = Field(default=50, ge=1, le=200)


class ArticleResponse(BaseModel):
    """Article response schema"""
    id: str = Field(..., description="MongoDB ID")
    journal_id: str
    journal_name: str
    issue_id: str
    issue_number: Optional[str] = None
    source_website: str
    
    title: str
    url: str
    doi: Optional[str] = None
    
    abstract: Optional[str] = None
    introduction: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    
    publication_date: Optional[str] = None
    publication_year: Optional[int] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    
    article_type: Optional[str] = None
    open_access: bool = False
    
    pdf_url: Optional[str] = None
    citation_count: int = 0
    references: List[str] = Field(default_factory=list)
    
    # OpenAlex ve Atıf Alanları
    openalex_id: Optional[str] = None
    is_openalex_indexed: bool = False
    historical_citation_data: dict = Field(default_factory=dict)
    citation_percentile: Optional[float] = None
    fwci: Optional[float] = None
    last_citation_update_date: Optional[datetime] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ArticleListResponse(BaseModel):
    """Article listesi response"""
    items: List[ArticleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class ArticleStatsResponse(BaseModel):
    """Article istatistikleri"""
    total_articles: int
    by_source: dict
    by_year: dict
    with_abstract: int
    with_doi: int
    open_access_count: int
    top_keywords: List[dict]
    top_authors: List[dict]

class ArticleCitationMetricsResponse(BaseModel):
    """Makale Atıf ve Etki Metrikleri Response"""
    id: str
    doi: Optional[str] = None
    citation_count: int = 0
    openalex_id: Optional[str] = None
    is_openalex_indexed: bool = False
    historical_citation_data: dict = Field(default_factory=dict, description="Yıllara göre atıf sayıları {2023: 10}")
    citation_percentile: Optional[float] = None
    fwci: Optional[float] = None
    last_citation_update_date: Optional[datetime] = None
    
    class Config:
        from_attributes = True
