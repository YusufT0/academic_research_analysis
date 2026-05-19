"""
Ağ hızı probe — yavaş internette page-load timeout'unu adaptif ölçeklemek için.

Hafif bir HTTP isteğinin gidiş-dönüş süresi ölçülür, gecikmeye göre
fast/slow/very_slow sınıfı çıkarılır, timeout o oranda büyütülür.
Ölçüm başarısız olursa cezalandırma yapılmaz ('fast' kabul edilir).

ÖNEMLİ: Ölçüm KASITLI olarak tarayıcı sürücüsünden bağımsızdır (stdlib HTTP).
Eskiden `driver.execute_async_script` ile ölçülüyordu; ancak SeleniumBase UC
modunda sürücü, CDP modu aktifleşmeden önce stealth/kopuk durumdadır ve bu
durumda JS round-trip zorlamak Chrome'da "tab crashed" hatasına yol açar
(sonraki ilk komutta, örn. set_window_size, patlar). Driver'a hiç dokunmayan
bu probe tüm scraper'larda (UC+CDP ve wire+uc) güvenlidir.
"""

import threading
import time
import urllib.request
from typing import Optional

from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger("network_probe")

# Soket seviyesi timeout (sn) — connect/read başına. DNS çözümünü KAPSAMAZ.
_PROBE_SOCKET_TIMEOUT_S = 4.0
# Sert duvar-saati üst sınırı (sn). DNS dahil her şeyi kapsar: bu süre
# içinde bitmezse ölçüm 'None' (=fast) kabul edilir ve driver start beklemez.
# Yavaş/dengesiz ağda getaddrinfo soket timeout'unu dinlemediği için şart.
_PROBE_HARD_DEADLINE_S = 5.0
_PROBE_UA = "Mozilla/5.0 (compatible; NetworkProbe/1.0)"


class NetworkProbe:
    """Hafif HTTP isteğiyle ağ gecikmesi ölçer ve sınıflandırır."""

    def measure(self, driver=None) -> Optional[float]:
        """
        Saniye cinsinden gecikme döner. Ölçülemezse None.

        Ölçüm bir watchdog thread'inde yapılır ve sert bir duvar-saati
        sınırıyla korunur: DNS/handshake takılsa bile driver start
        `_PROBE_HARD_DEADLINE_S`'ten fazla bloke OLMAZ (orphan thread
        daemon olduğundan zararsızdır).

        Args:
            driver: Yok sayılır (geriye dönük uyumluluk için tutulur).
                Ölçüm tarayıcıya dokunmaz — UC modunda tab-crash riski yok.
        """
        result: list[Optional[float]] = [None]

        def _run():
            try:
                req = urllib.request.Request(
                    settings.net_probe_url,
                    headers={"User-Agent": _PROBE_UA},
                    method="GET",
                )
                t0 = time.perf_counter()
                with urllib.request.urlopen(
                    req, timeout=_PROBE_SOCKET_TIMEOUT_S
                ) as resp:
                    resp.read(1)  # gövde küçük (genelde 204); ilk bayt yeterli
                result[0] = time.perf_counter() - t0
            except Exception as e:
                logger.debug("network probe ölçülemedi", error=str(e))

        t = threading.Thread(target=_run, name="network-probe", daemon=True)
        t.start()
        t.join(_PROBE_HARD_DEADLINE_S)
        if t.is_alive():
            logger.debug(
                "network probe deadline aşıldı, 'fast' kabul ediliyor",
                deadline_s=_PROBE_HARD_DEADLINE_S,
            )
            return None
        return result[0]

    def classify(self, latency_s: Optional[float]) -> str:
        """Gecikmeyi 'fast' | 'slow' | 'very_slow' olarak sınıflandır."""
        if latency_s is None:
            return "fast"  # ölçülemezse cezalandırma
        ms = latency_s * 1000.0
        if ms >= settings.net_very_slow_latency_ms:
            return "very_slow"
        if ms >= settings.net_slow_latency_ms:
            return "slow"
        return "fast"

    def timeout_multiplier(self, klass: str) -> float:
        """Sınıfa göre timeout çarpanı."""
        return {
            "fast": 1.0,
            "slow": settings.net_slow_multiplier,
            "very_slow": settings.net_very_slow_multiplier,
        }.get(klass, 1.0)

    def measure_and_classify(self, driver) -> str:
        """Ölç + sınıflandır, tek çağrıda. Yan etki: log."""
        latency = self.measure(driver)
        klass = self.classify(latency)
        logger.info(
            "network_probe",
            latency_ms=round(latency * 1000.0, 1) if latency is not None else None,
            network_class=klass,
        )
        return klass


def effective_page_load_timeout(base: int, network_class: str) -> int:
    """
    Taban timeout'u ağ sınıfına göre ölçekle, cap ile sınırla.

    Args:
        base: settings.<scraper>_page_load_timeout değeri
        network_class: 'fast' | 'slow' | 'very_slow'
    """
    mult = NetworkProbe().timeout_multiplier(network_class)
    scaled = int(base * mult)
    return min(scaled, settings.max_page_load_timeout_cap)
