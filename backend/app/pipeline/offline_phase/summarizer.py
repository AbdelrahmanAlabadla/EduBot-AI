import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from uuid import UUID

from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger(__name__)

SUMMARIZER_PROMPT_TEMPLATE = (
    "You are summarizing a section from a university admissions document for a search index.\n\n"
    "Section: {breadcrumb}\n\n"
    "Text:\n{parent_text}\n\n"
    "Write a 3-4 sentence summary that captures the SPECIFIC content of this section — "
    "named requirements, numbers, deadlines, eligibility conditions, fees, or exceptions. "
    "Do not use generic phrasing like \"this section discusses admission requirements.\" "
    "Name the actual rules, numbers, and conditions stated in the text. "
    "If the section has no specific numbers or rules, summarize its distinct topic clearly enough "
    "that it would not be confused with a different section."
)

MAX_CONCURRENT = 3


def _call_lm_studio(breadcrumb: str, parent_text: str, timeout: int = 120) -> Optional[str]:
    import requests

    prompt = SUMMARIZER_PROMPT_TEMPLATE.format(breadcrumb=breadcrumb, parent_text=parent_text)
    url = f"{settings.LLM_BASE_URL}/chat"
    payload = {
        "model": settings.REWRITE_MODEL,
        "system_prompt": "You are a precise summarizer. Output only the summary, no preamble, no commentary.",
        "input": [{"type": "text", "content": prompt}],
        "temperature": 0.3,
        "max_output_tokens": 500,
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
        summary = full.strip()
        if summary:
            return summary
        logger.warning("Empty summary for breadcrumb: %s", breadcrumb)
    except Exception as e:
        logger.error("Summary generation failed for %s: %s", breadcrumb, e)
    return None


def generate_parent_summaries(
    parent_chunks: List[Document],
    document_id: UUID,
    school_id: UUID,
) -> List[Document]:
    if not parent_chunks:
        return []

    summaries: List[Document] = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        future_map = {}
        for chunk in parent_chunks:
            breadcrumb = chunk.metadata.get("breadcrumb", "")
            parent_text = chunk.page_content
            future = executor.submit(_call_lm_studio, breadcrumb, parent_text)
            future_map[future] = chunk

        for future in as_completed(future_map):
            chunk = future_map[future]
            summary_text = future.result()
            if not summary_text:
                continue

            meta = dict(chunk.metadata)
            meta["chunk_type"] = "summary"
            meta["searchable_text"] = None

            # Prepend breadcrumb for embedding context
            breadcrumb = meta.get("breadcrumb", "")
            page_content = f"{breadcrumb} > Summary: {summary_text}" if breadcrumb else f"Summary: {summary_text}"

            summary_doc = Document(page_content=page_content, metadata=meta)
            summaries.append(summary_doc)

    logger.info("Generated %d summary chunks from %d parents", len(summaries), len(parent_chunks))
    return summaries
