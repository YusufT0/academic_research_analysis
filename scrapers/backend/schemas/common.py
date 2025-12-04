"""
Common Schemas - Pagination, Sorting, etc.
"""

from typing import TypeVar, Generic, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class SortOrder(str, Enum):
    """Sıralama yönü"""
    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    """Sayfalama parametreleri"""
    page: int = Field(default=1, ge=1, description="Sayfa numarası")
    page_size: int = Field(default=20, ge=1, le=100, description="Sayfa başına kayıt")
    
    @property
    def skip(self) -> int:
        """MongoDB skip değeri"""
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        """MongoDB limit değeri"""
        return self.page_size


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Sayfalanmış response"""
    items: List[T] = Field(..., description="Kayıtlar")
    total: int = Field(..., description="Toplam kayıt sayısı")
    page: int = Field(..., description="Mevcut sayfa")
    page_size: int = Field(..., description="Sayfa başına kayıt")
    total_pages: int = Field(..., description="Toplam sayfa sayısı")
    has_next: bool = Field(..., description="Sonraki sayfa var mı")
    has_prev: bool = Field(..., description="Önceki sayfa var mı")
    
    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int):
        """Helper method to create paginated response"""
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class MessageResponse(BaseModel):
    """Basit mesaj response"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Hata response"""
    error: str
    detail: Optional[str] = None
    success: bool = False
