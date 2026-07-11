import logging
from typing import List

from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceBgeEmbeddings

from app.pipeline.offline_phase.chunking import SEARCHABLE_TYPES

logger = logging.getLogger(__name__)

_model = None


def _get_embedder():
    global _model
    if _model is None:
        logger.info("Loading BGE-M3 embedding model...")
        _model = HuggingFaceBgeEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("BGE-M3 model loaded.")
    return _model


def embed_chunks(chunks: List[Document]) -> List[Document]:
    embedder = _get_embedder()
    to_embed = [c for c in chunks if c.metadata.get("chunk_type") in SEARCHABLE_TYPES]
    if not to_embed:
        logger.info("No chunks to embed.")
        return chunks

    texts = [c.page_content for c in to_embed]
    logger.info("Embedding %d chunks with BGE-M3 (%s)...", len(texts),
                ", ".join(sorted(set(c.metadata["chunk_type"] for c in to_embed))))
    embeddings = embedder.embed_documents(texts)

    for chunk, vector in zip(to_embed, embeddings):
        chunk.metadata["embedding"] = vector

    logger.info("Embedding complete.")
    return chunks
