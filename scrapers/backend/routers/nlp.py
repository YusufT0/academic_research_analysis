"""
NLP Router

Clustering, embedding ve benzerlik araması endpoint'leri
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.nlp_service import nlp_service
from utils.logger import get_logger

logger = get_logger('nlp_router')

router = APIRouter(prefix="/nlp", tags=["NLP & Clustering"])


# ============== Request/Response Schemas ==============

class TrainRequest(BaseModel):
    """Eğitim isteği"""
    model_version: Optional[str] = Field(None, description="Model versiyon etiketi (opsiyonel)")
    min_abstract_length: int = Field(50, description="Minimum abstract uzunluğu")


class TrainResponse(BaseModel):
    """Eğitim yanıtı"""
    status: str
    message: str
    model_version: Optional[str] = None
    total_articles: Optional[int] = None
    total_clusters: Optional[int] = None
    noise_count: Optional[int] = None
    auto_triggered: bool = False


class SearchResponse(BaseModel):
    """Arama yanıtı"""
    query: str
    model_version: str
    similarity_score: float
    cluster_id: Optional[int]
    cluster_label: Optional[str]
    total_in_cluster: Optional[int]
    articles: List[dict]


class ClusterSummary(BaseModel):
    """Cluster özeti"""
    id: str
    cluster_id: int
    label: Optional[str]
    article_count: int
    top_keywords: List[str]
    sample_titles: List[str]
    model_version: str


class StatusResponse(BaseModel):
    """Durum yanıtı"""
    has_trained_model: bool
    latest_model_version: Optional[str]
    latest_training_date: Optional[str]
    latest_stats: Optional[dict]
    is_training: bool
    running_version: Optional[str]
    cache_loaded: bool
    cached_version: Optional[str]
    # PKL model bilgileri
    pkl_model_available: bool = False
    pkl_model_loaded: bool = False
    pkl_model_path: Optional[str] = None


# ============== Endpoints ==============

@router.get("/status", response_model=StatusResponse, summary="NLP sistem durumunu getir")
async def get_nlp_status():
    """
    Mevcut NLP/Clustering sistem durumunu döndürür.
    
    - Eğitilmiş model var mı?
    - En son model versiyonu nedir?
    - Şu anda eğitim çalışıyor mu?
    """
    try:
        status = await nlp_service.get_status()
        return StatusResponse(**status)
    except Exception as e:
        logger.error(f"Status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train", response_model=TrainResponse, summary="Yeni clustering modeli eğit")
async def train_clustering(
    request: TrainRequest,
    background_tasks: BackgroundTasks
):
    """
    Veritabanındaki makalelerden yeni bir clustering modeli eğitir.
    
    - Tüm makalelerin abstract'larını alır
    - Embedding oluşturur
    - UMAP ile boyut indirger
    - HDBSCAN ile cluster'lar
    - Sonuçları DB'ye kaydeder
    
    **Not**: Bu işlem uzun sürebilir. Background task olarak çalışır.
    """
    try:
        # Önce çalışan bir eğitim var mı kontrol et
        status = await nlp_service.get_status()
        if status["is_training"]:
            raise HTTPException(
                status_code=409,
                detail=f"Bir eğitim zaten çalışıyor: {status['running_version']}"
            )
        
        # Eğitimi başlat
        result = await nlp_service.train_clustering(
            model_version=request.model_version,
            min_abstract_length=request.min_abstract_length
        )
        
        return TrainResponse(
            status="completed",
            message="Clustering model başarıyla eğitildi",
            model_version=result["model_version"],
            total_articles=result["total_articles"],
            total_clusters=result["total_clusters"],
            noise_count=result["noise_count"],
            auto_triggered=False
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=SearchResponse, summary="Benzer makaleleri ara")
async def search_similar_articles(
    query: str = Query(..., min_length=2, description="Arama sorgusu"),
    model_version: Optional[str] = Query(None, description="Model versiyonu (boş = en son)"),
    top_k: int = Query(10, ge=1, le=100, description="Döndürülecek makale sayısı"),
    auto_train: bool = Query(False, description="Analiz yoksa otomatik eğitim başlat")
):
    """
    Verilen sorguya benzer makaleleri bulur.
    
    - Query'yi embedding'e çevirir
    - En yakın cluster'ı bulur
    - O cluster'daki makaleleri döndürür
    
    **auto_train=true** ile analiz yoksa otomatik olarak eğitim başlatılır.
    """
    try:
        result = await nlp_service.search_similar(
            query=query,
            model_version=model_version,
            top_k=top_k,
            auto_train=auto_train
        )
        return SearchResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters", response_model=List[ClusterSummary], summary="Tüm cluster'ları listele")
async def list_clusters(
    model_version: Optional[str] = Query(None, description="Model versiyonu (boş = en son)"),
    include_noise: bool = Query(False, description="Noise cluster'ı dahil et")
):
    """
    Tüm cluster'ların özet bilgilerini döndürür.
    
    - Cluster ID ve etiketi
    - Makale sayısı
    - Top keywords
    - Örnek başlıklar
    """
    try:
        clusters = await nlp_service.get_clusters(
            model_version=model_version,
            include_noise=include_noise
        )
        return [ClusterSummary(**c) for c in clusters]
        
    except Exception as e:
        logger.error(f"List clusters error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters/{cluster_id}", summary="Cluster detayını getir")
async def get_cluster_detail(
    cluster_id: int,
    model_version: Optional[str] = Query(None, description="Model versiyonu (boş = en son)"),
    include_articles: bool = Query(True, description="Makaleleri dahil et"),
    article_limit: int = Query(50, ge=1, le=500, description="Makale limiti")
):
    """
    Belirli bir cluster'ın detaylı bilgilerini döndürür.
    
    - Cluster metadata
    - Opsiyonel: Cluster'daki makaleler
    """
    try:
        result = await nlp_service.get_cluster_detail(
            cluster_id=cluster_id,
            model_version=model_version,
            include_articles=include_articles,
            article_limit=article_limit
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Cluster bulunamadı")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cluster detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters/{cluster_id}/articles", summary="Cluster makalelerini getir")
async def get_cluster_articles(
    cluster_id: int,
    model_version: Optional[str] = Query(None, description="Model versiyonu (boş = en son)"),
    limit: int = Query(100, ge=1, le=500, description="Makale limiti"),
    skip: int = Query(0, ge=0, description="Atlanacak makale sayısı")
):
    """
    Belirli bir cluster'daki makaleleri sayfalı olarak döndürür.
    """
    try:
        result = await nlp_service.get_cluster_detail(
            cluster_id=cluster_id,
            model_version=model_version,
            include_articles=True,
            article_limit=limit + skip
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Cluster bulunamadı")
        
        articles = result.get("articles", [])[skip:skip + limit]
        
        return {
            "cluster_id": cluster_id,
            "total_count": result["article_count"],
            "returned_count": len(articles),
            "skip": skip,
            "limit": limit,
            "articles": articles
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cluster articles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/article/{article_id}/cluster", summary="Makalenin cluster'ını bul")
async def get_article_cluster(
    article_id: str,
    model_version: Optional[str] = Query(None, description="Model versiyonu (boş = en son)")
):
    """
    Belirli bir makalenin ait olduğu cluster'ı döndürür.
    """
    try:
        result = await nlp_service.get_article_cluster(
            article_id=article_id,
            model_version=model_version
        )
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail="Makale için cluster bulunamadı veya makale henüz işlenmemiş"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Article cluster error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", summary="Eğitim geçmişini getir")
async def get_training_history(
    limit: int = Query(10, ge=1, le=50, description="Kayıt limiti")
):
    """
    Geçmiş eğitim çalıştırmalarının listesini döndürür.
    
    - Model versiyonları
    - İstatistikler
    - Parametreler
    - Süreler
    """
    try:
        history = await nlp_service.get_training_history(limit=limit)
        return {
            "count": len(history),
            "runs": history
        }
        
    except Exception as e:
        logger.error(f"History error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Legacy Endpoint (Backward Compatibility) ==============

@router.get("/test_clustering", summary="[LEGACY] Model ile anahtar kelimeye benzer makaleleri çek")
async def legacy_test_clustering(
    keyword: str = Query(..., description="Arama yapılmak istenen anahtar kelime")
):
    """
    **[DEPRECATED]** Bu endpoint eski uyumluluk için korunmaktadır.
    Yeni projeler için `/nlp/search` endpoint'ini kullanın.
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Please provide a keyword.")
    
    try:
        result = await nlp_service.search_similar(query=keyword, top_k=50)
        
        # Eski format için dönüştür
        return {
            "status": "success",
            "similarity_rate": result["similarity_score"],
            "match_count": len(result["articles"]),
            "cluster_id": result["cluster_id"],
            "cluster_label": result["cluster_label"],
            "data": [a["title"] for a in result["articles"]]
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Legacy test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
