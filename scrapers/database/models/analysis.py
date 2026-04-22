"""
Database Models - Analysis
NLP ve Clustering analiz sonuçları için modeller
"""

from datetime import datetime
from typing import Optional, List, Any
from beanie import Document, PydanticObjectId
from pydantic import Field, field_validator

from .base import TimestampMixin


class ArticleEmbedding(Document, TimestampMixin):
    """
    Makale Embedding Modeli
    
    Her makale için embedding vektörünü ve temizlenmiş metni tutar.
    Article koleksiyonundan bağımsız, article_id ile referans verir.
    """
    
    article_id: PydanticObjectId = Field(..., description="İlgili makale ID'si")
    
    # Embedding vektörleri
    embedding_full: List[float] = Field(
        ..., 
        description="SentenceTransformer embedding vektörü (384-dim for all-MiniLM-L6-v2)"
    )
    embedding_reduced: List[float] = Field(
        ..., 
        description="UMAP ile indirgenmiş embedding vektörü"
    )
    
    # Preprocessing sonucu
    text_cleaned: str = Field(..., description="NLP için temizlenmiş abstract metni")
    
    # Metadata
    model_version: str = Field(..., description="Kullanılan model versiyonu")
    
    article_keywords : List[str] = Field(
        ...,
        description="Makaleye ait anahtar kelimeler."
    )
    article_dates : str = Field(
        ...,
        description="Date Published."
    )
    article_publisher : str = Field(
       None,
       description = "Publisher of the article." 
    )
    article_journal_id: PydanticObjectId = Field(
        None,
        description="Journal ID."
    )
 
    class Settings:
        # name = "article_embeddings_sample"
        name = "article_embeddings"
        indexes = [
            [("article_id", 1)],
            [("model_version", 1)],
            [("article_id", 1), ("model_version", 1)],
        ]


class Cluster(Document, TimestampMixin):
    """
    Cluster Modeli
    
    Her cluster için centroid vektörü, üye makaleler ve metadata tutar.
    Article'lar cluster'lardan habersiz, cluster'lar article'ları bilir.
    """
    
    cluster_id: int = Field(..., description="HDBSCAN cluster ID'si (-1 = noise)")
    
    # Centroid vektörleri - hızlı similarity araması için
    centroid_full: List[float] = Field(
        ..., 
        description="Cluster merkez vektörü (full embedding boyutu)"
    )
    centroid_reduced: List[float] = Field(
        ..., 
        description="İndirgenmiş centroid vektörü"
    )
    
    # Cluster'a ait makaleler (ana ilişki!)
    article_ids: List[PydanticObjectId] = Field(
        default_factory=list, 
        description="Bu cluster'a ait makale ID'leri"
    )
    
    # Cluster özellikleri
    label: Optional[str] = Field(
        None, 
        description="Cluster'ın otomatik oluşturulan etiketi"
    )
    top_keywords: List[str] = Field(
        default_factory=list, 
        description="En sık geçen anahtar kelimeler"
    )
    sample_titles: List[str] = Field(
        default_factory=list, 
        description="Örnek makale başlıkları (max 5)"
    )

    cluster_type: str = Field(
        ...,
        description="Yapılan clusterlamanin tipi."
    )
    group_id: Optional[str] = Field(
        default=None,
        description="Cluster'ın kaynak publisher'ı ya da journal'ı. ALL seçildiyse None."
    )

    @field_validator("group_id", mode="before")
    @classmethod
    def coerce_group_id(cls, v: Any) -> Optional[str]:
        """DB'de ObjectId olarak kaydedilmiş group_id'leri string'e çevirir."""
        if v is None:
            return None
        return str(v)
    # İstatistikler
    article_count: int = Field(default=0, description="Cluster'daki makale sayısı")
    avg_similarity: Optional[float] = Field(
        None, 
        description="Cluster içi ortalama benzerlik skoru"
    )
    
    # Model bilgisi
    model_version: str = Field(..., description="Clustering model versiyonu")
    
    class Settings:
        # name = "clusters_sample"
        name = "clusters"
        indexes = [
            [("cluster_id", 1), ("model_version", 1)],
            [("article_ids", 1)],
            [("model_version", 1)],
        ]


class AnalysisRun(Document, TimestampMixin):
    """
    Analiz Çalıştırma Kaydı
    
    Her clustering işlemi için parametreler ve istatistikleri tutar.
    Model versiyonlama ve geçmiş takibi sağlar.
    """
    
    model_version: str = Field(..., description="Bu çalıştırmanın versiyon ID'si")
    
    # Model parametreleri
    embedder_model: str = Field(default="all-MiniLM-L6-v2", description="Embedding modeli")
    umap_n_neighbors: int = Field(default=15, description="UMAP n_neighbors parametresi")
    umap_n_components: int = Field(default=10, description="UMAP çıktı boyutu")
    min_cluster_size: int = Field(default=20, description="HDBSCAN min_cluster_size")
    min_samples: int = Field(default=1, description="HDBSCAN min_samples")
    
    # İstatistikler
    total_articles: int = Field(default=0, description="İşlenen toplam makale sayısı")
    total_clusters: int = Field(default=0, description="Oluşan cluster sayısı (noise hariç)")
    noise_count: int = Field(default=0, description="Noise olarak işaretlenen makale sayısı")
    
    # Durum
    status: str = Field(
        default="pending", 
        description="Çalıştırma durumu: pending, running, completed, failed"
    )
    error_message: Optional[str] = Field(None, description="Hata mesajı (varsa)")
    
    # Zaman bilgileri
    started_at: Optional[datetime] = Field(None, description="Başlangıç zamanı")
    completed_at: Optional[datetime] = Field(None, description="Bitiş zamanı")
    
    class Settings:
        name = "analysis_runs"
        indexes = [
            [("model_version", 1)],
            [("status", 1)],
            [("created_at", -1)],
        ]
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Çalışma süresi (saniye)"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
