"""
Citation Graph Service
Level-by-level paralel BFS ile atıf grafiği oluşturma ve Redis'e cache'leme.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Set, List, Tuple

from beanie import PydanticObjectId

from database.models import Article
from backend.services.cache_service import get_cache_service
from backend.services.openalex.client import openalex_client
from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger("citation_graph")


class CitationGraphService:
    """
    OpenAlex 'cites' filtresini kullanarak level-by-level paralel BFS ile atıf grafiği oluşturur.
    Her derinlik seviyesindeki tüm düğümler eş zamanlı olarak sorgulanır.
    Sonuçlar Redis cache'e kaydedilir (TTL ile).
    """

    async def build_graph(
        self,
        article_id: str,
        max_depth: Optional[int] = None,
        max_per_level: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Kök makaleden itibaren level-by-level paralel BFS ile atıf grafiği oluşturur.

        Edge semantiği: source → target  (source, target'ı cite ediyor)

        Args:
            article_id: Article MongoDB ID (string)
            max_depth: BFS derinliği (None = settings'ten alınır)
            max_per_level: Her düğüm için max cite eden çalışma sayısı

        Returns:
            Graf verisi dict veya None (makale bulunamazsa/openalex_id yoksa)
        """
        depth = min(
            max_depth or settings.citation_graph_max_depth,
            settings.citation_graph_max_depth,
        )
        base_per_level = min(
            max_per_level or settings.citation_max_per_level,
            settings.citation_max_per_level,
        )
        # Derinlik arttıkça per_level'ı azalt; node patlamasını önler.
        # depth=1 → base, depth=2 → base//2, depth=3 → base//4, ...
        per_level = max(3, base_per_level // (2 ** max(0, depth - 1)))

        # 1. Kök makaleyi yükle
        try:
            article = await Article.get(PydanticObjectId(article_id))
        except Exception:
            logger.error(f"Article not found: {article_id}")
            return None

        if not article or not article.openalex_id:
            logger.warning(f"Article {article_id} has no openalex_id — skipping graph build")
            return None

        # 2. Redis cache kontrolü
        cache = get_cache_service()
        try:
            cached = await cache.get_citation_graph(article_id, depth)
            if cached:
                logger.debug(f"Citation graph cache hit for {article_id} depth={depth}")
                return cached
        except Exception as e:
            logger.warning(f"Cache check failed for {article_id}: {e}")

        # 3. Level-by-level paralel BFS
        root_id = article.openalex_id
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        visited: Set[str] = set()

        # Kök düğümü
        nodes[root_id] = {
            "id": root_id,
            "title": article.title,
            "doi": article.doi,
            "cited_by_count": article.citation_count,
            "publication_year": article.publication_year,
            "is_root": True,
            "is_internal": True,
            "internal_article_id": str(article.id),
            "depth": 0,
        }
        visited.add(root_id)

        # Concurrency limiti
        semaphore = asyncio.Semaphore(settings.citation_graph_concurrency)

        async def fetch_citing(node_id: str) -> Tuple[str, List[Dict[str, Any]]]:
            """Semaphore ile sınırlı tekil OpenAlex isteği."""
            async with semaphore:
                try:
                    works = await openalex_client.get_citing_works(node_id, per_page=per_level)
                except Exception as e:
                    logger.warning(f"get_citing_works failed for {node_id}: {e}")
                    works = []
                return node_id, works

        # BFS: seviye seviye işle
        current_level_ids: List[str] = [root_id]

        for current_depth in range(depth):
            if not current_level_ids:
                break

            # Bu seviyedeki tüm düğümler için eş zamanlı fetch
            level_results: List[Tuple[str, List[Dict[str, Any]]]] = await asyncio.gather(
                *[fetch_citing(nid) for nid in current_level_ids],
                return_exceptions=False,
            )

            next_level_ids: List[str] = []

            for current_id, citing_works in level_results:
                for work in citing_works[:per_level]:
                    work_id = work.get("id")
                    if not work_id:
                        continue

                    # Yeni düğüm
                    if work_id not in nodes:
                        nodes[work_id] = {
                            "id": work_id,
                            "title": work.get("title"),
                            "doi": work.get("doi"),
                            "cited_by_count": work.get("cited_by_count", 0),
                            "publication_year": work.get("publication_year"),
                            "is_root": False,
                            "is_internal": False,
                            "internal_article_id": None,
                            "depth": current_depth + 1,
                        }

                    # Yönlü kenar: work_id → current_id
                    edges.append({
                        "source": work_id,
                        "target": current_id,
                        "depth": current_depth + 1,
                    })

                    if work_id not in visited:
                        visited.add(work_id)
                        next_level_ids.append(work_id)

            current_level_ids = next_level_ids

        # 4. Graf verisini oluştur
        graph_data = {
            "root_article_id": str(article.id),
            "root_openalex_id": root_id,
            "max_depth": depth,
            "nodes": list(nodes.values()),
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "computed_at": datetime.utcnow().isoformat(),
        }

        # 5. Redis cache'e kaydet
        try:
            await cache.set_citation_graph(article_id, depth, graph_data)
        except Exception as e:
            logger.error(f"Failed to cache citation graph for {article_id}: {e}")

        logger.info(
            "Citation graph olusturuldu",
            article_id=article_id,
            depth=depth,
            per_level=per_level,
            nodes=graph_data["node_count"],
            edges=graph_data["edge_count"],
        )
        return graph_data

    async def expand_node(
        self,
        openalex_id: str,
        depth: int = 1,
        max_per_level: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Verilen OpenAlex ID'li düğümden itibaren BFS ile alt graf oluşturur.
        Mevcut grafa merge edilmek üzere nodes ve edges döner.
        """
        depth = min(depth, settings.citation_graph_max_depth)
        base_per_level = min(
            max_per_level or settings.citation_max_per_level,
            settings.citation_max_per_level,
        )
        per_level = max(3, base_per_level // (2 ** max(0, depth - 1)))

        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        visited: Set[str] = {openalex_id}

        semaphore = asyncio.Semaphore(settings.citation_graph_concurrency)

        async def fetch_citing(node_id: str) -> Tuple[str, List[Dict[str, Any]]]:
            async with semaphore:
                try:
                    works = await openalex_client.get_citing_works(node_id, per_page=per_level)
                except Exception as e:
                    logger.warning(f"expand get_citing_works failed for {node_id}: {e}")
                    works = []
                return node_id, works

        current_level_ids: List[str] = [openalex_id]

        for current_depth in range(depth):
            if not current_level_ids:
                break

            level_results = await asyncio.gather(
                *[fetch_citing(nid) for nid in current_level_ids],
                return_exceptions=False,
            )

            next_level_ids: List[str] = []

            for current_id, citing_works in level_results:
                for work in citing_works[:per_level]:
                    work_id = work.get("id")
                    if not work_id:
                        continue

                    if work_id not in nodes:
                        nodes[work_id] = {
                            "id": work_id,
                            "title": work.get("title"),
                            "doi": work.get("doi"),
                            "cited_by_count": work.get("cited_by_count", 0),
                            "publication_year": work.get("publication_year"),
                            "is_root": False,
                            "is_internal": False,
                            "internal_article_id": None,
                            "depth": current_depth + 1,
                        }

                    edges.append({
                        "source": work_id,
                        "target": current_id,
                        "depth": current_depth + 1,
                    })

                    if work_id not in visited:
                        visited.add(work_id)
                        next_level_ids.append(work_id)

            current_level_ids = next_level_ids

        logger.info(
            f"Citation graph expanded: openalex_id={openalex_id} depth={depth} "
            f"nodes={len(nodes)} edges={len(edges)}"
        )

        return {
            "expanded_node_id": openalex_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }


# Singleton
citation_graph_service = CitationGraphService()
