"""
Prometheus Metrics

Custom application-level metrikler.

Usage:
    from backend.core.metrics import ARTICLES_SCRAPED, SCRAPER_ERRORS
    
    ARTICLES_SCRAPED.labels(source="ieee").inc()
    SCRAPER_ERRORS.labels(source="ieee", error_type="timeout").inc()
"""

from prometheus_client import Counter, Histogram, Gauge


# ==================== Scraper Metrics ====================

ARTICLES_SCRAPED = Counter(
    "scraper_articles_total",
    "Total articles scraped",
    ["source"],
)

SCRAPER_ERRORS = Counter(
    "scraper_errors_total", 
    "Total scraper errors",
    ["source", "error_type"],
)

SCRAPER_DURATION = Histogram(
    "scraper_duration_seconds",
    "Scraping duration per journal",
    ["source"],
    buckets=[10, 30, 60, 120, 300, 600, 1800],
)

ACTIVE_SCRAPERS = Gauge(
    "active_scrapers",
    "Number of active scrapers",
)

# ==================== Database Metrics ====================

DB_OPERATION_DURATION = Histogram(
    "db_operation_duration_seconds",
    "Database operation duration",
    ["operation"],  # insert, find, update, delete
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

MONGODB_POOL_MAX_SIZE = Gauge(
    "mongodb_pool_max_size",
    "Configured MongoDB connection pool max size",
)

MONGODB_POOL_MIN_SIZE = Gauge(
    "mongodb_pool_min_size",
    "Configured MongoDB connection pool min size",
)

# ==================== Circuit Breaker Metrics ====================

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["breaker"],
)

# ==================== WebSocket Metrics ====================

WS_CONNECTIONS = Gauge(
    "ws_connections_active",
    "Active WebSocket connections",
)

# ==================== Cache Metrics ====================

CACHE_HITS = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["entity_type"],
)

CACHE_MISSES = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["entity_type"],
)

CACHE_MEMORY_USED_BYTES = Gauge(
    "cache_memory_used_bytes",
    "Redis memory used in bytes",
)

# ==================== Redis Streams Metrics ====================

STREAM_MESSAGES_PUBLISHED = Counter(
    "stream_messages_published_total",
    "Messages published to Redis Streams",
    ["stream"],
)

STREAM_MESSAGES_CONSUMED = Counter(
    "stream_messages_consumed_total",
    "Messages consumed from Redis Streams",
    ["stream", "consumer_group"],
)

STREAM_DLQ_SIZE = Gauge(
    "stream_dlq_size",
    "Dead letter queue size",
)
