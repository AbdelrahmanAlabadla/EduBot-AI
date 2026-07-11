import logging
from typing import List, Optional
from uuid import UUID

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.pipeline.offline_phase.chunking import SEARCHABLE_TYPES, CONTEXT_TYPES
from app.pipeline.offline_phase.embedding import _get_embedder

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
        logger.info("Creating Qdrant collection: %s", name)
        client.create_collection(
            collection_name=name,
            vectors_config={
                "size": 1024,
                "distance": "Cosine",
            },
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

    embedder = _get_embedder()
    client = _get_client()
    name = _collection_name(school_id)

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=name,
        embedding=embedder,
    )

    texts = [c.page_content for c in to_store]
    metadatas = [c.metadata for c in to_store]

    logger.info("Upserting %d chunks into Qdrant collection: %s", len(to_store), name)
    vector_store.add_texts(texts=texts, metadatas=metadatas)
    logger.info("Qdrant upsert complete.")

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
