"""
AnalysisRun Repository
Analiz çalıştırma kayıtları için CRUD operasyonları
"""

from datetime import datetime
from typing import Optional, List
from beanie import PydanticObjectId

from .base import BaseRepository
from ..models import AnalysisRun


class AnalysisRunRepository(BaseRepository[AnalysisRun]):
    """
    AnalysisRun Repository
    
    Analiz çalıştırma kayıtları için CRUD ve özel sorgular
    """
    
    def __init__(self):
        super().__init__(AnalysisRun)
    
    async def find_by_model_version(
        self, 
        model_version: str
    ) -> Optional[AnalysisRun]:
        """Model versiyonuna göre analiz kaydı bul"""
        return await AnalysisRun.find_one({"model_version": model_version})
    
    async def get_latest(self) -> Optional[AnalysisRun]:
        """En son analiz kaydını getir"""
        return await AnalysisRun.find_one(
            sort=[("created_at", -1)]
        )
    
    async def get_latest_completed(self) -> Optional[AnalysisRun]:
        """En son tamamlanan analiz kaydını getir"""
        return await AnalysisRun.find_one(
            {"status": "completed"},
            sort=[("completed_at", -1)]
        )
    
    async def get_running(self) -> Optional[AnalysisRun]:
        """Çalışan analiz kaydını getir"""
        return await AnalysisRun.find_one({"status": "running"})
    
    async def create_run(
        self,
        model_version: str,
        embedder_model: str = "all-MiniLM-L6-v2",
        umap_n_neighbors: int = 15,
        umap_n_components: int = 10,
        min_cluster_size: int = 20,
        min_samples: int = 1
    ) -> AnalysisRun:
        """Yeni analiz kaydı oluştur"""
        run = AnalysisRun(
            model_version=model_version,
            embedder_model=embedder_model,
            umap_n_neighbors=umap_n_neighbors,
            umap_n_components=umap_n_components,
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            status="pending"
        )
        await run.insert()
        return run
    
    async def start_run(self, run: AnalysisRun) -> AnalysisRun:
        """Analiz çalıştırmasını başlat"""
        run.status = "running"
        run.started_at = datetime.utcnow()
        await run.save()
        return run
    
    async def complete_run(
        self,
        run: AnalysisRun,
        total_articles: int,
        total_clusters: int,
        noise_count: int
    ) -> AnalysisRun:
        """Analiz çalıştırmasını tamamla"""
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.total_articles = total_articles
        run.total_clusters = total_clusters
        run.noise_count = noise_count
        await run.save()
        return run
    
    async def fail_run(
        self,
        run: AnalysisRun,
        error_message: str
    ) -> AnalysisRun:
        """Analiz çalıştırmasını başarısız olarak işaretle"""
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = error_message
        await run.save()
        return run
    
    async def get_history(
        self,
        limit: int = 10,
        status: Optional[str] = None
    ) -> List[AnalysisRun]:
        """Analiz geçmişini getir"""
        query = {}
        if status:
            query["status"] = status
        return await AnalysisRun.find(query).sort("-created_at").limit(limit).to_list()
    
    async def delete_by_model_version(self, model_version: str) -> bool:
        """Model versiyonuna göre analiz kaydını sil"""
        run = await self.find_by_model_version(model_version)
        if run:
            await run.delete()
            return True
        return False
