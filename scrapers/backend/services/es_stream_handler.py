"""
Elasticsearch Stream Handler

article:scraped stream'ini dinler ve gelen makaleleri Elasticsearch'e index'ler.
Bu write-through pattern sayesinde ES sync count-based değil event-driven olur.
"""

from typing import List, Dict, Any
from utils.logger import get_logger

logger = get_logger("es_stream_handler")


class ESStreamHandler:
    """
    Redis Streams'ten gelen article:scraped event'lerini ES'e index'ler.
    Micro-batch: stream_service 50'lik batch'ler gönderir, hepsini bulk index eder.
    """

    def register(self):
        """Handler'ı stream_service'e kaydet."""
        try:
            from backend.services.stream_service import stream_service
            stream_service.register_handler("article:scraped", self.handle_batch)
            logger.info("ES stream handler registered for article:scraped")
        except Exception as e:
            logger.error(f"ES stream handler registration failed: {e}")

    async def handle_batch(self, batch: List[Dict[str, Any]]):
        """
        article:scraped batch'ini ES'e bulk index et.
        batch: [{"id": msg_id, "data": {...article fields...}, "stream": "article:scraped"}, ...]
        """
        try:
            from backend.services.elasticsearch_service import elasticsearch_service
            if not elasticsearch_service.is_connected:
                logger.warning("ES not connected — skipping batch index")
                return

            articles = [msg["data"] for msg in batch if msg.get("data")]
            if not articles:
                return

            indexed = await elasticsearch_service.bulk_index(articles)
            logger.info(
                "ES stream handler: batch indexed",
                batch_size=len(batch),
                indexed=indexed,
            )
        except Exception as e:
            logger.error(f"ES stream handler batch error: {e}")
            raise  # stream_service'in DLQ'ya taşımasına izin ver


# Singleton
es_stream_handler = ESStreamHandler()
