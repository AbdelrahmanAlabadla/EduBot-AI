import logging
from typing import List, Dict, Any, Optional
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
        # Qdrant RRF scores are tiny (~0.001-0.05), so threshold must be 0.0.
        # Filtering happens at the reranker stage via RAG_SCORE_THRESHOLD.
        score_threshold=0.0,
    )


def fetch_parent_chunks(
    child_chunks: List[Dict[str, Any]],
    db: Session,
) -> List[Dict[str, Any]]:
    results = []
    needs_db = set()
    needs_db_chunks = []

    for chunk in child_chunks:
        payload = chunk.get("payload", {})
        parent_text = payload.get("parent_text")
        if parent_text:
            chunk["full_context"] = parent_text
            chunk["breadcrumb"] = payload.get("breadcrumb", "")
            results.append(chunk)
        else:
            pid = payload.get("parent_id")
            if pid:
                needs_db.add(pid)
            needs_db_chunks.append(chunk)

    if needs_db and db:
        parents = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.id.in_(list(needs_db)))
            .all()
        )
        parent_map = {str(p.id): p for p in parents}
        logger.info("Fetched %d parent chunks from Postgres (fallback)", len(parent_map))

        for chunk in needs_db_chunks:
            payload = chunk.get("payload", {})
            pid = payload.get("parent_id")
            ctype = payload.get("chunk_type", "")
            if pid and pid in parent_map:
                parent = parent_map[pid]
                if ctype in ("table", "faq"):
                    chunk_content = payload.get("page_content", "")
                    chunk["full_context"] = f"{parent.chunk_text}\n\n--- {ctype.title()} Data ---\n\n{chunk_content}"
                else:
                    chunk["full_context"] = parent.chunk_text
                chunk["breadcrumb"] = parent.breadcrumb or payload.get("breadcrumb", "")
            else:
                st = payload.get("searchable_text")
                chunk["full_context"] = st if st else payload.get("page_content", "")
            results.append(chunk)
    else:
        for chunk in needs_db_chunks:
            payload = chunk.get("payload", {})
            st = payload.get("searchable_text")
            chunk["full_context"] = st if st else payload.get("page_content", "")
            results.append(chunk)

    return results
