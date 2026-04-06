"""
Statistics Router
"""

from typing import Optional
from fastapi import APIRouter, Query

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.models import Journal, Issue, Article
from database.connection import get_database
from ..core.dependencies import get_scraper_manager
from ..services.cache_service import cache_service
from utils.logger import get_logger

logger = get_logger("stats_router")

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/", summary="Genel istatistikler")
async def get_general_stats():
    """Database ve scraper genel istatistikleri"""
    db = get_database()
    
    # Collection counts
    journal_count = await Journal.count()
    issue_count = await Issue.count()
    article_count = await Article.count()
    
    # Database stats
    db_stats = await db.get_statistics()
    
    # Scraper status
    manager = get_scraper_manager()
    scraper_status = manager.get_all_status()
    
    return {
        "database": {
            "journals": journal_count,
            "issues": issue_count,
            "articles": article_count,
            "data_size_mb": db_stats.get("data_size_mb", 0),
            "storage_size_mb": db_stats.get("storage_size_mb", 0),
        },
        "scrapers": {
            "ieee_status": scraper_status["ieee"]["status"],
            "sciencedirect_status": scraper_status["sciencedirect"]["status"],
            "acm_status": scraper_status["acm"]["status"],
            "any_running": scraper_status["any_running"],
        },
        "cache": await cache_service.get_cache_stats()
    }


@router.get("/journals", summary="Journal istatistikleri")
async def get_journal_stats():
    """Journal istatistikleri"""
    # Cache Check
    cached = await cache_service.get_search_results("stats_journals", {})
    if cached:
        logger.info("Cache HIT: stats journals")
        return cached

    # By source
    pipeline_source = [
        {
            "$group": {
                "_id": "$source_website",
                "count": {"$sum": 1},
                "total_articles": {"$sum": "$article_count"},
                "total_issues": {"$sum": "$issue_count"},
                "open_access_count": {"$sum": {"$cond": ["$open_access", 1, 0]}},
            }
        }
    ]
    
    collection = Journal.get_pymongo_collection()
    cursor = collection.aggregate(pipeline_source)
    by_source = await cursor.to_list(length=None)
    
    # By publisher
    pipeline_publisher = [
        {
            "$group": {
                "_id": "$publisher",
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    
    cursor = collection.aggregate(pipeline_publisher)
    by_publisher = await cursor.to_list(length=None)
    
    result = {
        "total": await Journal.count(),
        "by_source": {item["_id"]: item for item in by_source},
        "top_publishers": by_publisher,
    }
    await cache_service.set_search_results("stats_journals", {}, result)
    return result


@router.get("/articles", summary="Article istatistikleri")
async def get_article_stats():
    """Article istatistikleri"""
    # Cache Check
    cached = await cache_service.get_search_results("stats_articles", {})
    if cached:
        logger.info("Cache HIT: stats articles")
        return cached

    collection = Article.get_pymongo_collection()
    
    # By source
    pipeline_source = [
        {
            "$group": {
                "_id": "$source_website",
                "count": {"$sum": 1},
                "with_abstract": {"$sum": {"$cond": [{"$ne": ["$abstract", None]}, 1, 0]}},
                "with_doi": {"$sum": {"$cond": [{"$ne": ["$doi", None]}, 1, 0]}},
                "open_access": {"$sum": {"$cond": ["$open_access", 1, 0]}},
            }
        }
    ]
    
    cursor = collection.aggregate(pipeline_source)
    by_source = await cursor.to_list(length=None)
    
    # By year
    pipeline_year = [
        {"$match": {"publication_year": {"$ne": None}}},
        {
            "$group": {
                "_id": "$publication_year",
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": -1}},
        {"$limit": 10}
    ]
    
    cursor = collection.aggregate(pipeline_year)
    by_year = await cursor.to_list(length=None)
    
    # Top keywords
    pipeline_keywords = [
        {"$unwind": "$keywords"},
        {
            "$group": {
                "_id": "$keywords",
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 20}
    ]
    
    cursor = collection.aggregate(pipeline_keywords)
    top_keywords = await cursor.to_list(length=None)
    
    # Top authors
    pipeline_authors = [
        {"$unwind": "$authors"},
        {
            "$group": {
                "_id": "$authors",
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 20}
    ]
    
    cursor = collection.aggregate(pipeline_authors)
    top_authors = await cursor.to_list(length=None)
    
    result = {
        "total": await Article.count(),
        "by_source": {item["_id"]: item for item in by_source},
        "by_year": {str(item["_id"]): item["count"] for item in by_year},
        "top_keywords": top_keywords,
        "top_authors": top_authors,
    }
    
    await cache_service.set_search_results("stats_articles", {}, result)
    return result


@router.get("/citations", summary="Atıf istatistikleri")
async def get_citation_stats():
    """Atıf (Citation) yoğunlukları ve özet istatistikleri"""
    cached = await cache_service.get_search_results("stats_citations", {})
    if cached:
        logger.info("Cache HIT: stats citations")
        return cached

    # Makale Atıf Dağılımı (Citation Distribution)
    article_coll = Article.get_pymongo_collection()
    
    distribution_pipeline = [
        {
            "$bucket": {
                "groupBy": {"$ifNull": ["$citation_count", 0]},
                "boundaries": [0, 1, 5, 20, 50, 100],
                "default": "100+",
                "output": {"count": {"$sum": 1}}
            }
        }
    ]
    dist_cursor = article_coll.aggregate(distribution_pipeline)
    distribution_raw = await dist_cursor.to_list(length=None)
    
    # En Çok Atıf Alan Makaleler
    top_articles_pipeline = [
        {"$sort": {"citation_count": -1}},
        {"$limit": 10},
        {"$project": {"title": 1, "authors": 1, "citation_count": 1, "publication_year": 1}}
    ]
    top_articles_cursor = article_coll.aggregate(top_articles_pipeline)
    top_articles = await top_articles_cursor.to_list(length=None)

    # Yıllara Göre Toplam Atıf Yoğunluğu
    pub_year_pipeline = [
        {"$match": {"publication_year": {"$ne": None}}},
        {
            "$group": {
                "_id": "$publication_year",
                "total_citations": {"$sum": {"$ifNull": ["$citation_count", 0]}},
                "article_count": {"$sum": 1}
            }
        },
        {"$sort": {"_id": -1}},
        {"$limit": 15},
        {"$sort": {"_id": 1}}
    ]
    pub_year_cursor = article_coll.aggregate(pub_year_pipeline)
    pub_year_citations = await pub_year_cursor.to_list(length=None)

    journal_coll = Journal.get_pymongo_collection()

    # H-Index'i en yüksek dergiler
    top_h_index_pipeline = [
        {"$match": {"h_index": {"$ne": None}}},
        {"$sort": {"h_index": -1}},
        {"$limit": 10},
        {"$project": {"name": 1, "h_index": 1, "i10_index": 1, "total_citation_count": 1}}
    ]
    top_h_index_cursor = journal_coll.aggregate(top_h_index_pipeline)
    top_h_index_journals = await top_h_index_cursor.to_list(length=None)

    result = {
        "citation_distribution": distribution_raw,
        "top_cited_articles": [{**a, "_id": str(a["_id"])} for a in top_articles],
        "citations_by_pub_year": pub_year_citations,
        "top_h_index_journals": [{**j, "_id": str(j["_id"])} for j in top_h_index_journals]
    }

    await cache_service.set_search_results("stats_citations", {}, result)
    return result


@router.get("/scraper", summary="Scraper istatistikleri")
async def get_scraper_stats():
    """Scraper ilerleme ve istatistikleri"""
    manager = get_scraper_manager()
    
    ieee = manager.get_ieee_status()
    sd = manager.get_sciencedirect_status()
    acm = manager.get_acm_status()
    
    return {
        "ieee": {
            "status": ieee["status"],
            "progress_percent": ieee["progress_percent"],
            "journals_scraped": ieee["journals_scraped"],
            "issues_scraped": ieee["issues_scraped"],
            "articles_scraped": ieee["articles_scraped"],
            "articles_updated": ieee["articles_updated"],
            "errors_count": ieee["errors_count"],
            "elapsed_seconds": ieee["elapsed_seconds"],
            "current_journal": ieee["current_journal"],
        },
        "sciencedirect": {
            "status": sd["status"],
            "progress_percent": sd["progress_percent"],
            "journals_scraped": sd["journals_scraped"],
            "issues_scraped": sd["issues_scraped"],
            "articles_scraped": sd["articles_scraped"],
            "articles_updated": sd["articles_updated"],
            "errors_count": sd["errors_count"],
            "elapsed_seconds": sd["elapsed_seconds"],
            "current_journal": sd["current_journal"],
        },
        "acm": {
            "status": acm["status"],
            "progress_percent": acm["progress_percent"],
            "journals_scraped": acm["journals_scraped"],
            "issues_scraped": acm["issues_scraped"],
            "articles_scraped": acm["articles_scraped"],
            "articles_updated": acm["articles_updated"],
            "errors_count": acm["errors_count"],
            "elapsed_seconds": acm["elapsed_seconds"],
            "current_journal": acm["current_journal"],
        },
        "totals": {
            "journals_scraped": ieee["journals_scraped"] + sd["journals_scraped"] + acm["journals_scraped"],
            "issues_scraped": ieee["issues_scraped"] + sd["issues_scraped"] + acm["issues_scraped"],
            "articles_scraped": ieee["articles_scraped"] + sd["articles_scraped"] + acm["articles_scraped"],
            "errors_count": ieee["errors_count"] + sd["errors_count"] + acm["errors_count"],
        }
    }

@router.get("/cache", summary="Cache istatistikleri")
async def get_cache_stats():
    """Redis cache istatistikleri"""
    stats = await cache_service.get_cache_stats()
    return stats


@router.delete("/cache", summary="Cache temizle")
async def clear_cache(pattern: Optional[str] = Query(None, description="Silinecek key pattern (örn: 'search:*')")):
    """
    Cache temizleme
    
    - pattern belirtilmezse: Tüm cache temizlenir
    - pattern belirtilirse: Sadece o pattern'e uyan key'ler silinir
    """
    if pattern:
        deleted = await cache_service.invalidate_pattern(pattern)
        return {"message": f"Pattern '{pattern}' ile eşleşen {deleted} key silindi"}
    else:
        deleted = await cache_service.invalidate_pattern("*")
        return {"message": f"Tüm cache temizlendi ({deleted} key silindi)"}
