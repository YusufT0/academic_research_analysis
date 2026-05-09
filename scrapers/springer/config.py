"""Configuration management for Springer scraper."""

from backend.core.config import settings


class ProxyConfig:
    """Proxy ayarlarını yöneten sınıf."""

    def __init__(self):
        self.use_proxy = settings.use_proxy
        self.user = settings.proxy_user
        self.password = settings.proxy_pass
        self.host = settings.proxy_host
        self.port = settings.proxy_port

    def is_configured(self) -> bool:
        if not self.use_proxy:
            return False
        return bool(self.user and self.password and self.host and self.port)

    def get_proxy_string(self) -> str:
        if not self.is_configured():
            return ""
        return f"{self.user}:{self.password}@{self.host}:{self.port}"


class SpringerConfig:
    """Springer scraper genel ayarları."""

    def __init__(self):
        self.base_url = getattr(
            settings,
            "springer_base_url",
            "https://link.springer.com/brands/springer/journals/computer-science",
        )
        self.springer_domain = "https://link.springer.com"

        self.min_wait = getattr(settings, "springer_min_wait", 3)
        self.max_wait = getattr(settings, "springer_max_wait", 8)
        self.page_load_timeout = getattr(settings, "springer_page_load_timeout", 60)
        self.max_articles = getattr(settings, "springer_max_articles", 100)
