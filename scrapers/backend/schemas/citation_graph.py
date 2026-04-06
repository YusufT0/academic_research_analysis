"""
Citation Graph API Schemas
Atıf grafiği API yanıt şemaları
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel


class CitationNodeSchema(BaseModel):
    id: str
    title: Optional[str] = None
    doi: Optional[str] = None
    cited_by_count: Optional[int] = None
    publication_year: Optional[int] = None
    is_root: bool = False
    is_internal: bool = False
    internal_article_id: Optional[str] = None
    depth: int = 0


class CitationEdgeSchema(BaseModel):
    source: str   # Cite eden makale (OpenAlex ID)
    target: str   # Cite edilen makale (OpenAlex ID)
    depth: int


class CitationExpandResponse(BaseModel):
    expanded_node_id: str
    node_count: int
    edge_count: int
    nodes: List[CitationNodeSchema]
    edges: List[CitationEdgeSchema]


class CitationGraphResponse(BaseModel):
    root_article_id: str
    root_openalex_id: str
    max_depth: int
    node_count: int
    edge_count: int
    computed_at: str
    nodes: List[CitationNodeSchema]
    edges: List[CitationEdgeSchema]
