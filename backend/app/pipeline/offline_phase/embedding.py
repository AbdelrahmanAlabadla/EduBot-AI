import logging
import os
from typing import List, Dict, Tuple

os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Suppress transformers tokenizer warnings
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("tokenizers").setLevel(logging.ERROR)

from FlagEmbedding import BGEM3FlagModel
from langchain_core.documents import Document

from app.pipeline.offline_phase.chunking import SEARCHABLE_TYPES

logger = logging.getLogger(__name__)

_model = None


def _get_embedder() -> BGEM3FlagModel:
    global _model
    if _model is None:
        logger.info("Loading BGE-M3 FlagModel (dense + sparse)...")
        _model = BGEM3FlagModel(
            "BAAI/bge-m3",
            use_fp16=False,
            device="cpu",
        )
        logger.info("BGE-M3 FlagModel loaded.")
    return _model


def _to_qdrant_sparse(lexical_weights: Dict[str, float]) -> Dict:
    indices = []
    values = []
    for token_id_str, weight in sorted(lexical_weights.items(), key=lambda x: int(x[0])):
        indices.append(int(token_id_str))
        values.append(weight)
    return {"indices": indices, "values": values}


def embed_chunks(chunks: List[Document], batch_size: int = 32) -> List[Document]:
    embedder = _get_embedder()
    to_embed = [c for c in chunks if c.metadata.get("chunk_type") in SEARCHABLE_TYPES]
    if not to_embed:
        logger.info("No chunks to embed.")
        return chunks

    texts = []
    for c in to_embed:
        if c.metadata.get("chunk_type") == "table":
            st = c.metadata.get("searchable_text")
            texts.append(st if st else c.page_content)
        else:
            texts.append(c.page_content)
    logger.info("Embedding %d chunks with BGE-M3 (dense + sparse, batch_size=%d)...",
                len(texts), batch_size)
    output = embedder.encode(
        texts,
        batch_size=batch_size,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    for chunk, dense, sparse in zip(to_embed, output["dense_vecs"], output["lexical_weights"]):
        chunk.metadata["embedding"] = dense.tolist()
        chunk.metadata["sparse_vector"] = _to_qdrant_sparse(sparse)

    logger.info("Embedding complete.")
    return chunks


def embed_query(text: str) -> Tuple[List[float], Dict]:
    embedder = _get_embedder()
    output = embedder.encode(
        [text],
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    dense = output["dense_vecs"][0].tolist()
    sparse = _to_qdrant_sparse(output["lexical_weights"][0])
    return dense, sparse
