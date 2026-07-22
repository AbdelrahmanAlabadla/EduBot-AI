import logging
import math
import re
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.pipeline.online_phase.llm_reranker import llm_rerank_and_filter

logger = logging.getLogger(__name__)

_HTML_ENTITY_RE = re.compile(r'&#\d+;|&[a-zA-Z]+;')


def _clean_text(text: str) -> str:
    text = _HTML_ENTITY_RE.sub(' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ====================================================================
# Cross-encoder reranker (disabled — kept for reference)
# ====================================================================
# _reranker = None
#
# def _get_reranker():
#     global _reranker
#     if _reranker is None:
#         logger.info("Loading cross-encoder reranker: %s", settings.RERANKER_MODEL)
#         from FlagEmbedding import FlagReranker
#         _reranker = FlagReranker(
#             settings.RERANKER_MODEL,
#             use_fp16=True,
#             device="cuda",
#         )
#         logger.info("Reranker loaded.")
#     return _reranker
# ====================================================================


def initial_judge(
    chunks: List[Dict[str, Any]],
    query: str,
    min_rrf_score: float = 0.0001,
) -> bool:
    if not chunks:
        logger.info("Initial judge: no chunks retrieved — pipeline should halt")
        return False

    top_score = chunks[0].get("score", 0)
    if top_score < min_rrf_score:
        logger.info("Initial judge: top RRF score %.4f below min %.4f — halting", top_score, min_rrf_score)
        return False

    if top_score < 0.01:
        logger.warning("Initial judge: top RRF score is very low (%.4f) — answer quality may suffer", top_score)

    logger.info("Initial judge: %d chunks retrieved, top RRF score=%.4f for query: %.80s", len(chunks), top_score, query)
    return True


def rerank_and_filter(
    chunks: List[Dict[str, Any]],
    query: str,
    top_k: int = None,
    score_threshold: float = None,
) -> List[Dict[str, Any]]:
    if top_k is None:
        top_k = settings.RAG_FINAL_K
    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD
    fallback_k = getattr(settings, "RAG_FALLBACK_K", 10)

    if not chunks:
        return []

    reranker_type = getattr(settings, "RERANKER_TYPE", "llm")

    # ------------------------------------------------------------------
    # LLM RERANKER (default)
    # ------------------------------------------------------------------
    if reranker_type == "llm":
        return llm_rerank_and_filter(chunks, query, top_k=top_k, score_threshold=score_threshold)

    # ------------------------------------------------------------------
    # NO RERANKER — use RRF scores directly
    # ------------------------------------------------------------------
    if reranker_type == "rrf":
        use_k = max(top_k, fallback_k)
        scored = [(chunk, chunk.get("score", 0)) for chunk in chunks]
        scored.sort(key=lambda x: x[1], reverse=True)
        kept = []
        for chunk, score in scored[:use_k]:
            chunk["rerank_score"] = float(score)
            kept.append(chunk)
        logger.info("RRF-only: kept %d / %d chunks (top-%d)", len(kept), len(chunks), use_k)
        return kept

    # ------------------------------------------------------------------
    # CROSS-ENCODER PATH (requires _get_reranker() uncommented above)
    # ------------------------------------------------------------------
    # reranker = _get_reranker()
    #
    # pairs = []
    # for chunk in chunks:
    #     text = chunk.get("full_context") or chunk.get("payload", {}).get("page_content", "")
    #     text = _clean_text(text)
    #     pairs.append([query, text])
    #
    # logger.info("Reranking %d chunks with cross-encoder...", len(pairs))
    #
    # try:
    #     raw_scores = reranker.compute_score(pairs, normalize=False)
    # except Exception as e:
    #     use_k = max(top_k, fallback_k)
    #     logger.warning("Cross-encoder compute_score failed: %s — falling back to top-%d from RRF scores", e, use_k)
    #     scored = [(chunk, chunk.get("score", 0)) for chunk in chunks]
    #     scored.sort(key=lambda x: x[1], reverse=True)
    #     kept = []
    #     for chunk, score in scored[:use_k]:
    #         chunk["rerank_score"] = float(score)
    #         kept.append(chunk)
    #     logger.info("Rerank fallback: kept %d / %d chunks (top-%d)", len(kept), len(chunks), use_k)
    #     return kept
    #
    # if raw_scores and len(raw_scores) == len(chunks):
    #     raw_min, raw_max = min(raw_scores), max(raw_scores)
    #     normalized = [1.0 / (1.0 + math.exp(-s)) for s in raw_scores]
    #     sig_min, sig_max = min(normalized), max(normalized)
    #     logger.info("Rerank raw logits: min=%.4f  max=%.4f  |  sigmoid: min=%.4f  max=%.4f  (threshold=%.2f)",
    #                  raw_min, raw_max, sig_min, sig_max, score_threshold)
    # else:
    #     use_k = max(top_k, fallback_k)
    #     logger.warning("Cross-encoder returned %s scores for %d chunks — falling back to top-%d from RRF scores",
    #                    "no" if not raw_scores else str(len(raw_scores)), len(chunks), use_k)
    #     scored = [(chunk, chunk.get("score", 0)) for chunk in chunks]
    #     scored.sort(key=lambda x: x[1], reverse=True)
    #     kept = []
    #     for chunk, score in scored[:use_k]:
    #         chunk["rerank_score"] = float(score)
    #         kept.append(chunk)
    #     logger.info("Rerank fallback: kept %d / %d chunks (top-%d)", len(kept), len(chunks), use_k)
    #     return kept
    #
    # scored = list(zip(chunks, normalized))
    # scored.sort(key=lambda x: x[1], reverse=True)
    #
    # filtered = []
    # for chunk, score in scored:
    #     chunk["rerank_score"] = float(score)
    #     if score >= score_threshold:
    #         filtered.append(chunk)
    #
    # kept = filtered[:top_k]
    # logger.info("Rerank: kept %d / %d chunks (threshold=%.2f)", len(kept), len(chunks), score_threshold)
    #
    # if logger.isEnabledFor(logging.DEBUG):
    #     for chunk, score in scored:
    #         p = chunk.get("payload", {})
    #         decision = "KEPT" if score >= score_threshold else "DROP"
    #         logger.debug("Rerank %s score=%.4f %s",
    #                      decision, score,
    #                      chunk.get("breadcrumb") or p.get("breadcrumb", "?"))
    #
    # return kept

    # Fallback if RERANKER_TYPE is unrecognised (treat as RRF-only)
    use_k = max(top_k, fallback_k)
    scored = [(chunk, chunk.get("score", 0)) for chunk in chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    kept = []
    for chunk, score in scored[:use_k]:
        chunk["rerank_score"] = float(score)
        kept.append(chunk)
    logger.info("Unknown reranker_type=%s — RRF fallback: kept %d / %d chunks (top-%d)",
                reranker_type, len(kept), len(chunks), use_k)
    return kept
