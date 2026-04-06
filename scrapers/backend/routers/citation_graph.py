"""
Citation Graph Router
Atıf grafiği API endpoint'leri
"""

from fastapi import APIRouter, HTTPException, Query

from backend.services.openalex.citation_graph_service import citation_graph_service
from backend.services.cache_service import get_cache_service
from backend.schemas.citation_graph import CitationGraphResponse, CitationExpandResponse, CitationNodeSchema, CitationEdgeSchema
from backend.core.config import settings

router = APIRouter(prefix="/citation-graph", tags=["Citation Graph"])


@router.get(
    "",
    response_model=CitationGraphResponse,
    summary="Makale atıf grafiğini getir",
    description=(
        "Verilen makale için BFS ile oluşturulan atıf grafiğini döner. "
        "Edge yönü: source → target (source, target'ı cite ediyor). "
        "İlk istekte hesaplama yapılır ve Redis'e cache'lenir; "
        "force_refresh=true ile cache geçersiz kılınır."
    ),
)
async def get_citation_graph(
    article_id: str = Query(..., description="Makale MongoDB ID'si"),
    depth: int = Query(
        default=2,
        ge=1,
        le=5,
        description="BFS derinliği (1-5 arası, max .env'deki CITATION_GRAPH_MAX_DEPTH)",
    ),
    force_refresh: bool = Query(
        default=False,
        description="Cache'i geçersiz kıl ve grafiği yeniden hesapla",
    ),
):
    effective_depth = min(depth, settings.citation_graph_max_depth)

    # Cache temizle (force_refresh istendi ise)
    if force_refresh:
        try:
            cache = get_cache_service()
            await cache.invalidate_citation_graph(article_id)
        except Exception:
            pass

    graph = await citation_graph_service.build_graph(
        article_id=article_id,
        max_depth=effective_depth,
    )

    if not graph:
        raise HTTPException(
            status_code=404,
            detail=(
                "Makale bulunamadı veya OpenAlex ID'si yok. "
                "Önce OpenAlex taramasını çalıştırın."
            ),
        )

    return CitationGraphResponse(
        root_article_id=graph["root_article_id"],
        root_openalex_id=graph["root_openalex_id"],
        max_depth=graph["max_depth"],
        node_count=graph["node_count"],
        edge_count=graph["edge_count"],
        computed_at=graph["computed_at"],
        nodes=[CitationNodeSchema(**n) for n in graph["nodes"]],
        edges=[CitationEdgeSchema(**e) for e in graph["edges"]],
    )


@router.get(
    "/expand",
    response_model=CitationExpandResponse,
    summary="Bir düğümü genişlet (OpenAlex ID ile)",
    description=(
        "Verilen OpenAlex ID'li düğümün atıf yapanlarını getirir. "
        "Mevcut grafa merge edilmek üzere yeni node ve edge listesi döner."
    ),
)
async def expand_citation_node(
    openalex_id: str = Query(..., description="Genişletilecek düğümün OpenAlex ID'si"),
    depth: int = Query(
        default=1,
        ge=1,
        le=3,
        description="Genişletme derinliği (1-3)",
    ),
):
    result = await citation_graph_service.expand_node(
        openalex_id=openalex_id,
        depth=depth,
    )

    if not result or not result.get("nodes"):
        raise HTTPException(
            status_code=404,
            detail="Bu düğüm için atıf verisi bulunamadı.",
        )

    return CitationExpandResponse(
        expanded_node_id=result["expanded_node_id"],
        node_count=result["node_count"],
        edge_count=result["edge_count"],
        nodes=[CitationNodeSchema(**n) for n in result["nodes"]],
        edges=[CitationEdgeSchema(**e) for e in result["edges"]],
    )
