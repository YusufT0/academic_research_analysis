import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .citation_service import citation_service
from database.models import Article, Journal
from backend.routers.websocket import emit_scraper_event

logger = logging.getLogger(__name__)

class OpenAlexManualScanner:
    """
    Manuel olarak tetiklenebilen OpenAlex tarama yöneticisi.
    Background task olarak çalışır, mevcut makale veritabanını tarar
    ve henüz OpenAlex verisi çekilmemiş (is_openalex_indexed=False veya missing)
    makalelerin/dergilerin verilerini API üzerinden günceller.
    WebSocket üzerinden ilerleme durumunu 'openalex' scraper_type ile yayınlar.
    """

    def __init__(self):
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.total_articles = 0
        self.processed_articles = 0
        self.total_journals = 0
        self.processed_journals = 0
        self.updated_count = 0
        self.start_time: Optional[datetime] = None
        self.status = "idle"

    def start_scan(self):
        if self.is_running:
            return False
        
        self.is_running = True
        self.status = "running"
        self.total_articles = 0
        self.processed_articles = 0
        self.total_journals = 0
        self.processed_journals = 0
        self.updated_count = 0
        self.start_time = datetime.now(timezone.utc)

        # Trigger scanning background task
        self._task = asyncio.create_task(self._scan_process())
        return True

    def stop_scan(self):
        if not self.is_running:
            return False
        
        self.is_running = False
        self.status = "stopping"
        # Task will exit on next check
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "total_articles": self.total_articles,
            "processed_articles": self.processed_articles,
            "total_journals": self.total_journals,
            "processed_journals": self.processed_journals,
            "updated_count": self.updated_count,
            "start_time": self.start_time.isoformat() if self.start_time else None
        }

    async def _scan_process(self):
        """Asıl tarama işlemini yürüten asenkron döngü"""
        try:
            self._emit_event("status_update", "OpenAlex bağlamlı tarama başladı.")
            
            # TODO: Pagination ile fetch edebiliriz ama basitlik için chunks kullanacağız.
            
            # Adım 1: Düzeltilmemiş veya openalex verisi eksik makaleler (örneğin doi var is_openalex_indexed yok/False)
            unindexed_articles = await Article.find(
                {"doi": {"$exists": True, "$ne": None}, "is_openalex_indexed": {"$ne": True}}
            ).to_list()

            self.total_articles = len(unindexed_articles)
            self._emit_event("log", f"{self.total_articles} adet taranmamış makale bulundu.")

            chunk_size = 50
            for i in range(0, self.total_articles, chunk_size):
                if not self.is_running:
                    self._emit_event("log", "Kullanıcı taramayı durdurdu.")
                    break
                
                chunk = unindexed_articles[i:i+chunk_size]
                
                # Citation servise gönder
                try:
                    updated = await citation_service.update_articles_citations_bulk(chunk)
                    self.updated_count += updated
                except Exception as e:
                    logger.error(f"Bulk update hatası: {e}")
                    self._emit_event("error", f"Update error: {str(e)}")

                self.processed_articles += len(chunk)

                # Güncellenen makaleler için depth-1 atıf grafiği oluştur
                from .citation_graph_service import citation_graph_service
                for article in chunk:
                    if not self.is_running:
                        break
                    if article.openalex_id:
                        try:
                            await citation_graph_service.build_graph(
                                str(article.id), max_depth=1
                            )
                        except Exception as graph_err:
                            logger.warning(f"Graph build skipped for {article.id}: {graph_err}")

                # Progress raporla
                self._emit_progress()

                # Bir miktar bekle (Rate limiting vs.)
                await asyncio.sleep(0.5)

            # Adım 2: Dergiler
            if self.is_running:
                unindexed_journals = await Journal.find(
                    {"openalex_id": None}
                ).to_list()

                self.total_journals = len(unindexed_journals)
                if self.total_journals > 0:
                    self._emit_event("log", f"{self.total_journals} adet taranmamış dergi bulundu.")
                
                for journal in unindexed_journals:
                    if not self.is_running:
                        break
                    
                    try:
                        success = await citation_service.update_journal_citation_metrics(journal)
                        if success:
                            self.updated_count += 1
                    except Exception as e:
                        logger.error(f"Journal update hatası: {e}")

                    self.processed_journals += 1
                    self._emit_progress()
                    await asyncio.sleep(0.5)

            if self.is_running:
                self.status = "completed"
                self._emit_event("completed", "Tarama başarıyla tamamlandı.")
            else:
                self.status = "stopped"

        except Exception as e:
            logger.error(f"OpenAlex scanner process hatası: {e}")
            self.status = "error"
            self._emit_event("error", f"Bilinmeyen hata: {str(e)}")
        finally:
            self.is_running = False

    def _emit_progress(self):
        # Yüzdelik hesapla vs.
        total_items = self.total_articles + self.total_journals
        processed = self.processed_articles + self.processed_journals
        
        # Avoid division by zero
        progress_val = (processed / total_items * 100) if total_items > 0 else 0
        
        emit_scraper_event(
            event_type="progress",
            scraper_type="openalex",
            data={
                "processed_articles": self.processed_articles,
                "total_articles": self.total_articles,
                "processed_journals": self.processed_journals,
                "total_journals": self.total_journals,
                "updated_count": self.updated_count,
                "progress_percentage": round(progress_val, 2)
            }
        )
        
    def _emit_event(self, event_type: str, message: str):
        emit_scraper_event(
            event_type=event_type,
            scraper_type="openalex",
            data={"message": message, **self.get_status()}
        )

openalex_manual_scanner = OpenAlexManualScanner()
