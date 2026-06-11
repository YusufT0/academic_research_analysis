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
    app_name: str = Field(default="Academic Research Scraper API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    app_description: str = Field(default="Academic Research Scraper API Documentation", alias="APP_DESCRIPTION")
    debug: bool = Field(default=False, alias="DEBUG")
    
    # CORS
    cors_origins: List[str] = Field(default=["*"], alias="CORS_ORIGINS")
    
    # Proxy Settings
    use_proxy: bool = Field(default=False, alias="USE_PROXY", description="Proxy kullanılsın mı")
    proxy_user: str = Field(default="", env="proxy_user", alias="proxy_user", description="Proxy username")
    proxy_pass: str = Field(default="", env="proxy_pass", alias="proxy_pass", description="Proxy password")
    proxy_host: str = Field(default="", env="proxy_host", alias="proxy_host", description="Proxy host or IP")
    proxy_port: str = Field(default="8080", env="proxy_port", alias="proxy_port", description="Proxy port")
    
    # MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="academic_research")
    mongodb_username: Optional[str] = Field(default=None)
    mongodb_password: Optional[str] = Field(default=None)
    
    # Scraper Settings
    auto_start_scrapers: bool = Field(default=False, alias="AUTO_START_SCRAPERS")
    scraper_lazy_load: bool = Field(default=True, alias="SCRAPER_LAZY_LOAD", description="Scraper modülleri başlangıçta değil ilk kullanımda yüklensin mi")
    run_tests_on_startup: bool = Field(default=False, alias="RUN_TESTS_ON_STARTUP", description="Backend başlarken testler çalıştırılsın mı")
    scraper_headless: bool = Field(default=True, alias="SCRAPER_HEADLESS", description="Browser headless modda çalışsın mı")
    ieee_max_articles: int = Field(default=100, alias="IEEE_MAX_ARTICLES", description="IEEE scraper maksimum makale sayısı")
    ieee_depth: int = Field(default=1, alias="IEEE_DEPTH", description="IEEE scraper kaç yeni issue işlenecek (1=sadece en yeni, 0/None=tümü)")
    sciencedirect_max_articles: int = Field(default=100, alias="SCIENCEDIRECT_MAX_ARTICLES", description="ScienceDirect scraper maksimum makale sayısı")
    acm_max_articles: int = Field(default=100, alias="ACM_MAX_ARTICLES", description="ACM scraper maksimum makale sayısı")
    enabled_scrapers: str = Field(default="ieee,sciencedirect", alias="ENABLED_SCRAPERS", description="Çalışacak scraper'lar (virgülle ayrılmış): ieee, sciencedirect, acm, wiley, springer")
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
    
    @property
    def acm_enabled(self) -> bool:
        """ACM scraper etkin mi?"""
        return 'acm' in self.enabled_scrapers.lower()

    @property
    def wiley_enabled(self) -> bool:
        """Wiley scraper etkin mi?"""
        return 'wiley' in self.enabled_scrapers.lower()

    @property
    def springer_enabled(self) -> bool:
        """Springer scraper etkin mi?"""
        return 'springer' in self.enabled_scrapers.lower()
    
    # Scraper Base URLs
    ieeexplore_base_url: str = Field(default="https://ieeexplore.ieee.org", alias="IEEEXPLORE_BASE_URL", description="IEEE Xplore base URL")
    sciencedirect_base_url: str = Field(default="https://www.sciencedirect.com", alias="SCIENCEDIRECT_BASE_URL", description="ScienceDirect base URL")

    # Scraper Timeouts & Delays
    ieee_min_wait: int = Field(default=4, alias="IEEE_MIN_WAIT", description="IEEE scraper minimum bekleme süresi (sn)")
    ieee_max_wait: int = Field(default=10, alias="IEEE_MAX_WAIT", description="IEEE scraper maksimum bekleme süresi (sn)")
    ieee_page_load_timeout: int = Field(default=90, alias="IEEE_PAGE_LOAD_TIMEOUT", description="IEEE sayfa yükleme timeout (sn)")

    sd_timeout: int = Field(default=90, alias="SD_TIMEOUT", description="Science Direct sayfa yükleme timeout (sn)")
    sd_implicit_wait: int = Field(default=90, alias="SD_IMPLICIT_WAIT", description="Science Direct implicit wait (sn)")
    sd_min_wait: float = Field(default=2.0, alias="SD_MIN_WAIT", description="ScienceDirect scraper minimum bekleme süresi (sn)")
    sd_max_wait: float = Field(default=5.0, alias="SD_MAX_WAIT", description="ScienceDirect scraper maksimum bekleme süresi (sn)")
    
    # ACM Timeouts & Delays
    acm_base_url: str = Field(default="https://dl.acm.org/journals", alias="ACM_BASE_URL", description="ACM Digital Library base URL")
    acm_min_wait: int = Field(default=4, alias="ACM_MIN_WAIT", description="ACM scraper minimum bekleme süresi (sn)")
    acm_max_wait: int = Field(default=10, alias="ACM_MAX_WAIT", description="ACM scraper maksimum bekleme süresi (sn)")
    acm_page_load_timeout: int = Field(default=90, alias="ACM_PAGE_LOAD_TIMEOUT", description="ACM sayfa yükleme timeout (sn)")

    # Wiley Timeouts & Delays
    wiley_base_url: str = Field(
        default="https://onlinelibrary.wiley.com/action/showPublications?ConceptID=68&PubType=journal&startPage=0&pageSize=20",
        alias="WILEY_BASE_URL",
        description="Wiley Online Library base URL"
    )
    wiley_min_wait: int = Field(default=4, alias="WILEY_MIN_WAIT", description="Wiley scraper minimum bekleme süresi (sn)")
    wiley_max_wait: int = Field(default=10, alias="WILEY_MAX_WAIT", description="Wiley scraper maksimum bekleme süresi (sn)")
    wiley_page_load_timeout: int = Field(default=90, alias="WILEY_PAGE_LOAD_TIMEOUT", description="Wiley sayfa yükleme timeout (sn)")
    wiley_max_articles: int = Field(default=100, alias="WILEY_MAX_ARTICLES", description="Wiley scraper maksimum makale sayısı")

    # Springer Timeouts & Delays
    springer_base_url: str = Field(
        default="https://link.springer.com/brands/springer/journals/computer-science",
        alias="SPRINGER_BASE_URL",
        description="Springer base URL"
    )
    springer_min_wait: int = Field(default=3, alias="SPRINGER_MIN_WAIT", description="Springer scraper minimum bekleme süresi (sn)")
    springer_max_wait: int = Field(default=8, alias="SPRINGER_MAX_WAIT", description="Springer scraper maksimum bekleme süresi (sn)")
    springer_page_load_timeout: int = Field(default=60, alias="SPRINGER_PAGE_LOAD_TIMEOUT", description="Springer sayfa yükleme timeout (sn)")
    springer_max_articles: int = Field(default=100, alias="SPRINGER_MAX_ARTICLES", description="Springer scraper maksimum makale sayısı")
    
    # ─────────────────────────────────────────────────────────────────────
    # Slow-Network / Resilience Settings (yavaş internet optimizasyonu)
    # ─────────────────────────────────────────────────────────────────────
    # Sayfa yükleme stratejisi: "normal" (tüm subresource'lar) | "eager"
    # (DOMContentLoaded'da devam, görseller beklenmez) | "none"
    page_load_strategy: str = Field(default="eager", alias="PAGE_LOAD_STRATEGY", description="Chrome pageLoadStrategy: normal|eager|none")
    implicit_wait: int = Field(default=5, alias="IMPLICIT_WAIT", description="Selenium implicit wait (sn) — düşük tut, explicit wait kullanılır")
    max_page_load_timeout_cap: int = Field(default=240, alias="MAX_PAGE_LOAD_TIMEOUT_CAP", description="Adaptif timeout üst sınırı (sn)")

    # Kaynak engelleme (görsel/font/medya inmesin → yavaş hatta bant tasarrufu)
    block_resources_default: bool = Field(default=True, alias="BLOCK_RESOURCES", description="Varsayılan kaynak engelleme (görsel/font/medya)")
    block_images: bool = Field(default=True, alias="BLOCK_IMAGES", description="Görselleri engelle")
    block_fonts: bool = Field(default=True, alias="BLOCK_FONTS", description="Web fontlarını engelle")
    block_media: bool = Field(default=True, alias="BLOCK_MEDIA", description="Video/ses medyasını engelle")
    block_stylesheets: bool = Field(default=False, alias="BLOCK_STYLESHEETS", description="CSS engelle (RİSKLİ: anti-bot/JS görünürlük kontrolünü bozabilir)")
    blocked_url_patterns_csv: str = Field(
        default="*doubleclick.net*,*googlesyndication.com*,*google-analytics.com*,*googletagmanager.com*,*scorecardresearch.com*,*hotjar.com*,*segment.io*,*facebook.net*,*adservice.google.com*",
        alias="BLOCKED_URL_PATTERNS",
        description="CDP ile engellenecek reklam/tracker URL pattern'leri (virgülle ayrık)"
    )

    # Per-scraper kaynak engelleme override (None → block_resources_default)
    ieee_block_resources: Optional[bool] = Field(default=None, alias="IEEE_BLOCK_RESOURCES", description="IEEE için kaynak engelleme override")
    sciencedirect_block_resources: Optional[bool] = Field(default=None, alias="SCIENCEDIRECT_BLOCK_RESOURCES", description="ScienceDirect için kaynak engelleme override")
    acm_block_resources: Optional[bool] = Field(default=None, alias="ACM_BLOCK_RESOURCES", description="ACM için kaynak engelleme override")
    wiley_block_resources: Optional[bool] = Field(default=None, alias="WILEY_BLOCK_RESOURCES", description="Wiley için kaynak engelleme override")
    springer_block_resources: Optional[bool] = Field(default=None, alias="SPRINGER_BLOCK_RESOURCES", description="Springer için kaynak engelleme override")

    # Ağ hızı probe (driver/proxy üzerinden ölçülür, timeout'u ölçeklemek için)
    net_probe_url: str = Field(default="https://www.google.com/generate_204", alias="NET_PROBE_URL", description="Ağ hızı ölçümü için hafif URL")
    net_slow_latency_ms: int = Field(default=800, alias="NET_SLOW_LATENCY_MS", description="Bu gecikmenin üstü 'slow' sınıfı (ms)")
    net_very_slow_latency_ms: int = Field(default=2500, alias="NET_VERY_SLOW_LATENCY_MS", description="Bu gecikmenin üstü 'very_slow' sınıfı (ms)")
    net_slow_multiplier: float = Field(default=2.0, alias="NET_SLOW_MULTIPLIER", description="'slow' sınıfında timeout çarpanı")
    net_very_slow_multiplier: float = Field(default=3.5, alias="NET_VERY_SLOW_MULTIPLIER", description="'very_slow' sınıfında timeout çarpanı")

    # Adaptif eşzamanlılık (yavaş/dengesiz hatta worker havuzunu küçült)
    adaptive_concurrency_enabled: bool = Field(default=True, alias="ADAPTIVE_CONCURRENCY_ENABLED", description="Adaptif max_tabs etkin mi")
    adaptive_min_tabs: int = Field(default=1, alias="ADAPTIVE_MIN_TABS", description="Adaptif worker alt sınırı")
    adaptive_max_tabs: int = Field(default=6, alias="ADAPTIVE_MAX_TABS", description="Adaptif worker üst sınırı")
    adaptive_window: int = Field(default=12, alias="ADAPTIVE_WINDOW", description="Hata oranı kayar pencere boyutu (fetch)")
    adaptive_error_hi: float = Field(default=0.35, alias="ADAPTIVE_ERROR_HI", description="Bu hata oranının üstünde worker azalt")
    adaptive_error_lo: float = Field(default=0.10, alias="ADAPTIVE_ERROR_LO", description="Bu hata oranının altında worker artır")
    adaptive_cooldown_fetches: int = Field(default=8, alias="ADAPTIVE_COOLDOWN_FETCHES", description="İki resize kararı arası min fetch sayısı")

    # Retry / Circuit Breaker (resilient_fetch)
    retry_max: int = Field(default=3, alias="RETRY_MAX", description="resilient_get maksimum deneme sayısı")
    retry_backoff_base: float = Field(default=1.5, alias="RETRY_BACKOFF_BASE", description="Exponential backoff taban çarpanı")
    retry_backoff_cap: float = Field(default=30.0, alias="RETRY_BACKOFF_CAP", description="Backoff bekleme üst sınırı (sn)")
    partial_page_recovery_enabled: bool = Field(default=True, alias="PARTIAL_PAGE_RECOVERY_ENABLED", description="Timeout'ta window.stop() + kısmi sayfa kurtarma")
    cb_failure_threshold: int = Field(default=8, alias="CB_FAILURE_THRESHOLD", description="Circuit breaker açılma eşiği (ardışık hata)")
    cb_recovery_timeout: int = Field(default=180, alias="CB_RECOVERY_TIMEOUT", description="Circuit breaker HALF_OPEN'a geçiş süresi (sn)")

    # Yavaş ağ simülasyonu (yalnızca doğrulama/test — CDP emulateNetworkConditions)
    scraper_net_emulate: bool = Field(default=False, alias="SCRAPER_NET_EMULATE", description="TEST: CDP ile yavaş ağ emülasyonu aç")
    scraper_net_emulate_latency_ms: int = Field(default=400, alias="SCRAPER_NET_EMULATE_LATENCY_MS", description="TEST: emüle gecikme (ms)")
    scraper_net_emulate_download_bps: int = Field(default=51200, alias="SCRAPER_NET_EMULATE_DOWNLOAD_BPS", description="TEST: emüle indirme hızı (byte/sn)")
    scraper_net_emulate_upload_bps: int = Field(default=20480, alias="SCRAPER_NET_EMULATE_UPLOAD_BPS", description="TEST: emüle yükleme hızı (byte/sn)")

    # Per-scraper max_tabs (önceden scraper_manager'da hasattr fallback ile okunuyordu)
    ieee_max_tabs: int = Field(default=3, alias="IEEE_MAX_TABS", description="IEEE paralel worker (tab) sayısı")
    sciencedirect_max_tabs: int = Field(default=3, alias="SCIENCEDIRECT_MAX_TABS", description="ScienceDirect paralel worker sayısı")
    acm_max_tabs: int = Field(default=3, alias="ACM_MAX_TABS", description="ACM paralel worker sayısı")
    wiley_max_tabs: int = Field(default=3, alias="WILEY_MAX_TABS", description="Wiley paralel worker sayısı")
    springer_max_tabs: int = Field(default=3, alias="SPRINGER_MAX_TABS", description="Springer paralel worker sayısı")

    def block_resources_for(self, scraper: str) -> bool:
        """Verilen scraper için kaynak engelleme etkin mi (override yoksa default)."""
        override = getattr(self, f"{scraper}_block_resources", None)
        return self.block_resources_default if override is None else override

    # PDF Settings
    pdf_download_timeout: int = Field(default=60, alias="PDF_DOWNLOAD_TIMEOUT", description="PDF indirme timeout süresi (sn)")
    pdf_download_chunk_size: int = Field(default=8192, alias="PDF_DOWNLOAD_CHUNK_SIZE", description="PDF dosya yazma parça boyutu (byte)")
    
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
        default=10, 
        alias="NLP_UMAP_N_NEIGHBORS",
        description="UMAP n_neighbors parametresi"
    )
    nlp_umap_n_components: int = Field(
        default=15, 
        alias="NLP_UMAP_N_COMPONENTS",
        description="UMAP çıktı boyutu"
    )
    nlp_min_cluster_size_all: int = Field(
    default=10,
    alias="NLP_MIN_CLUSTER_SIZE_ALL",
    description="HDBSCAN min_cluster_size for all articles clustering"
    )
    nlp_min_samples_all: int = Field(
        default=3,
        alias="NLP_MIN_SAMPLES_ALL",
        description="HDBSCAN min_samples for all articles clustering"
    )

    nlp_min_cluster_size_publisher: int = Field(
        default=5,
        alias="NLP_MIN_CLUSTER_SIZE_PUBLISHER",
        description="HDBSCAN min_cluster_size for publisher clustering"
    )
    nlp_min_samples_publisher: int = Field(
        default=2,
        alias="NLP_MIN_SAMPLES_PUBLISHER",
        description="HDBSCAN min_samples for publisher clustering"
    )

    nlp_min_cluster_size_journal: int = Field(
        default=3,
        alias="NLP_MIN_CLUSTER_SIZE_JOURNAL",
        description="HDBSCAN min_cluster_size for journal clustering"
    )
    nlp_min_samples_journal: int = Field(
        default=1,
        alias="NLP_MIN_SAMPLES_JOURNAL",
        description="HDBSCAN min_samples for journal clustering"
    )
    nlp_lazy_init: bool = Field(
        default=True,
        alias="NLP_LAZY_INIT",
        description="NLP modelleri başlangıçta değil ilk kullanımda yüklensin mi"
    )
    nlp_model_dir: str = Field(
        default="nlp_models",
        alias="NLP_MODEL_DIR",
        description="Yerel NLP model deposu dizini"
    )
    nlp_cross_encoder_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="NLP_CROSS_ENCODER_MODEL",
        description="CrossEncoder model adı"
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
    
    # ==================== OpenAlex API Settings ====================
    openalex_api_base_url: str = Field(
        default="https://api.openalex.org",
        alias="OPENALEX_API_BASE_URL",
        description="OpenAlex API Base URL"
    )
    openalex_polite_email: Optional[str] = Field(
        default=None,
        alias="OPENALEX_POLITE_EMAIL",
        description="Email address for polite pool access to bypass rate limits"
    )
    openalex_api_timeout: int = Field(
        default=30,
        alias="OPENALEX_API_TIMEOUT",
        description="OpenAlex API timeout in seconds"
    )
    openalex_bulk_chunk_size: int = Field(
        default=50,
        alias="OPENALEX_BULK_CHUNK_SIZE",
        description="Max chunk size for bulk requests"
    )
    citation_graph_max_depth: int = Field(
        default=5,
        alias="CITATION_GRAPH_MAX_DEPTH",
        description="Maximum BFS traversal depth for citation graph collection"
    )
    citation_max_per_level: int = Field(
        default=50,
        alias="CITATION_MAX_PER_LEVEL",
        description="Maximum citing works fetched per node per BFS level"
    )
    cache_ttl_citation_graph: int = Field(
        default=3600,
        alias="CACHE_TTL_CITATION_GRAPH",
        description="Citation graph persistent cache TTL in seconds"
    )
    citation_graph_concurrency: int = Field(
        default=8,
        alias="CITATION_GRAPH_CONCURRENCY",
        description="Max concurrent OpenAlex requests during citation graph BFS"
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
    elasticsearch_auto_sync: bool = Field(
        default=True,
        alias="ELASTICSEARCH_AUTO_SYNC",
        description="Elasticsearch otomatik senkronizasyon (startup ve live) yapılsın mı"
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
    def nlp_model_dir_path(self) -> Path:
        """Yerel NLP model dizini tam yolu"""
        model_path = Path(self.nlp_model_dir)
        if model_path.is_absolute():
            return model_path
        return Path(__file__).parent.parent.parent / model_path

    @property
    def nlp_embedder_path(self) -> Path:
        """Embedder model yerel yolu"""
        return self.nlp_model_dir_path / "embedder"

    @property
    def nlp_cross_encoder_path(self) -> Path:
        """CrossEncoder model yerel yolu"""
        return self.nlp_model_dir_path / "cross_encoder"
    
    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"
        populate_by_name = True  # Hem field name hem alias ile populate et


# Singleton
settings = Settings()
