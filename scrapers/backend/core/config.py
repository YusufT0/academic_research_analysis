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
    
    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"
        populate_by_name = True  # Hem field name hem alias ile populate et


# Singleton
settings = Settings()
