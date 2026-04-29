import asyncio
import logging
from typing import Dict, Any, List

from backend.services.stream_service import stream_service
from backend.services.openalex.citation_service import citation_service
from database.models import Article, Journal

logger = logging.getLogger(__name__)

class CitationWorker:
    """
    Background worker for listening to Redis Streams and updating 
    citation data asynchronously via OpenAlex API.
    """

    async def _handle_article_citation_needed(self, batch: List[Dict[str, Any]]) -> None:
        """
        Stream'den 'article:citation_needed' mesajı geldiğinde tetiklenir.
        stream_service batch (list of {id, data, stream}) olarak çağırır.
        """
        for msg in batch:
            data = msg.get("data", {}) if isinstance(msg, dict) else {}
            await self._process_article_citation(data)

    async def _process_article_citation(self, data: Dict[str, Any]) -> None:
        article_id = data.get("article_id")
        doi = data.get("doi")
        
        if not doi:
            logger.warning(f"No DOI found in citation payload for article: {article_id}")
            return

        try:
            article = await Article.get(article_id)
            if not article:
                logger.warning(f"Article not found in DB with ID: {article_id}")
                return

            updated_count = await citation_service.update_articles_citations_bulk([article])

            if updated_count > 0:
                logger.info(f"Successfully updated citation data for Article (DOI: {doi})")
                await stream_service.publish("article:indexed", {"article_id": str(article.id)})

                try:
                    from backend.services.openalex.citation_graph_service import citation_graph_service
                    await citation_graph_service.build_graph(str(article.id), max_depth=1)
                except Exception as graph_err:
                    logger.warning(f"Graph build skipped for {article_id}: {graph_err}")
            else:
                logger.info(f"OpenAlex did not find data for DOI: {doi}")

        except Exception as e:
            logger.error(f"Error handling article citation update for {article_id}: {str(e)}")
            await stream_service.publish("article:dlq", {
                "failed_stream": "article:citation_needed",
                "article_id": article_id,
                "error": str(e)
            })

    async def _handle_journal_citation_needed(self, batch: List[Dict[str, Any]]) -> None:
        """
        Stream'den 'journal:citation_needed' mesajı geldiğinde tetiklenir.
        stream_service batch (list of {id, data, stream}) olarak çağırır.
        """
        for msg in batch:
            data = msg.get("data", {}) if isinstance(msg, dict) else {}
            journal_id = data.get("journal_id")

            try:
                journal = await Journal.get(journal_id)
                if not journal:
                    logger.warning(f"Journal not found in DB with ID: {journal_id}")
                    continue

                success = await citation_service.update_journal_citation_metrics(journal)

                if success:
                    logger.info(f"Successfully updated journal metrics for: {journal.name}")
                else:
                    logger.warning(f"Could not find journal metrics in OpenAlex for: {journal.name}")

            except Exception as e:
                logger.error(f"Error handling journal citation update for {journal_id}: {str(e)}")
                await stream_service.publish("article:dlq", {
                    "failed_stream": "journal:citation_needed",
                    "journal_id": journal_id,
                    "error": str(e)
                })

    def register_workers(self):
        """Bu fonksiyon stream service consumer'larına handlerları kaydeder."""
        stream_service.register_handler("article:citation_needed", self._handle_article_citation_needed)
        stream_service.register_handler("journal:citation_needed", self._handle_journal_citation_needed)
        logger.info("Citation Stream Workers registered successfully.")

citation_worker = CitationWorker()
