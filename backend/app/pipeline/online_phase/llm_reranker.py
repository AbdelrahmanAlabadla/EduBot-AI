import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

_HTML_ENTITY_RE = re.compile(r'&#\d+;|&[a-zA-Z]+;')

_SYSTEM_PROMPT = (
    "You are a relevance judge for a university admissions chatbot. "
    "For each document chunk below, rate its relevance to answering the "
    "user's query on a scale of 0-10: "
    "0 = completely irrelevant or no useful information, "
    "10 = directly and completely answers the query. "
    "Respond with ONLY a valid JSON object in exactly this format: "
    '{"scores": [score1, score2, ...]}. '
    "No explanation, no markdown, no additional text."
)

_MAX_CONCURRENT = 3


def _clean_text(text: str) -> str:
    text = _HTML_ENTITY_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _call_lm_studio(prompt: str, timeout: int = 60) -> Optional[str]:
    import requests

    url = f"{settings.LLM_BASE_URL}/chat"
    payload = {
        "model": settings.REWRITE_MODEL,
        "system_prompt": _SYSTEM_PROMPT,
        "input": [{"type": "text", "content": prompt}],
        "temperature": 0.0,
        "max_output_tokens": 256,
        "stream": False,
    }
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        full = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                full += item.get("content", "")
        return full.strip()
    except Exception as e:
        logger.warning("LLM reranker call failed: %s", e)
        return None


def _parse_scores(raw: str, expected: int) -> Optional[List[float]]:
    if not raw:
        return None
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        parsed = json.loads(raw[start:end])
        scores = parsed.get("scores", [])
    except (ValueError, json.JSONDecodeError):
        try:
            start = raw.index("[")
            end = raw.rindex("]") + 1
            scores = json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            logger.warning("Could not parse LLM reranker output: %.120s", raw)
            return None

    if not isinstance(scores, list) or len(scores) != expected:
        logger.warning(
            "LLM reranker returned %d scores for %d chunks",
            len(scores), expected,
        )
        return None

    cleaned = []
    for s in scores:
        try:
            val = float(s)
            cleaned.append(max(0.0, min(10.0, val)))
        except (TypeError, ValueError):
            cleaned.append(0.0)

    return cleaned


def _score_batch(
    indices: List[int],
    chunk_texts: List[str],
    query: str,
) -> Tuple[List[int], Optional[List[float]]]:
    lines = [f"Query: {query}"]
    for i, text in enumerate(chunk_texts):
        lines.append(f"\nChunk {i + 1}: {text}")
    prompt = "\n".join(lines)

    raw = _call_lm_studio(prompt)
    scores = _parse_scores(raw, len(chunk_texts))
    return indices, scores


def llm_rerank_and_filter(
    chunks: List[Dict[str, Any]],
    query: str,
    top_k: int = None,
    score_threshold: float = None,
) -> List[Dict[str, Any]]:
    if top_k is None:
        top_k = settings.RAG_FINAL_K
    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD
    batch_size = getattr(settings, "LLM_RERANKER_BATCH_SIZE", 5)
    max_chars = getattr(settings, "LLM_RERANKER_MAX_CHARS", 1200)

    if not chunks:
        return []

    logger.info(
        "LLM reranker: scoring %d chunks (batch_size=%d, max_chars=%d, top_k=%d, threshold=%.2f)",
        len(chunks), batch_size, max_chars, top_k, score_threshold,
    )

    chunk_texts = []
    for chunk in chunks:
        text = chunk.get("full_context") or chunk.get("payload", {}).get("page_content", "")
        text = _clean_text(text)
        if len(text) > max_chars:
            text = text[:max_chars] + " ..."
        chunk_texts.append(text)

    scored = []

    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT) as executor:
        futures = {}
        for batch_start in range(0, len(chunks), batch_size):
            batch_end = min(batch_start + batch_size, len(chunks))
            indices = list(range(batch_start, batch_end))
            texts = [chunk_texts[i] for i in indices]
            future = executor.submit(_score_batch, indices, texts, query)
            futures[future] = indices

        for future in as_completed(futures):
            indices, scores = future.result()
            if scores is None:
                for idx in indices:
                    score = chunks[idx].get("score", 0.0)
                    scored.append((idx, score))
                    logger.info(
                        "  chunk[%d] fallback RRF score=%.4f",
                        idx, score,
                    )
            else:
                for idx, score_val in zip(indices, scores):
                    normalized = score_val / 10.0
                    scored.append((idx, normalized))
                    logger.info(
                        "  chunk[%d] LLM score=%.1f/10 → %.4f",
                        idx, score_val, normalized,
                    )

    scored.sort(key=lambda x: x[1], reverse=True)

    kept = []
    for idx, score_val in scored:
        chunks[idx]["rerank_score"] = score_val
        if score_val >= score_threshold:
            kept.append(chunks[idx])

    kept = kept[:top_k]
    logger.info(
        "LLM reranker: kept %d / %d chunks (threshold=%.2f, top_k=%d)",
        len(kept), len(chunks), score_threshold, top_k,
    )

    if kept:
        logger.info(
            "  Top chunk: score=%.4f  breadcrumb=%s",
            kept[0].get("rerank_score", 0),
            kept[0].get("breadcrumb") or kept[0].get("payload", {}).get("breadcrumb", "?"),
        )

    return kept
