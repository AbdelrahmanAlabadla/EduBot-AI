import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def build_context(
    chunks: List[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    if not chunks:
        return "", []

    sections = []
    allowed_citation_ids = []

    for i, chunk in enumerate(chunks):
        doc_id = f"doc_{i + 1}"
        allowed_citation_ids.append(doc_id)

        payload = chunk.get("payload", {})
        text = chunk.get("full_context") or payload.get("page_content", "")
        breadcrumb = chunk.get("breadcrumb") or payload.get("breadcrumb", "")
        source = payload.get("source_file", "")
        score = chunk.get("rerank_score", chunk.get("score", 0))

        header = f"[{doc_id}]"
        if breadcrumb:
            header += f" Section: {breadcrumb}"
        if source:
            header += f" (Source: {source})"
        header += f" [Relevance: {score:.3f}]"

        sections.append(f"{header}\n{text}")

    context = "\n\n---\n\n".join(sections)
    logger.info("Built context with %d chunks, %d chars, citation IDs: %s",
                len(chunks), len(context), allowed_citation_ids)

    return context, allowed_citation_ids
