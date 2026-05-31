"""
Chrome performans/bant genişliği ayarları — yavaş internet optimizasyonu.

Tek doğruluk kaynağı: tüm scraper driver'ları (wire+uc ve SeleniumBase aileleri)
bu modüldeki yardımcıları kullanır. Görsel/font/medya engelleme ve pageLoadStrategy
yavaş hatta indirilen bayt miktarını ve sayfa yükleme süresini dramatik düşürür.

JavaScript ASLA kapatılmaz (anti-bot/Cloudflare JS gerektirir).
"""

from typing import List, Optional

from utils.logger import get_logger

logger = get_logger("chrome_tuning")


def build_perf_prefs(
    block_images: bool = True,
    block_fonts: bool = True,
    block_media: bool = True,
    block_stylesheets: bool = False,
) -> dict:
    """
    Chrome `prefs` experimental option için içerik ayarları.

    managed_default_content_settings değerleri: 1 = izin ver, 2 = engelle.
    JavaScript hiçbir koşulda engellenmez.
    """
    content_settings: dict = {}
    if block_images:
        content_settings["images"] = 2
    if block_stylesheets:
        content_settings["stylesheets"] = 2
    # Notification/popup gürültüsünü her zaman kapat
    content_settings["notifications"] = 2

    prefs: dict = {
        "profile.managed_default_content_settings": content_settings,
        "profile.default_content_setting_values": {
            "notifications": 2,
        },
    }
    # Font engelleme prefs ile güvenilir değil; CDP/blink-settings ile yapılır.
    # (block_fonts/block_media parametreleri perf_chrome_args + CDP'de kullanılır)
    return prefs


def perf_chrome_args(block_images: bool = True) -> List[str]:
    """uc/Chrome options'a eklenecek performans flag'leri."""
    args = [
        "--disable-background-networking",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-background-timer-throttling",
        "--no-default-browser-check",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-domain-reliability",
    ]
    if block_images:
        # Render motoru seviyesinde görselleri kapat (prefs strip edilse bile çalışır)
        args.append("--blink-settings=imagesEnabled=false")
    return args


def apply_page_load_strategy(options, strategy: str = "eager") -> None:
    """ChromeOptions/uc.ChromeOptions üzerine pageLoadStrategy uygula."""
    strategy = (strategy or "eager").lower()
    if strategy not in ("normal", "eager", "none"):
        strategy = "eager"
    try:
        options.page_load_strategy = strategy
    except Exception as e:  # bazı eski option sınıfları desteklemeyebilir
        logger.warning("pageLoadStrategy ayarlanamadı", strategy=strategy, error=str(e))


def blocked_url_patterns(csv: str) -> List[str]:
    """Virgülle ayrık reklam/tracker pattern CSV'sini listeye çevir."""
    if not csv:
        return []
    return [p.strip() for p in csv.split(",") if p.strip()]


def enable_cdp_request_blocking(
    driver,
    patterns: Optional[List[str]] = None,
    block_images: bool = True,
    block_fonts: bool = True,
    block_media: bool = True,
) -> None:
    """
    CDP üzerinden ağ isteklerini engelle. uc bazen `prefs`'i strip ettiği için
    bu **garanti yol**. Hiçbir koşulda fatal değildir (best-effort, try/except).

    - Network.setBlockedURLs: bilinen reklam/tracker domainleri
    - Görsel engelleme: blink-settings=imagesEnabled=false (perf_chrome_args) ile yapılır.

    NOT: Fetch.enable / requestPaused yaklaşımı Selenium'da kullanılmaz.
    Selenium'un senkron modeli Fetch.requestPaused event'lerine yanıt vermeyi
    desteklemediğinden, yakalanan istekler sonsuza asılı kalır ve readyState
    hiç 'complete' olmaz — her fetch 15+ sn timeout'a düşer.
    """
    if driver is None:
        return

    patterns = patterns or []

    # Reklam/tracker URL pattern engelleme — Network.setBlockedURLs hemen
    # net::ERR_BLOCKED_BY_CLIENT döndürür, istekler asılı kalmaz.
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        if patterns:
            driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": patterns})
            logger.info(
                "resource_blocking_enabled",
                method="Network.setBlockedURLs",
                pattern_count=len(patterns),
            )
    except Exception as e:
        logger.warning("CDP Network.setBlockedURLs başarısız", error=str(e))


def maybe_emulate_slow_network(driver, settings) -> None:
    """
    SADECE TEST/DOĞRULAMA: settings.scraper_net_emulate True ise CDP ile
    yavaş ağ koşulu emüle eder. Üretimde varsayılan kapalı.
    """
    if not getattr(settings, "scraper_net_emulate", False) or driver is None:
        return
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "latency": settings.scraper_net_emulate_latency_ms,
                "downloadThroughput": settings.scraper_net_emulate_download_bps,
                "uploadThroughput": settings.scraper_net_emulate_upload_bps,
            },
        )
        logger.warning(
            "slow_network_emulation_active",
            latency_ms=settings.scraper_net_emulate_latency_ms,
            download_bps=settings.scraper_net_emulate_download_bps,
        )
    except Exception as e:
        logger.warning("Ağ emülasyonu ayarlanamadı", error=str(e))
