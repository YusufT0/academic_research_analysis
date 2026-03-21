"""
Backend Configuration
"""

from typing import Optional, List
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# .env dosyasının yolu
ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Backend ayarları"""
    
    # API Settings
    app_name: str = Field(default="Academic Research Scraper API")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    
    # CORS
    cors_origins: List[str] = Field(default=["*"])
    
    # MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="academic_research")
    mongodb_username: Optional[str] = Field(default=None)
    mongodb_password: Optional[str] = Field(default=None)
    
    # Scraper Settings
    auto_start_scrapers: bool = Field(default=True, alias="AUTO_START_SCRAPERS", description="Backend başladığında scraper'ları otomatik başlat")
    scraper_headless: bool = Field(default=True, alias="SCRAPER_HEADLESS", description="Browser headless modda çalışsın mı")
    ieee_max_articles: int = Field(default=100, alias="IEEE_MAX_ARTICLES", description="IEEE scraper maksimum makale sayısı")
    sciencedirect_max_articles: int = Field(default=100, alias="SCIENCEDIRECT_MAX_ARTICLES", description="ScienceDirect scraper maksimum makale sayısı")
    enabled_scrapers: str = Field(default="ieee,sciencedirect", alias="ENABLED_SCRAPERS", description="Çalışacak scraper'lar (virgülle ayrılmış): ieee, sciencedirect")
    scraper_run_mode: str = Field(default="parallel", alias="SCRAPER_RUN_MODE", description="Scraper çalışma modu: 'parallel', 'sequential' veya 'round_robin'")
    round_robin_journals_per_switch: int = Field(default=3, alias="ROUND_ROBIN_JOURNALS_PER_SWITCH", description="Round robin modunda kaç journalda bir site değiştirileceği")
    
    @property
    def ieee_enabled(self) -> bool:
        """IEEE scraper etkin mi?"""
        return 'ieee' in self.enabled_scrapers.lower()
    
    @property
    def sciencedirect_enabled(self) -> bool:
        """ScienceDirect scraper etkin mi?"""
        return 'sciencedirect' in self.enabled_scrapers.lower()
    
    # Rate Limiting
    scrape_delay_min: float = Field(default=2.0, description="Minimum bekleme süresi (saniye)")
    scrape_delay_max: float = Field(default=5.0, description="Maksimum bekleme süresi (saniye)")
    
    # NLP/Clustering Settings
    # nlp_prefer_pkl: bool = Field(
    #     default=True,
    #     alias="NLP_PREFER_PKL",
    #     description="True: Önce PKL kullan, False: Önce DB kullan"
    # )
    # nlp_model_path: str = Field(
    #     default="analyzer/clustering_model_.pkl", 
    #     alias="NLP_MODEL_PATH",
    #     description="Clustering model dosya yolu"
    # )
    nlp_model_version: str = Field(
        default="v1.0", 
        alias="NLP_MODEL_VERSION",
        description="Model versiyonu"
    )
    nlp_embedder_model: str = Field(
        # default="all-MiniLM-L6-v2", 
        default= "allenai/aspire-sentence-embedder",
        alias="NLP_EMBEDDER_MODEL",
        description="SentenceTransformer model adı"
    )
    nlp_umap_n_neighbors: int = Field(
        default=15, 
        alias="NLP_UMAP_N_NEIGHBORS",
        description="UMAP n_neighbors parametresi"
    )
    nlp_umap_n_components: int = Field(
        default=15, 
        alias="NLP_UMAP_N_COMPONENTS",
        description="UMAP çıktı boyutu"
    )
    nlp_min_cluster_size: int = Field(
        default=20, 
        alias="NLP_MIN_CLUSTER_SIZE",
        description="HDBSCAN min_cluster_size"
    )
    nlp_min_samples: int = Field(
        default=1, 
        alias="NLP_MIN_SAMPLES",
        description="HDBSCAN min_samples"
    )
    
    # Redis Cache Settings
    redis_enabled: bool = Field(
        default=True,
        alias="REDIS_ENABLED",
        description="Redis cache aktif mi"
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
        description="Redis bağlantı URL'i"
    )
    redis_prefix: str = Field(
        default="academic",
        alias="REDIS_PREFIX",
        description="Redis key prefix'i"
    )
    
    # Cache TTL Settings (saniye)
    cache_ttl_article: int = Field(
        default=3600,  # 1 saat
        alias="CACHE_TTL_ARTICLE",
        description="Article cache TTL (saniye)"
    )
    cache_ttl_journal: int = Field(
        default=21600,  # 6 saat
        alias="CACHE_TTL_JOURNAL",
        description="Journal cache TTL (saniye)"
    )
    cache_ttl_issue: int = Field(
        default=7200,  # 2 saat
        alias="CACHE_TTL_ISSUE",
        description="Issue cache TTL (saniye)"
    )
    cache_ttl_cluster: int = Field(
        default=1800,  # 30 dakika
        alias="CACHE_TTL_CLUSTER",
        description="Cluster cache TTL (saniye)"
    )
    cache_ttl_search: int = Field(
        default=900,  # 15 dakika
        alias="CACHE_TTL_SEARCH",
        description="Search results cache TTL (saniye)"
    )
    cache_ttl_stats: int = Field(
        default=300,  # 5 dakika
        alias="CACHE_TTL_STATS",
        description="Stats cache TTL (saniye)"
    )
    
    # Prefetch Settings
    prefetch_enabled: bool = Field(
        default=True,
        alias="PREFETCH_ENABLED",
        description="Akıllı prefetch aktif mi"
    )
    prefetch_articles_per_issue: int = Field(
        default=20,
        alias="PREFETCH_ARTICLES_PER_ISSUE",
        description="Issue görüntülenince kaç makale prefetch edilsin"
    )
    prefetch_issues_per_journal: int = Field(
        default=20,
        alias="PREFETCH_ISSUES_PER_JOURNAL",
        description="Journal görüntülenince kaç issue prefetch edilsin"
    )
    prefetch_articles_per_cluster: int = Field(
        default=50,
        alias="PREFETCH_ARTICLES_PER_CLUSTER",
        description="Cluster arama/görüntülemede kaç makale prefetch edilsin"
    )
    prefetch_neighbor_clusters: int = Field(
        default=2,
        alias="PREFETCH_NEIGHBOR_CLUSTERS",
        description="Cluster görüntülemede kaç komşu cluster prefetch edilsin (±)"
    )
    prefetch_neighbor_issues: int = Field(
        default=2,
        alias="PREFETCH_NEIGHBOR_ISSUES",
        description="Issue görüntülemede kaç komşu issue prefetch edilsin (±)"
    )
    prefetch_neighbor_articles_limit: int = Field(
        default=30,
        alias="PREFETCH_NEIGHBOR_ARTICLES_LIMIT",
        description="Komşu cluster için kaç makale prefetch edilsin"
    )
    
    # ==================== Elasticsearch ====================
    elasticsearch_url: str = Field(
        default="http://localhost:9200",
        alias="ELASTICSEARCH_URL",
        description="Elasticsearch URL"
    )
    elasticsearch_index_prefix: str = Field(
        default="academic",
        alias="ELASTICSEARCH_INDEX_PREFIX",
        description="Elasticsearch index prefix"
    )
    
    # ==================== Redis Streams ====================
    redis_streams_enabled: bool = Field(
        default=True,
        alias="REDIS_STREAMS_ENABLED",
        description="Redis Streams event pipeline aktif mi"
    )
    redis_streams_consumer_group: str = Field(
        default="academic-backend",
        alias="REDIS_STREAMS_CONSUMER_GROUP",
        description="Consumer group adı"
    )
    redis_streams_dlq_retry_interval: int = Field(
        default=300,
        alias="REDIS_STREAMS_DLQ_RETRY_INTERVAL",
        description="DLQ retry aralığı (saniye)"
    )
    
    # ==================== Logging ====================
    log_format: str = Field(
        default="pretty",
        alias="LOG_FORMAT",
        description="Log format: json (production) veya pretty (dev)"
    )
    
    @property
    def nlp_model_full_path(self) -> Path:
        """NLP model tam yolu"""
        model_path = Path(self.nlp_model_path)
        if model_path.is_absolute():
            return model_path
        return Path(__file__).parent.parent.parent / model_path
    
    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"
        populate_by_name = True  # Hem field name hem alias ile populate et


# Singleton
settings = Settings()
