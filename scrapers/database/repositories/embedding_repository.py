"""
Embedding Repository
ArticleEmbedding CRUD operasyonları
"""

from typing import Optional, List
from beanie import PydanticObjectId

from .base import BaseRepository
from ..models import ArticleEmbedding


class EmbeddingRepository(BaseRepository[ArticleEmbedding]):
    """
    Embedding Repository
    
    ArticleEmbedding koleksiyonu için CRUD ve özel sorgular
    """
    
    def __init__(self):
        super().__init__(ArticleEmbedding)
    
    async def find_by_article_id(
        self, 
        article_id: PydanticObjectId,
        model_version: Optional[str] = None
    ) -> Optional[ArticleEmbedding]:
        """Article ID'ye göre embedding bul"""
        query = {"article_id": article_id}
        if model_version:
            query["model_version"] = model_version
        return await ArticleEmbedding.find_one(query)
    
    async def find_many_by_article_ids(
    self, 
    article_ids: List[PydanticObjectId],
    model_version: Optional[str] = None
    ) -> List[ArticleEmbedding]:
        query = {"article_id": {"$in": article_ids}}
        
        if model_version:
            query["model_version"] = model_version
        return await ArticleEmbedding.find(query).to_list()
    
    async def find_by_model_version(
        self, 
        model_version: str,
        limit: int = 1000
    ) -> List[ArticleEmbedding]:
        """Model versiyonuna göre tüm embedding'leri getir"""
        return await ArticleEmbedding.find(
            {"model_version": model_version}
        ).limit(limit).to_list()
    
    async def bulk_create(
        self, 
        embeddings: List[ArticleEmbedding]
    ) -> List[ArticleEmbedding]:
        """Toplu embedding oluştur"""
        if embeddings:
            await ArticleEmbedding.insert_many(embeddings)
        return embeddings
    
    async def delete_by_model_version(self, model_version: str) -> int:
        """Model versiyonuna göre tüm embedding'leri sil"""
        result = await ArticleEmbedding.find(
            {"model_version": model_version}
        ).delete()
        return result.deleted_count if result else 0
    
    async def count_by_model_version(self, model_version: str) -> int:
        """Model versiyonuna göre embedding sayısı"""
        return await ArticleEmbedding.find(
            {"model_version": model_version}
        ).count()
    
    async def get_article_ids_by_model_version(
        self, 
        model_version: str
    ) -> List[PydanticObjectId]:
        """Model versiyonuna göre işlenmiş article ID'lerini getir"""
        embeddings = await ArticleEmbedding.find(
            {"model_version": model_version},
            projection_model=None
        ).to_list()
        return [e.article_id for e in embeddings]
    
    async def exists_for_article(
        self,
        article_id: PydanticObjectId,
        model_version: Optional[str] = None
    ) -> bool:
        """Article için embedding var mı?"""
        query = {"article_id": article_id}
        if model_version:
            query["model_version"] = model_version
        return await ArticleEmbedding.find_one(query) is not None

    async def delete_by_article_ids(self, article_ids: List[PydanticObjectId]) -> int:
        """Verilen makale ID'lerine ait tüm embedding'leri sil"""
        if not article_ids:
            return 0
        result = await ArticleEmbedding.find({"article_id": {"$in": article_ids}}).delete()
        return result.deleted_count if result else 0
