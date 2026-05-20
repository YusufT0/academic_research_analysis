"""
NLP Router

Clustering, embedding ve benzerlik araması endpoint'leri
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.nlp_service import nlp_service
from backend.services.cache_service import cache_service
from backend.core.config import settings
from database.repositories.analysis_run_repository import AnalysisRunRepository
from utils.logger import get_logger

logger = get_logger("nlp_router")

router = APIRouter(prefix="/nlp", tags=["NLP & Clustering"])


# ============== Request/Response Schemas ==============


class TrainRequest(BaseModel):
    """Eğitim isteği"""

    model_version: Optional[str] = Field(
        None, description="Model versiyon etiketi (opsiyonel)"
    )
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
    centroid: float
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


class ModelVersionsResponse(BaseModel):
    """Model versiyon listesi yanıtı"""
    latest_model_version: Optional[str]
    model_versions: List[str]


# ============== Endpoints ==============


@router.get(
    "/status", response_model=StatusResponse, summary="NLP sistem durumunu getir"
)
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


@router.get("/model_versions", response_model=ModelVersionsResponse, summary="Kullanılabilir NLP model versiyonlarını getir")
async def get_nlp_model_versions():
    """
    Trend analizinde veya artırımlı eğitimde seçilebilecek model versiyonlarını döndürür.
    DB'deki tamamlanmış analizler ve diskteki joblib dosyaları birlikte dikkate alınır.
    """
    try:
        status = await nlp_service.get_status()
        latest_model_version = status.get("latest_model_version")

        repo = AnalysisRunRepository()
        completed_runs = await repo.get_history(limit=200, status="completed")
        db_versions = [run.model_version for run in completed_runs if run.model_version]

        models_dir = Path(__file__).parent.parent.parent / "nlp_models"
        fs_versions: List[str] = []
        if models_dir.exists():
            umap_versions = {
                p.stem.replace("umap_", "")
                for p in models_dir.glob("umap_*.joblib")
            }
            hdbscan_versions = {
                p.stem.replace("hdbscan_all_", "")
                for p in models_dir.glob("hdbscan_all_*.joblib")
            }
            fs_versions = sorted(umap_versions & hdbscan_versions, reverse=True)

        ordered_versions: List[str] = []

        def _add_version(version: Optional[str]):
            if version and version not in ordered_versions:
                ordered_versions.append(version)

        _add_version(latest_model_version)
        for version in db_versions:
            _add_version(version)
        for version in fs_versions:
            _add_version(version)

        return ModelVersionsResponse(
            latest_model_version=latest_model_version,
            model_versions=ordered_versions,
        )
    except Exception as e:
        logger.error(f"Model versions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/train_incremental", summary= "Add to the model existing.")
async def add_new_articles(
    model_version: Optional[str] = Query(None, description="Model version"),
    min_abstract_length: Optional[int] = Query(
        50, description="Minimum abstract length"
    ),
):
    try:
        return await nlp_service.assign_new_articles(
            model_version=model_version, min_abstract_length=min_abstract_length
        )
    except Exception as e:
        logger.error(f"Incremental training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── In-memory task store for parallel journal analysis ──────────────────────
_analysis_tasks: Dict[str, Dict[str, Any]] = {}


def _make_step(status: str = "pending", message: str = "") -> Dict[str, Any]:
    return {"status": status, "message": message}


def _cleanup_tasks() -> None:
    if len(_analysis_tasks) > 100:
        done_keys = [k for k, v in _analysis_tasks.items() if v["status"] in ("done", "error")]
        for k in done_keys[: len(done_keys) // 2]:
            _analysis_tasks.pop(k, None)


async def _run_journal_analysis(
    task_id: str,
    jid: Any,
    model_version: Optional[str],
    min_abstract_length: int,
) -> None:
    task = _analysis_tasks[task_id]

    async def run_cluster_update() -> None:
        step = task["steps"]["cluster_update"]
        step["status"] = "running"
        step["message"] = "Makaleler kümelerine atanıyor..."
        try:
            result = await nlp_service.assign_new_articles(
                model_version=model_version,
                min_abstract_length=min_abstract_length,
                journal_ids=[jid],
            )
            result.setdefault("affected_clusters", [])
            task["result"] = result
            step["status"] = "done"
            step["message"] = f"{result.get('assigned', 0)} makale atandı"
        except Exception as exc:
            step["status"] = "error"
            step["message"] = str(exc)
            logger.error(f"cluster_update step error: {exc}")

    async def run_openalex() -> None:
        step = task["steps"]["openalex"]
        step["status"] = "running"
        step["message"] = "OpenAlex atıf verileri güncelleniyor..."
        try:
            from database.models import Article
            from backend.services.openalex.citation_service import citation_service as _cs
            articles = await Article.find({"journal_id": jid}).to_list()
            if articles:
                updated = await _cs.update_articles_citations_bulk(articles)
                step["status"] = "done"
                step["message"] = f"{updated} makale güncellendi"
            else:
                step["status"] = "done"
                step["message"] = "İşlenecek makale bulunamadı"
        except Exception as exc:
            step["status"] = "error"
            step["message"] = str(exc)
            logger.error(f"openalex step error: {exc}")

    async def run_elasticsearch() -> None:
        step = task["steps"]["elasticsearch"]
        step["status"] = "running"
        step["message"] = "Elasticsearch'e indexleniyor..."
        try:
            from database.models import Article
            from backend.services.elasticsearch_service import elasticsearch_service as _es
            articles = await Article.find({"journal_id": jid}).to_list()
            if articles:
                dicts = []
                for a in articles:
                    d = a.model_dump()
                    d["id"] = str(a.id)
                    if a.journal_id:
                        d["journal_id"] = str(a.journal_id)
                    if a.issue_id:
                        d["issue_id"] = str(a.issue_id)
                    dicts.append(d)
                indexed = await _es.bulk_index(dicts)
                step["status"] = "done"
                step["message"] = f"{indexed} makale indexlendi"
            else:
                step["status"] = "done"
                step["message"] = "İşlenecek makale bulunamadı"
        except Exception as exc:
            step["status"] = "error"
            step["message"] = str(exc)
            logger.error(f"elasticsearch step error: {exc}")

    await asyncio.gather(run_cluster_update(), run_openalex(), run_elasticsearch())

    all_statuses = [s["status"] for s in task["steps"].values()]
    task["status"] = "done" if all(s != "error" for s in all_statuses) else "done_with_errors"


class StartAnalysisResponse(BaseModel):
    task_id: str
    status: str


class AnalysisProgressResponse(BaseModel):
    task_id: str
    status: str
    steps: Dict[str, Dict[str, str]]
    result: Optional[dict] = None
    error: Optional[str] = None


class ActiveJournalAnalysisResponse(BaseModel):
    found: bool
    task_id: Optional[str] = None
    status: Optional[str] = None
    journal_id: Optional[str] = None
    model_version: Optional[str] = None
    started_at: Optional[str] = None


@router.post("/assign_for_journal", response_model=StartAnalysisResponse, summary="Belirtilen journal için paralel analiz başlat")
async def assign_for_journal(
    journal_id: str = Query(..., description="Hedef journal'ın MongoDB ObjectId'si"),
    model_version: Optional[str] = Query(None),
    min_abstract_length: int = Query(50),
):
    from beanie import PydanticObjectId as ObjId
    try:
        jid = ObjId(journal_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz journal_id formatı")

    journal_id_str = str(jid)

    # Aynı journal için halihazırda çalışan bir görev varsa onu döndür (idempotent davranış)
    for task in _analysis_tasks.values():
        if task.get("status") != "running":
            continue
        if task.get("journal_id") != journal_id_str:
            continue
        if model_version is not None and task.get("model_version") != model_version:
            continue
        return StartAnalysisResponse(task_id=task["task_id"], status="already_running")

    _cleanup_tasks()
    task_id = str(uuid.uuid4())
    _analysis_tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "journal_id": journal_id_str,
        "model_version": model_version,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": {
            "cluster_update": _make_step("pending", "Bekliyor..."),
            "openalex": _make_step("pending", "Bekliyor..."),
            "elasticsearch": _make_step("pending", "Bekliyor..."),
        },
        "result": None,
        "error": None,
    }
    asyncio.create_task(_run_journal_analysis(task_id, jid, model_version, min_abstract_length))
    return StartAnalysisResponse(task_id=task_id, status="started")


@router.get("/analysis_progress/{task_id}", response_model=AnalysisProgressResponse, summary="Analiz görevi ilerleme durumu")
async def get_analysis_progress(task_id: str):
    task = _analysis_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    return AnalysisProgressResponse(**task)


@router.get(
    "/analysis_active_for_journal",
    response_model=ActiveJournalAnalysisResponse,
    summary="Journal için çalışan analiz görevini getir",
)
async def get_active_analysis_for_journal(
    journal_id: str = Query(..., description="Hedef journal'ın MongoDB ObjectId'si"),
    model_version: Optional[str] = Query(None),
):
    from beanie import PydanticObjectId as ObjId
    try:
        jid = str(ObjId(journal_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz journal_id formatı")

    running_tasks = []
    for task in _analysis_tasks.values():
        if task.get("status") != "running":
            continue
        if task.get("journal_id") != jid:
            continue
        if model_version is not None and task.get("model_version") != model_version:
            continue
        running_tasks.append(task)

    if not running_tasks:
        return ActiveJournalAnalysisResponse(found=False)

    running_tasks.sort(key=lambda t: t.get("started_at") or "", reverse=True)
    selected = running_tasks[0]
    return ActiveJournalAnalysisResponse(
        found=True,
        task_id=selected.get("task_id"),
        status=selected.get("status"),
        journal_id=selected.get("journal_id"),
        model_version=selected.get("model_version"),
        started_at=selected.get("started_at"),
    )


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
                detail=f"Bir eğitim zaten çalışıyor: {status['running_version']}",
            )

        # Eğitimi başlat
        result = await nlp_service.train_clustering(
            model_version=request.model_version,
            min_abstract_length=request.min_abstract_length,
        )

        return TrainResponse(
            status="completed",
            message="Clustering model başarıyla eğitildi",
            model_version=result["model_version"],
            total_articles=result["total_articles"],
            total_clusters=result["total_clusters"],
            noise_count=result["noise_count"],
            auto_triggered=False,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_bar_chart_input")
async def get_bar_chart_input(
    query: Optional[str] = Query(
        None, description="Arama sorgusu (None = son aramanın sonuçları)"
    ),
    model_version: Optional[str] = Query(None, description="Model versiyonu"),
):
    try:
        return await nlp_service.get_date_graph_input(query, model_version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_pie_chart_input")
async def get_pie_chart_input(
    query: str = Query(..., min_length=2, description="Arama sorgusu"),
    model_version: Optional[str] = Query(None, description="Model versiyonu"),
    top_k: int = Query(10, ge=1, le=100, description="Döndürülecek makale sayısı"),
):
    try:
        return await nlp_service.word_finding_pipeline(query, model_version, top_k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/get_scatter_chart_input")
# async def get_pie_chart_input():
#     try:
#         return await nlp_service.get_scatter_graph_input()
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         logger.error(f"Graph error: {e}")
#         raise HTTPException(status_code = 500, detail= str(e))
#
@router.get("/search", response_model=SearchResponse, summary="Benzer makaleleri ara")
async def search_similar_articles(
    query: str = Query(..., min_length=2, description="Arama sorgusu"),
    model_version: Optional[str] = Query(
        None, description="Model versiyonu (boş = en son)"
    ),
    top_k: int = Query(10, ge=1, le=100, description="Döndürülecek makale sayısı"),
    auto_train: bool = Query(False, description="Analiz yoksa otomatik eğitim başlat"),
):
    """
    Verilen sorguya benzer makaleleri bulur.

    - Query'yi embedding'e çevirir
    - En yakın cluster'ı bulur
    - O cluster'daki makaleleri döndürür

    **auto_train=true** ile analiz yoksa otomatik olarak eğitim başlatılır.

    Cache desteği: Aynı sorgu için sonuçlar cache'lenir.
    """
    try:
        # Her zaman nlp_service içindeki state'i güncelle (chart endpointleri buna bağımlı).
        # Cache yalnızca HTTP response için kullanılır, state için değil.
        result = await nlp_service.search_similar(
            query=query, model_version=model_version, top_k=top_k, auto_train=auto_train
        )

        cache_params = {"model_version": model_version, "top_k": top_k}
        cached_result = await cache_service.get_search_results(query, cache_params)
        if cached_result:
            logger.debug(f"Search cache HIT (state updated): {query}")
            return SearchResponse(**cached_result)

        # Cache'de yoksa sonucu cache'le
        await cache_service.set_search_results(query, cache_params, result)
        logger.info(f"Cache MISS: search '{query[:30]}...' - cached")

        # Cluster'daki diğer makaleleri ve komşu cluster'ları prefetch et (background)
        if settings.prefetch_enabled and result.get("cluster_id") is not None:
            cluster_id = result["cluster_id"]
            mv = result.get("model_version", "pkl_legacy")

            async def prefetch_cluster_and_neighbors():
                try:
                    logger.info(
                        f"Prefetch starting: cluster {cluster_id} and neighbors"
                    )

                    # 1. Ana cluster'ın tüm makalelerini prefetch et
                    if mv != "pkl_legacy":
                        full_result = await nlp_service.get_cluster_detail(
                            cluster_id=cluster_id,
                            model_version=mv,
                            include_articles=True,
                            article_limit=settings.prefetch_articles_per_cluster,
                        )
                        if full_result:
                            # Cluster meta bilgisini cache'le
                            cluster_data = {
                                k: v for k, v in full_result.items() if k != "articles"
                            }
                            await cache_service.set_cluster(
                                cluster_id, mv, cluster_data
                            )
                            # Makaleleri cache'le
                            await cache_service.set_cluster_articles(
                                cluster_id, mv, full_result.get("articles", [])
                            )
                            logger.info(
                                f"Prefetch: cluster {cluster_id} cached with {len(full_result.get('articles', []))} articles"
                            )

                    # 2. Komşu cluster'ları prefetch et
                    n = settings.prefetch_neighbor_clusters
                    neighbor_ids = [cluster_id + i for i in range(-n, n + 1) if i != 0]
                    neighbor_ids = [nid for nid in neighbor_ids if nid >= 0]

                    for neighbor_id in neighbor_ids:
                        try:
                            neighbor_result = await nlp_service.get_cluster_detail(
                                cluster_id=neighbor_id,
                                model_version=mv,
                                include_articles=True,
                                article_limit=settings.prefetch_neighbor_articles_limit,
                            )
                            if neighbor_result:
                                neighbor_data = {
                                    k: v
                                    for k, v in neighbor_result.items()
                                    if k != "articles"
                                }
                                await cache_service.set_cluster(
                                    neighbor_id, mv, neighbor_data
                                )
                                await cache_service.set_cluster_articles(
                                    neighbor_id, mv, neighbor_result.get("articles", [])
                                )
                        except Exception:
                            pass  # Komşu cluster yoksa sessizce geç

                    logger.info(
                        f"Prefetch completed: cluster {cluster_id} + {len(neighbor_ids)} neighbors"
                    )

                except Exception as e:
                    logger.error(f"Cluster prefetch error: {e}")

            cache_service._schedule_prefetch(prefetch_cluster_and_neighbors())

        return SearchResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/clusters", response_model=List[ClusterSummary], summary="Tüm cluster'ları listele"
)
async def list_clusters(
    model_version: Optional[str] = Query(
        None, description="Model versiyonu (boş = en son)"
    ),
    include_noise: bool = Query(False, description="Noise cluster'ı dahil et"),
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
            model_version=model_version, include_noise=include_noise
        )
        return [ClusterSummary(**c) for c in clusters]

    except Exception as e:
        logger.error(f"List clusters error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/patch_labels", summary="Cluster label'larını yeniden hesapla (train gerektirmez)"
)
async def patch_cluster_labels(
    model_version: str = Query(..., description="Patch uygulanacak model versiyonu"),
    force_recompute: bool = Query(False, description="Var olan labelları zorla yeniden hesapla"),
    background_tasks: BackgroundTasks = None,
):
    """
    Verilen model versiyonundaki label=null veya top_keywords=[] olan cluster'ları
    ArticleEmbedding'lerden keyword çekerek ve cross-encoder ile en temsili label'ı
    hesaplayarak günceller. Yeni bir eğitim başlatmaz.
    """
    try:
        result = await nlp_service.patch_cluster_labels(
            model_version=model_version, force_recompute=force_recompute
        )
        return result
    except Exception as e:
        logger.error(f"Patch labels error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/patch_group_ids",
    summary="Publisher/journal cluster'larının null group_id'lerini doldur (train gerektirmez)",
)
async def patch_cluster_group_ids(
    model_version: str = Query(..., description="Patch uygulanacak model versiyonu"),
):
    try:
        result = await nlp_service.patch_cluster_group_ids(model_version=model_version)
        return result
    except Exception as e:
        logger.error(f"Patch group_ids error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_journal_topic_trends")
async def list_journal_topic_trends(
    name: str, model_version: str, top_n: int = Query(10, ge=1, le=100)
):
    try:
        topic_trends = await nlp_service.get_journal_topic_trends(
            journal_name=name, model_version=model_version, top_n=top_n
        )
        return topic_trends
    except Exception as e:
        logger.error(f"Get Journal Topic Trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_publisher_topic_trends")
async def list_publisher_topic_trends(
    name: str, model_version: str, top_n: int = Query(10, ge=1, le=100)
):
    try:
        topic_trends = await nlp_service.get_publisher_topic_trends(
            publisher_name=name, model_version=model_version, top_n=top_n
        )
        return topic_trends
    except Exception as e:
        logger.error(f"Get Publisher Topic Trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_all_topic_trends")
async def list_all_topic_trends(
    model_version: str, top_n: int = Query(10, ge=1, le=100)
):
    try:
        topic_trends = await nlp_service.get_all_topic_trends(
            model_version=model_version, top_n=top_n
        )
        return topic_trends
    except Exception as e:
        logger.error(f"Get All Topic Trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_keyword_topic_trends")
async def get_keyword_topic_trends(
    keyword: str = Query(..., min_length=1, description="Anahtar kelime"),
    model_version: str = Query(..., description="Model versiyonu"),
    top_n: int = Query(10, ge=1, le=100, description="Döndürülecek topic sayısı"),
):
    try:
        topic_trends = await nlp_service.get_keyword_topic_trends(
            keyword=keyword, model_version=model_version, top_n=top_n
        )
        return topic_trends
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Get Keyword Topic Trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list_clusters", summary="Cluster metadatasını listele (graph data yok)")
async def list_clusters_endpoint(
    model_version: str,
    cluster_type: str = Query("all"),
    group_id: Optional[str] = Query(None),
):
    try:
        return await nlp_service.list_clusters(
            model_version=model_version,
            cluster_type=cluster_type,
            group_id=group_id,
        )
    except Exception as e:
        logger.error(f"List clusters error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cluster_trend_series", summary="Tek bir cluster için zaman serisi")
async def get_cluster_trend_series(
    cluster_id: int,
    model_version: str,
    cluster_type: str = Query("all"),
    group_id: Optional[str] = Query(None),
):
    try:
        return await nlp_service.get_cluster_trend_series(
            cluster_id=cluster_id,
            model_version=model_version,
            cluster_type=cluster_type,
            group_id=group_id,
        )
    except Exception as e:
        logger.error(f"Cluster trend series error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters/{cluster_id}", summary="Cluster detayını getir")
async def get_cluster_detail(
    cluster_id: int,
    model_version: Optional[str] = Query(
        None, description="Model versiyonu (boş = en son)"
    ),
    include_articles: bool = Query(True, description="Makaleleri dahil et"),
    article_limit: int = Query(50, ge=1, le=500, description="Makale limiti"),
):
    """
    Belirli bir cluster'ın detaylı bilgilerini döndürür.

    - Cluster metadata
    - Opsiyonel: Cluster'daki makaleler

    Cache desteği: Cluster bilgileri cache'lenir.
    """
    try:
        # Önce gerçek model version'ı belirle
        actual_mv = model_version
        if not actual_mv:
            # En son model versiyonunu al
            status = await nlp_service.get_status()
            actual_mv = (
                status.get("latest_model_version")
                or status.get("cached_version")
                or "latest"
            )

        # Önce cluster cache'ine bak
        cached_cluster = await cache_service.get_cluster(cluster_id, actual_mv)
        cached_articles = None

        if include_articles:
            cached_articles = await cache_service.get_cluster_articles(
                cluster_id, actual_mv
            )

        # Tam cache hit
        if cached_cluster and (not include_articles or cached_articles):
            logger.info(f"Cache HIT: cluster {cluster_id} (v: {actual_mv})")
            result = cached_cluster.copy()
            if include_articles and cached_articles:
                result["articles"] = cached_articles[:article_limit]
            return result

        # Cache'de yoksa hesapla
        logger.info(f"Cache MISS: cluster {cluster_id} - DB'den alınıyor")
        result = await nlp_service.get_cluster_detail(
            cluster_id=cluster_id,
            model_version=model_version,
            include_articles=include_articles,
            article_limit=article_limit,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Cluster bulunamadı")

        # Gerçek model version'ı sonuçtan al
        actual_mv = result.get("model_version", actual_mv)

        # Cluster bilgisini cache'le (articles hariç)
        cluster_data = {k: v for k, v in result.items() if k != "articles"}
        await cache_service.set_cluster(cluster_id, actual_mv, cluster_data)

        # Articles varsa onları da cache'le
        if include_articles and result.get("articles"):
            await cache_service.set_cluster_articles(
                cluster_id, actual_mv, result["articles"]
            )

        logger.info(f"Cluster {cluster_id} cached (version: {actual_mv})")

        # Prefetch: Komşu cluster'ları background'da cache'le
        if settings.prefetch_enabled:

            async def prefetch_neighbor_clusters():
                try:
                    n = settings.prefetch_neighbor_clusters
                    neighbor_ids = [cluster_id + i for i in range(-n, n + 1) if i != 0]
                    neighbor_ids = [nid for nid in neighbor_ids if nid >= 0]

                    prefetched = 0
                    for neighbor_id in neighbor_ids:
                        # Zaten cache'de mi kontrol et
                        if await cache_service.get_cluster(neighbor_id, actual_mv):
                            continue

                        try:
                            neighbor_result = await nlp_service.get_cluster_detail(
                                cluster_id=neighbor_id,
                                model_version=actual_mv,
                                include_articles=True,
                                article_limit=settings.prefetch_neighbor_articles_limit,
                            )
                            if neighbor_result:
                                neighbor_data = {
                                    k: v
                                    for k, v in neighbor_result.items()
                                    if k != "articles"
                                }
                                await cache_service.set_cluster(
                                    neighbor_id, actual_mv, neighbor_data
                                )
                                if neighbor_result.get("articles"):
                                    await cache_service.set_cluster_articles(
                                        neighbor_id,
                                        actual_mv,
                                        neighbor_result["articles"],
                                    )
                                prefetched += 1
                        except Exception:
                            pass  # Komşu cluster yoksa sessizce geç

                    if prefetched > 0:
                        logger.info(
                            f"Prefetch completed: {prefetched} neighbor clusters for cluster {cluster_id}"
                        )
                except Exception as e:
                    logger.error(f"Neighbor cluster prefetch error: {e}")

            cache_service._schedule_prefetch(prefetch_neighbor_clusters())

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cluster detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters/{cluster_id}/articles", summary="Cluster makalelerini getir")
async def get_cluster_articles(
    cluster_id: int,
    model_version: Optional[str] = Query(
        None, description="Model versiyonu (boş = en son)"
    ),
    limit: int = Query(15, ge=1, le=100, description="Sayfa başına makale sayısı"),
    skip: int = Query(0, ge=0, description="Atlanacak makale sayısı"),
    search: Optional[str] = Query(None, description="Başlık arama terimi"),
):
    """
    Belirli bir cluster'daki makaleleri backend'de sayfalama ve arama ile döndürür.
    - search yoksa ilk sayfa için cache kullanılır.
    - search varsa cache bypass edilir, MongoDB regex sorgusu yapılır.
    """
    try:
        # Model versiyonu belirle
        actual_mv = model_version
        if not actual_mv:
            status = await nlp_service.get_status()
            actual_mv = (
                status.get("latest_model_version")
                or status.get("cached_version")
                or "latest"
            )

        # Arama varsa direkt DB'den al (cache bypass)
        if search and search.strip():
            result = await nlp_service.get_cluster_articles_filtered(
                cluster_id=cluster_id,
                model_version=actual_mv,
                skip=skip,
                limit=limit,
                search=search,
            )
            if not result:
                raise HTTPException(status_code=404, detail="Cluster bulunamadı")
            return result

        # Arama yok — ilk sayfa için cache dene
        if skip == 0:
            cached_articles = await cache_service.get_cluster_articles(
                cluster_id, actual_mv
            )
            if cached_articles:
                logger.info(f"Cache HIT: cluster {cluster_id} articles")
                page_articles = cached_articles[:limit]
                return {
                    "cluster_id": cluster_id,
                    "total_count": len(cached_articles),
                    "skip": skip,
                    "limit": limit,
                    "articles": page_articles,
                }

        # Cache miss — DB'den sayfalı çek
        logger.info(f"Cache MISS: cluster {cluster_id} articles - DB'den alınıyor")
        result = await nlp_service.get_cluster_articles_filtered(
            cluster_id=cluster_id,
            model_version=actual_mv,
            skip=skip,
            limit=limit,
            search=None,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Cluster bulunamadı")

        # İlk sayfa ise tüm makaleleri cache'le (total_count kadar)
        if skip == 0:
            # total_count kadar makale çek ve cache'e yaz
            all_result = await nlp_service.get_cluster_articles_filtered(
                cluster_id=cluster_id,
                model_version=actual_mv,
                skip=0,
                limit=result["total_count"] or 500,
                search=None,
            )
            if all_result:
                await cache_service.set_cluster_articles(
                    cluster_id, actual_mv, all_result["articles"]
                )
                logger.info(
                    f"Cluster {cluster_id} articles cached ({len(all_result['articles'])} adet)"
                )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cluster articles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/article/{article_id}/cluster", summary="Makalenin cluster'ını bul")
async def get_article_cluster(
    article_id: str,
    model_version: Optional[str] = Query(
        None, description="Model versiyonu (boş = en son)"
    ),
):
    """
    Belirli bir makalenin ait olduğu cluster'ı döndürür.
    """
    try:
        result = await nlp_service.get_article_cluster(
            article_id=article_id, model_version=model_version
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Makale için cluster bulunamadı veya makale henüz işlenmemiş",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Article cluster error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", summary="Eğitim geçmişini getir")
async def get_training_history(
    limit: int = Query(10, ge=1, le=50, description="Kayıt limiti"),
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
        return {"count": len(history), "runs": history}

    except Exception as e:
        logger.error(f"History error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Legacy Endpoint (Backward Compatibility) ==============


@router.get(
    "/test_clustering",
    summary="[LEGACY] Model ile anahtar kelimeye benzer makaleleri çek",
)
async def legacy_test_clustering(
    keyword: str = Query(..., description="Arama yapılmak istenen anahtar kelime"),
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
            "data": [a["title"] for a in result["articles"]],
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Legacy test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
