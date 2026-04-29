"""
Cluster Repository
Cluster CRUD operasyonları
"""

from typing import Optional, List
from beanie import PydanticObjectId

from .base import BaseRepository
from ..models import Cluster


class ClusterRepository(BaseRepository[Cluster]):
    """
    Cluster Repository
    
    Cluster koleksiyonu için CRUD ve özel sorgular
    """
    
    def __init__(self):
        super().__init__(Cluster)
    
    async def find_by_cluster_id(
        self, 
        cluster_id: int,
        model_version: str
    ) -> Optional[Cluster]:
        """Cluster ID ve model versiyonuna göre cluster bul"""
        return await Cluster.find_one({
            "cluster_id": cluster_id,
            "model_version": model_version
        })
    
    async def find_by_model_version(
        self, 
        model_version: str,
        include_noise: bool = False
    ) -> List[Cluster]:
        """Model versiyonuna göre tüm cluster'ları getir"""
        query = {"model_version": model_version}
        if not include_noise:
            query["cluster_id"] = {"$ne": -1}
        print("TRYING TO FIND")
        return await Cluster.find(query).to_list()

    async def find_by_model_version_on_all(
        self, 
        model_version: str,
        include_noise: bool = False
    ) -> List[Cluster]:
        """Model versiyonuna göre tüm cluster'ları getir"""
        query = {"model_version": model_version, "cluster_type" : "all"}
        if not include_noise:
            query["cluster_id"] = {"$ne": -1}
        print("TRYING TO FIND")
        return await Cluster.find(query).to_list()


    async def find_cluster_by_article(
        self, 
        article_id: PydanticObjectId,
        model_version: Optional[str] = None
    ) -> Optional[Cluster]:
        """Bir makalenin ait olduğu cluster'ı bul"""
        query = {"article_ids": article_id}
        if model_version:
            query["model_version"] = model_version
        return await Cluster.find_one(query)
    
    async def get_cluster_articles(
        self, 
        cluster_id: int,
        model_version: str
    ) -> List[PydanticObjectId]:
        """Cluster'daki tüm makale ID'lerini getir"""
        cluster = await self.find_by_cluster_id(cluster_id, model_version)
        return cluster.article_ids if cluster else []
    
    async def bulk_create(self, clusters: List[Cluster]) -> List[Cluster]:
        """Toplu cluster oluştur"""
        if clusters:
            await Cluster.insert_many(clusters)
        return clusters
    
    async def delete_by_model_version(self, model_version: str) -> int:
        """Model versiyonuna göre tüm cluster'ları sil"""
        result = await Cluster.find(
            {"model_version": model_version}
        ).delete()
        return result.deleted_count if result else 0
    
    async def count_by_model_version(
        self, 
        model_version: str,
        include_noise: bool = False
    ) -> int:
        """Model versiyonuna göre cluster sayısı"""
        query = {"model_version": model_version}
        if not include_noise:
            query["cluster_id"] = {"$ne": -1}
        return await Cluster.find(query).count()
    
    async def get_cluster_summary(
        self, 
        model_version: str
    ) -> List[dict]:
        """Cluster özet bilgilerini getir"""
        clusters = await self.find_by_model_version(model_version, include_noise=False)
        return [
            {
                "cluster_id": c.cluster_id,
                "label": c.label,
                "article_count": c.article_count,
                "top_keywords": c.top_keywords[:5],
                "sample_titles": c.sample_titles[:3],
            }
            for c in clusters
        ]
    
    async def add_article_to_cluster(
        self,
        cluster_id: int,
        model_version: str,
        article_id: PydanticObjectId
    ) -> bool:
        """Cluster'a makale ekle"""
        cluster = await self.find_by_cluster_id(cluster_id, model_version)
        if cluster and article_id not in cluster.article_ids:
            cluster.article_ids.append(article_id)
            cluster.article_count = len(cluster.article_ids)
            await cluster.save()
            return True
        return False
    
    async def get_largest_clusters(
        self,
        model_version: str,
        limit: int = 10
    ) -> List[Cluster]:
        """En büyük cluster'ları getir"""
        return await Cluster.find(
            {"model_version": model_version, "cluster_id": {"$ne": -1}}
        ).sort("-article_count").limit(limit).to_list()
