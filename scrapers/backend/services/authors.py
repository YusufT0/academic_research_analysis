"""
Authors Service
"""

from typing import Dict, Any, List, Optional
from collections import Counter
from database.models import Article
from backend.services.cache_service import cache_service
from backend.services.openalex.client import openalex_client
from utils.logger import get_logger

logger = get_logger('authors_service')

class AuthorsService:
    async def get_authors_list(
        self, 
        page: int = 1, 
        page_size: int = 20, 
        sort_by: str = "article_count_desc",
        search: Optional[str] = None,
        min_articles: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Geleneksel veritabanı aggregation kullanarak yazar listesi döndürür.
        Redis'te önbelleklenir. Arama, filtreleme ve sıralama destekler.
        """
        # Cache anahtarını dinamik üretiyoruz
        search_part = f"_q_{search.lower().replace(' ', '_')}" if search else ""
        min_art_part = f"_min_{min_articles}" if min_articles else ""
        cache_key = f"list_p{page}_s{page_size}_{sort_by}{search_part}{min_art_part}"
        redis_key = cache_service._make_key("authors", cache_key)
        
        cached = await cache_service.get(redis_key)
        if cached:
            return cached

        skip = (page - 1) * page_size
        
        # Sort ayarları
        sort_field = "count"
        sort_dir = -1
        if sort_by == "article_count_asc":
            sort_dir = 1
        elif sort_by == "name_asc":
            sort_field = "_id"
            sort_dir = 1
        elif sort_by == "name_desc":
            sort_field = "_id"
            sort_dir = -1

        pipeline = []
        
        # 1. Başlangıç Filtresi (Tüm dokümanları taramayı azaltmak için)
        if search:
            pipeline.append({"$match": {"authors": {"$regex": search, "$options": "i"}}})
            
        # 2. Array'i aç
        pipeline.append({"$unwind": "$authors"})
        
        # 3. Yazar bazlı filtreleme (Sadece aranan yazarı tut, makaledeki diğer ortak yazarları ele)
        if search:
            pipeline.append({"$match": {"authors": {"$regex": search, "$options": "i"}}})
            
        # 4. Gruplama
        pipeline.append(
            {"$group": {
                "_id": "$authors",
                "count": {"$sum": 1},
                "journal_names": {"$addToSet": "$journal_name"},
                "keywords": {"$push": "$keywords"},
            }}
        )
        
        # 5. Gruplama sonrası limit (Having)
        if min_articles and min_articles > 1:
            pipeline.append({"$match": {"count": {"$gte": min_articles}}})
            
        # 6. Sıralama ve Pagination Facet
        pipeline.extend([
            {"$sort": {sort_field: sort_dir}},
            {"$facet": {
                "metadata": [{"$count": "total"}],
                "data": [{"$skip": skip}, {"$limit": page_size}]
            }}
        ])

        collection = Article.get_pymongo_collection()
        cursor = collection.aggregate(pipeline)
        result = await cursor.to_list(length=None)
        
        try:
            total = result[0]["metadata"][0]["total"] if result[0]["metadata"] else 0
            authors = result[0]["data"]
        except Exception:
            total = 0
            authors = []

        formatted_authors = []
        for a in authors:
            all_keywords = [item for sublist in a.get("keywords", []) for item in sublist]
            top_keywords = [k for k, _ in Counter(all_keywords).most_common(5)]
            
            formatted_authors.append({
                "name": a["_id"],
                "article_count": a["count"],
                "journals": list(a.get("journal_names", []))[:3],
                "top_keywords": top_keywords,
            })

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        response = {
            "items": formatted_authors,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        # Cache for 1 hour
        await cache_service.set(redis_key, response, ttl=3600)
        return response

    async def get_author_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Belirli bir yazarın detaylarını DB ve OpenAlex üzerinden derler.
        """
        redis_key = cache_service._make_key("author", name)
        cached = await cache_service.get(redis_key)
        if cached:
            return cached

        # 1. DB'den makale analizi (Aggregation)
        pipeline = [
            {"$match": {"authors": name}},
            {"$facet": {
                "articles": [
                    {"$sort": {"publication_year": -1}}, # newest first
                    {"$project": {
                        "_id": 0,
                        "id": {"$toString": "$_id"},
                        "title": 1, 
                        "journal_name": 1, 
                        "publication_year": 1, 
                        "citation_count": 1,
                        "doi": 1,
                        "source_website": 1,
                        "url": 1
                    }}
                ],
                "stats": [
                    {"$unwind": "$keywords"},
                    {"$group": {
                        "_id": "$keywords",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 5}
                ],
                "co_authors": [
                    {"$unwind": "$authors"},
                    {"$match": {"authors": {"$ne": name}}},
                    {"$group": {
                        "_id": "$authors",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 10}
                ]
            }}
        ]

        try:
            collection = Article.get_pymongo_collection()
            cursor = collection.aggregate(pipeline)
            result = await cursor.to_list(length=None)
            if not result or not result[0].get("articles"):
                return None # Author not found in DB
                
            db_data = result[0]
            articles = db_data.get("articles", [])
            top_keywords = [k["_id"] for k in db_data.get("stats", [])]
            co_authors = [{"name": c["_id"], "count": c["count"]} for c in db_data.get("co_authors", [])]
        except Exception as e:
            logger.error(f"Error fetching author from DB: {e}")
            return None

        # 2. OpenAlex Verileri
        openalex_data = None
        target_author_id = None
        
        # 2.1 Anchor Matching: Kendi veritabanımızdaki makalesinden DOI üzerinden yazar profili ID'si ayıklama
        # Başarı oranını artırmak için, tek bir makale yerine maksimum 3 farklı DOI dener
        anchor_dois = [a.get("doi") for a in articles if a.get("doi")][:3]
        
        for anchor_doi in anchor_dois:
            if target_author_id:
                break # Zaten ID bulduysak diğer DOI'leri denemeye gerek yok
                
            try:
                oa_work = await openalex_client.get_work_by_doi(anchor_doi)
                if oa_work and "authorships" in oa_work:
                    for authorship in oa_work.get("authorships", []):
                        author_obj = authorship.get("author", {})
                        display_name = author_obj.get("display_name", "")
                        # İsim eşleştirmesi
                        if name.lower() in display_name.lower() or display_name.lower() in name.lower():
                            target_author_id = author_obj.get("id")
                            logger.info(f"True Author ID matched via anchor DOI ({anchor_doi}): {target_author_id}")
                            break
            except Exception as e:
                logger.warning(f"Failed to find anchor work for {name} with DOI {anchor_doi}: {e}")

        # 2.2 Verileri Çekme
        try:
            if target_author_id:
                openalex_data = await openalex_client.get_author_by_id(target_author_id)
            
            # Eğer DOI ile yazar ID çıkartılamamışsa veya açık profil bulunamadıysa (Fallback)
            if not openalex_data:
                logger.info(f"Fetching author {name} by name as fallback...")
                openalex_data = await openalex_client.search_author_by_name(name)
        except Exception as e:
            logger.warning(f"Failed to fetch OpenAlex for {name}: {e}")

        oa_stats, affiliations, topics, counts_by_year, ids = {}, [], [], [], {}
        oa_works_count, oa_cited_by_count = 0, 0
        
        if openalex_data:
            summary = openalex_data.get("summary_stats", {})
            oa_stats = {
                "h_index": summary.get("h_index"),
                "i10_index": summary.get("i10_index"),
                "2yr_mean_citedness": summary.get("2yr_mean_citedness")
            }
            
            oa_works_count = openalex_data.get("works_count", 0)
            oa_cited_by_count = openalex_data.get("cited_by_count", 0)
            counts_by_year = openalex_data.get("counts_by_year", [])
            ids = openalex_data.get("ids", {})
            
            for aff in openalex_data.get("affiliations", []):
                inst = aff.get("institution", {})
                if inst:
                    affiliations.append({
                        "name": inst.get("display_name"),
                        "country_code": inst.get("country_code"),
                        "years": aff.get("years", [])
                    })

            for topic in openalex_data.get("topics", [])[:5]:
                topics.append(topic.get("display_name"))

        profile = {
            "name": name,
            "db_stats": {
                "article_count": len(articles),
                "top_keywords": top_keywords,
                "co_authors": co_authors
            },
            "openalex_metrics": {
                "works_count": oa_works_count,
                "cited_by_count": oa_cited_by_count,
                "h_index": oa_stats.get("h_index"),
                "i10_index": oa_stats.get("i10_index"),
                "ids": ids,
                "topics": topics,
                "affiliations": affiliations,
                "counts_by_year": counts_by_year
            },
            "articles": articles
        }

        # Cache it heavily for 1 week as it's a very heavy operation to build this
        await cache_service.set(redis_key, profile, ttl=604800)
        return profile

    async def get_author_articles(self, name: str, page: int = 1, page_size: int = 15) -> Dict[str, Any]:
        """
        Geleneksel veritabanından yazarın makale listesini paginated olarak döner.
        """
        cache_key = f"{name}_p{page}_s{page_size}"
        redis_key = cache_service._make_key("author_articles", cache_key)
        
        cached = await cache_service.get(redis_key)
        if cached:
            return cached

        skip = (page - 1) * page_size
        pipeline = [
            {"$match": {"authors": name}},
            {"$facet": {
                "metadata": [{"$count": "total"}],
                "data": [
                    {"$sort": {"publication_year": -1}},
                    {"$skip": skip},
                    {"$limit": page_size},
                    {"$project": {
                        "_id": 0,
                        "id": {"$toString": "$_id"},
                        "title": 1, 
                        "journal_name": 1, 
                        "publication_year": 1, 
                        "citation_count": 1,
                        "doi": 1,
                        "source_website": 1,
                        "url": 1
                    }}
                ]
            }}
        ]

        try:
            collection = Article.get_pymongo_collection()
            cursor = collection.aggregate(pipeline)
            result = await cursor.to_list(length=None)
            
            total = result[0]["metadata"][0]["total"] if result[0].get("metadata") else 0
            articles = result[0].get("data", [])
        except Exception as e:
            logger.error(f"Error fetching author articles from DB: {e}")
            total = 0
            articles = []

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        response = {
            "items": articles,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        await cache_service.set(redis_key, response, ttl=604800)
        return response

authors_service = AuthorsService()
