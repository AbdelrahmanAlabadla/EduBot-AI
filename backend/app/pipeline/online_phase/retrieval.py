import logging
from typing import List, Dict, Any
from uuid import UUID

from app.core.config import settings
from app.pipeline.online_phase.rrf import rrf_search
from app.pipeline.offline_phase.qdrant import _get_client, _collection_name
from app.models.document_chunk import DocumentChunk
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def hybrid_search(
    rewritten_query: str,
    school_id: UUID,
    dense_limit: int = None,
    sparse_limit: int = None,
    final_limit: int = None,
    score_threshold: float = None,
) -> List[Dict[str, Any]]:
    if dense_limit is None:
        dense_limit = settings.RAG_DENSE_LIMIT
    if sparse_limit is None:
        sparse_limit = settings.RAG_SPARSE_LIMIT
    if final_limit is None:
        final_limit = dense_limit + sparse_limit
    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD

    client = _get_client()
    collection = _collection_name(school_id)

    return rrf_search(
        client, collection, rewritten_query,
        dense_limit=dense_limit,
        sparse_limit=sparse_limit,
        final_limit=final_limit,
        score_threshold=score_threshold,
    )


def fetch_parent_chunks(
    child_chunks: List[Dict[str, Any]],
    db: Session,
) -> List[Dict[str, Any]]:
    parent_ids = set()
    child_by_parent = {}

    for chunk in child_chunks:
        payload = chunk.get("payload", {})
        parent_id = payload.get("parent_id")
        if parent_id:
            parent_ids.add(parent_id)
            child_by_parent.setdefault(parent_id, []).append(chunk)

    if not parent_ids:
        return child_chunks

    parents = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.id.in_(list(parent_ids)))
        .all()
    )
    parent_map = {str(p.id): p for p in parents}

    results = []
    seen_ids = set()
    for chunk in child_chunks:
        pid = chunk.get("payload", {}).get("parent_id")
        if pid and pid in parent_map:
            key = f"parent_{pid}"
            if key not in seen_ids:
                parent = parent_map[pid]
                # Attach parent text as full_context to first child
                chunk["full_context"] = parent.chunk_text
                chunk["breadcrumb"] = parent.breadcrumb or chunk.get("payload", {}).get("breadcrumb", "")
                seen_ids.add(key)
        else:
            payload = chunk.get("payload", {})
            st = payload.get("searchable_text")
            chunk["full_context"] = st if st else payload.get("page_content", "")
        results.append(chunk)

    logger.info("Fetched %d parent chunks from Postgres", len(parent_map))
    return results
