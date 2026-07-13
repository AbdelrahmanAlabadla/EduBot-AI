import logging
from typing import List, Optional, Dict
from uuid import UUID, uuid4

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import (
    PointStruct,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    Distance,
    HnswConfigDiff,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.pipeline.offline_phase.chunking import SEARCHABLE_TYPES, CONTEXT_TYPES

logger = logging.getLogger(__name__)

_client: Optional[QdrantClient] = None

REQUIRED_METADATA = {
    "chunk_type", "breadcrumb", "document_id",
    "school_id", "chunk_order",
}


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
    return _client


def _collection_name(school_id: UUID | str) -> str:
    return f"school_{school_id}"


def _ensure_collection(school_id: UUID | str):
    client = _get_client()
    name = _collection_name(school_id)
    try:
        client.get_collection(name)
    except (UnexpectedResponse, ValueError):
        logger.info("Creating Qdrant collection (dense + sparse): %s", name)
        client.create_collection(
            collection_name=name,
            vectors_config={
                "": VectorParams(size=1024, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=SparseIndexParams(),
                ),
            },
            hnsw_config=HnswConfigDiff(
                payload_m=16,
                m=0,
            ),
        )


def _validate_schema(chunks: List[Document]):
    for chunk in chunks:
        meta = chunk.metadata
        missing = REQUIRED_METADATA - set(meta.keys())
        if missing:
            raise ValueError(
                f"Chunk missing required metadata fields: {missing}"
            )


def store_in_qdrant(
    chunks: List[Document],
    school_id: UUID | str,
    db: Optional[Session] = None,
):
    to_store = [c for c in chunks if c.metadata.get("chunk_type") in SEARCHABLE_TYPES]
    if not to_store:
        logger.info("No embeddable chunks to store in Qdrant.")
        return

    _validate_schema(to_store)
    _ensure_collection(school_id)

    client = _get_client()
    name = _collection_name(school_id)

    points = []
    for chunk in to_store:
        meta = chunk.metadata
        dense = meta.get("embedding")
        sparse = meta.get("sparse_vector")
        if dense is None:
            logger.warning("Chunk missing embedding, skipping upsert: %.60s", chunk.page_content)
            continue

        vectors: Dict = {"": dense}
        if sparse:
            vectors["sparse"] = sparse

        payload = {k: v for k, v in meta.items() if k not in ("embedding", "sparse_vector")}
        payload["page_content"] = chunk.page_content

        points.append(PointStruct(
            id=meta.get("qdrant_point_id") or str(uuid4()),
            vector=vectors,
            payload=payload,
        ))

    if points:
        logger.info("Upserting %d points into Qdrant collection: %s", len(points), name)
        client.upsert(collection_name=name, points=points)
        logger.info("Qdrant upsert complete.")
    else:
        logger.info("No valid points to upsert.")

    if db:
        _save_parents_to_postgres(chunks, db)


def _save_parents_to_postgres(chunks: List[Document], db: Session):
    from app.models.document_chunk import DocumentChunk

    parent_chunks = [c for c in chunks if c.metadata.get("chunk_type") in CONTEXT_TYPES]
    if not parent_chunks:
        return

    for chunk in parent_chunks:
        meta = chunk.metadata
        exists = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == meta["document_id"],
            DocumentChunk.chunk_type == "parent",
            DocumentChunk.breadcrumb == meta["breadcrumb"],
        ).first()
        if exists:
            continue
        db_chunk = DocumentChunk(
            document_id=meta["document_id"],
            school_id=meta["school_id"],
            chunk_text=chunk.page_content,
            chunk_order=meta.get("chunk_order", 0),
            chunk_type="parent",
            breadcrumb=meta.get("breadcrumb", ""),
            chunk_metadata=meta,
        )
        db.add(db_chunk)

    db.commit()
    logger.info("Parent chunks saved to Postgres.")
