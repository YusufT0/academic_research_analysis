"""
Elasticsearch Service

Full-text search, autocomplete ve faceted arama.

Kullanım:
    es = ElasticsearchService()
    await es.connect()
    await es.index_article(article_data)
    results = await es.search("machine learning", filters={"source": "ieee"})
"""

import os
from typing import Optional, List, Dict, Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from utils.logger import get_logger

logger = get_logger("elasticsearch")

# Index mapping for articles
ARTICLE_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "article_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "stop", "snowball"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "title": {"type": "text", "analyzer": "article_analyzer"},
            "abstract": {"type": "text", "analyzer": "article_analyzer"},
            "keywords": {"type": "keyword"},
            "authors": {"type": "keyword"},
            "source_website": {"type": "keyword"},
            "publication_year": {"type": "integer"},
            "journal_name": {"type": "keyword"},
            "journal_id": {"type": "keyword"},
            "issue_id": {"type": "keyword"},
            "doi": {"type": "keyword"},
            "url": {"type": "keyword"},
            "article_type": {"type": "keyword"},
            "open_access": {"type": "boolean"},
            "citation_count": {"type": "integer"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
}


class ElasticsearchService:
    """Elasticsearch full-text search service"""
    
    def __init__(self):
        self._client: Optional[AsyncElasticsearch] = None
        from backend.core.config import settings
        self._index_prefix = settings.elasticsearch_index_prefix
        self._url = settings.elasticsearch_url
    
    @property
    def articles_index(self) -> str:
        return f"{self._index_prefix}_articles"
    
    @property
    def is_connected(self) -> bool:
        return self._client is not None
    
    async def connect(self):
        """Elasticsearch'e bağlan ve index'leri oluştur"""
        try:
            self._client = AsyncElasticsearch(
                [self._url],
                request_timeout=30,
                retry_on_timeout=True,
                max_retries=3,
            )
            
            # Bağlantı testi
            info = await self._client.info()
            logger.info(
                "Elasticsearch connected",
                version=info["version"]["number"],
                cluster=info["cluster_name"],
            )
            
            # Index'leri oluştur
            await self.create_indices()
            
        except Exception as e:
            logger.error("Elasticsearch connection failed", error=str(e))
            self._client = None
    
    async def close(self):
        """Bağlantıyı kapat"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Elasticsearch connection closed")
    
    async def create_indices(self):
        """Index'leri oluştur (yoksa)"""
        if not self._client:
            return
        
        try:
            exists = await self._client.indices.exists(index=self.articles_index)
            if not exists:
                await self._client.indices.create(
                    index=self.articles_index,
                    body=ARTICLE_INDEX_MAPPING,
                )
                logger.info("Elasticsearch index created", index=self.articles_index)
            else:
                logger.info("Elasticsearch index exists", index=self.articles_index)
        except Exception as e:
            logger.error("Index creation failed", error=str(e))
    
    async def index_article(self, article_data: Dict[str, Any]) -> bool:
        """Tek makale indexle"""
        if not self._client:
            return False
        
        try:
            doc_id = article_data.get("id", article_data.get("_id"))
            if not doc_id:
                return False
            
            doc = self._prepare_document(article_data)
            
            await self._client.index(
                index=self.articles_index,
                id=str(doc_id),
                document=doc,
            )
            return True
        except Exception as e:
            logger.error("Article index failed", article_id=str(doc_id), error=str(e))
            return False
    
    async def bulk_index(self, articles: List[Dict[str, Any]]) -> int:
        """Toplu makale indexleme"""
        if not self._client or not articles:
            return 0
        
        actions = []
        for article in articles:
            doc_id = article.get("id", article.get("_id"))
            if not doc_id:
                continue
            
            doc = self._prepare_document(article)
            actions.append({
                "_index": self.articles_index,
                "_id": str(doc_id),
                "_source": doc,
            })
        
        if not actions:
            return 0
        
        try:
            success, errors = await async_bulk(
                self._client,
                actions,
                raise_on_error=False,
            )
            if errors:
                logger.warning("Bulk index partial failures", 
                             success=success, errors=len(errors))
                # Hatanın detayını görmek için ilk hatayı logla
                logger.error("İlk hata detayı:", first_error=str(errors[0]))
            else:
                logger.info("Bulk index completed", count=success)
            return success
        except Exception as e:
            logger.error("Bulk index failed", error=str(e))
            return 0
    
    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Full-text arama + filtreler"""
        if not self._client:
            return {"items": [], "total": 0, "query": query}
        
        # Build ES query
        must = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "abstract^2", "keywords^2", "authors"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]
        
        filter_clauses = []
        if filters:
            if "source_website" in filters:
                filter_clauses.append({"term": {"source_website": filters["source_website"]}})
            if "publication_year" in filters:
                filter_clauses.append({"term": {"publication_year": filters["publication_year"]}})
            if "journal_name" in filters:
                filter_clauses.append({"term": {"journal_name": filters["journal_name"]}})
            if "open_access" in filters:
                filter_clauses.append({"term": {"open_access": filters["open_access"]}})
        
        body = {
            "query": {
                "bool": {
                    "must": must,
                    "filter": filter_clauses,
                }
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "highlight": {
                "fields": {
                    "title": {"fragment_size": 200},
                    "abstract": {"fragment_size": 300},
                },
            },
            "aggs": {
                "sources": {"terms": {"field": "source_website", "size": 10}},
                "years": {"terms": {"field": "publication_year", "size": 20, "order": {"_key": "desc"}}},
                "journals": {"terms": {"field": "journal_name", "size": 20}},
            },
        }
        
        try:
            result = await self._client.search(index=self.articles_index, body=body)
            
            hits = result["hits"]
            items = []
            for hit in hits["hits"]:
                item = hit["_source"]
                item["id"] = hit["_id"]  # Frontend key prop mapping
                item["_id"] = hit["_id"]
                item["_score"] = hit["_score"]
                if "highlight" in hit:
                    item["highlights"] = hit["highlight"]
                items.append(item)
            
            total = hits["total"]["value"] if isinstance(hits["total"], dict) else hits["total"]
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            
            # Frontend: SearchFacetBucket ({key: string, count: number}) dönüşümü
            aggs = result.get("aggregations", {})
            facets = {}
            if aggs:
                if "sources" in aggs:
                    facets["sources"] = [{"key": str(b["key"]), "count": b["doc_count"]} for b in aggs["sources"].get("buckets", [])]
                if "years" in aggs:
                    facets["years"] = [{"key": str(b["key"]), "count": b["doc_count"]} for b in aggs["years"].get("buckets", [])]
                if "journals" in aggs:
                    facets["journals"] = [{"key": str(b["key"]), "count": b["doc_count"]} for b in aggs["journals"].get("buckets", [])]
            
            return {
                "items": items,
                "total": total,
                "query": query,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "facets": facets,
            }
        except Exception as e:
            logger.error("Search failed", query=query, error=str(e))
            return {"items": [], "total": 0, "query": query, "error": str(e)}
    
    async def suggest(self, prefix: str, limit: int = 10) -> List[str]:
        """Autocomplete önerileri"""
        if not self._client or not prefix:
            return []
        
        try:
            result = await self._client.search(
                index=self.articles_index,
                body={
                    "query": {
                        "multi_match": {
                            "query": prefix,
                            "fields": ["title"],
                            "type": "phrase_prefix",
                        }
                    },
                    "size": limit,
                    "_source": ["title"],
                },
            )
            
            return [hit["_source"]["title"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.error("Suggest failed", prefix=prefix, error=str(e))
            return []
    
    async def suggest_journals(self, prefix: str, limit: int = 15) -> List[str]:
        """Dergi adı autocomplete — prefix eşleşmesi (case-insensitive)"""
        if not self._client or not prefix:
            return []

        try:
            result = await self._client.search(
                index=self.articles_index,
                body={
                    "size": 0,
                    "query": {
                        "wildcard": {
                            "journal_name": {
                                "value": f"*{prefix}*",
                                "case_insensitive": True,
                            }
                        }
                    },
                    "aggs": {
                        "journal_names": {
                            "terms": {
                                "field": "journal_name",
                                "size": limit,
                            }
                        }
                    },
                },
            )
            buckets = result.get("aggregations", {}).get("journal_names", {}).get("buckets", [])
            return [b["key"] for b in buckets]
        except Exception as e:
            logger.error("Journal suggest failed", prefix=prefix, error=str(e))
            return []

    async def get_facets(self) -> Dict[str, Any]:
        """Aggregation bazlı filtreler"""
        if not self._client:
            return {}
        
        try:
            result = await self._client.search(
                index=self.articles_index,
                body={
                    "size": 0,
                    "aggs": {
                        "sources": {"terms": {"field": "source_website", "size": 20}},
                        "years": {"terms": {"field": "publication_year", "size": 30, "order": {"_key": "desc"}}},
                        "journals": {"terms": {"field": "journal_name", "size": 50}},
                        "article_types": {"terms": {"field": "article_type", "size": 20}},
                        "top_keywords": {"terms": {"field": "keywords", "size": 50}},
                        "top_authors": {"terms": {"field": "authors", "size": 50}},
                    },
                },
            )
            return result.get("aggregations", {})
        except Exception as e:
            logger.error("Facets failed", error=str(e))
            return {}
    
    def _prepare_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Makale verisini ES document formatına dönüştür"""
        from datetime import datetime
        doc = {}
        
        # Kopyalanacak alanlar
        fields = [
            "title", "abstract", "keywords", "authors",
            "source_website", "publication_year", "journal_name",
            "journal_id", "issue_id", "doi", "url",
            "article_type", "open_access", "citation_count",
            "created_at", "updated_at",
        ]
        
        for field in fields:
            if field in data and data[field] is not None:
                val = data[field]
                # ObjectId'leri string'e çevir
                if hasattr(val, "__str__") and not isinstance(val, (str, int, float, bool, list, datetime)):
                    val = str(val)
                # Datetime nesnelerini ISO formatına çevir (T ayracı zorunlu — ES strict_date_optional_time)
                if isinstance(val, datetime):
                    val = val.isoformat()
                # Stream üzerinden string olarak gelen tarih alanlarını düzelt:
                # "2026-04-04 12:48:59.958383" → "2026-04-04T12:48:59.958383"
                if field in ("created_at", "updated_at", "scraped_at") and isinstance(val, str):
                    val = val.replace(" ", "T", 1)
                doc[field] = val
        
        return doc


# Global instance
elasticsearch_service = ElasticsearchService()
