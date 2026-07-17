import logging
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Prefetch, FusionQuery, Fusion

from app.core.config import settings
from app.pipeline.offline_phase.embedding import embed_query

logger = logging.getLogger(__name__)


def rrf_search(
    client: QdrantClient,
    collection_name: str,
    query: str,
    dense_limit: int = None,
    sparse_limit: int = None,
    final_limit: int = None,
    score_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    if dense_limit is None:
        dense_limit = settings.RAG_DENSE_LIMIT
    if sparse_limit is None:
        sparse_limit = settings.RAG_SPARSE_LIMIT
    if final_limit is None:
        final_limit = settings.RAG_RRF_LIMIT

    dense_vec, sparse_vec = embed_query(query)

    logger.info("RRF search: dense_limit=%d sparse_limit=%d final_limit=%d",
                dense_limit, sparse_limit, final_limit)

    result = client.query_points(
        collection_name=collection_name,
        prefetch=[
            Prefetch(query=dense_vec, using="", limit=dense_limit),
            Prefetch(query=sparse_vec, using="sparse", limit=sparse_limit),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=final_limit,
        score_threshold=score_threshold,
        with_payload=True,
        with_vectors=False,
    )

    points = [{"id": p.id, "score": p.score, "payload": p.payload or {}} for p in result.points]
    logger.info("RRF search returned %d points", len(points))
    return points
