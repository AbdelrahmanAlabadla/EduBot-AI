import json
import logging
import re
from typing import List, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a query rewrite assistant for a school admissions chatbot.
Your task is to rewrite the user's latest query into a standalone, self-contained question.

Rules:
1. Resolve pronouns and incomplete phrases using conversation history.
   Example: User previously asked about "Computer Science", now asks "What about scholarships?"
   → Rewrite to "What scholarships are available for the Computer Science program?"

2. Detect the primary language of the user's latest query. Output "Arabic" if any Arabic
   script is detected. If mixed Arabic/English, default to "Arabic" as tie-breaker.

3. Do NOT translate. Output the rewritten query in its original language.

4. If the query contains an explicit language instruction (e.g., "reply in English"),
   keep the instruction in the rewritten_query for the generation model.

5. Return valid JSON only with exactly these two keys."""


def _build_rewrite_prompt(
    current_query: str,
    history: List[Dict[str, str]],
) -> str:
    parts = []
    if history:
        parts.append("### Conversation History (last 4 turns):")
        for turn in history[-4:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "assistant":
                content = content[:settings.REWRITE_MAX_TURN_CHARS]
            parts.append(f"{role.capitalize()}: {content}")

    parts.append(f"\n### Current user query:\n{current_query}")
    parts.append("\n### Output JSON:")

    total = 0
    truncated = []
    for p in reversed(parts):
        total += len(p)
        if total > settings.REWRITE_MAX_HISTORY_CHARS:
            break
        truncated.insert(0, p)

    return "\n".join(truncated)


def rewrite_query(
    current_query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    prompt = _build_rewrite_prompt(current_query, history or [])

    url = f"{settings.LLM_BASE_URL}/chat"
    payload = {
        "model": settings.LLM_MODEL,
        "system_prompt": _SYSTEM_PROMPT,
        "input": [{"type": "text", "content": prompt}],
        "temperature": 0.2,
        "max_output_tokens": 256,
        "stream": False,
    }

    try:
        import requests
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        raw = _extract_text(data)
    except Exception as e:
        logger.warning("Query rewrite failed: %s — falling back to original query", e)
        return _fallback(current_query, history)

    return _parse_rewrite_output(raw, current_query)


def _extract_text(data: dict) -> str:
    full = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            full += item.get("content", "")
    return full.strip()


def _parse_rewrite_output(raw: str, fallback_query: str) -> Dict[str, str]:
    try:
        # Strip markdown code fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        json_start = cleaned.index("{")
        json_end = cleaned.rindex("}") + 1
        parsed = json.loads(cleaned[json_start:json_end])
        rewritten = parsed.get("rewritten_query", fallback_query)
        lang = parsed.get("detected_language", "English")
        if lang not in ("Arabic", "English"):
            lang = "English"
        return {"rewritten_query": rewritten, "detected_language": lang}
    except (ValueError, json.JSONDecodeError):
        logger.warning("Could not parse rewrite output: %.120s", raw)
        return _fallback(fallback_query)


def _fallback(query: str, history: List[Dict[str, str]] = None) -> Dict[str, str]:
    import re
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", query))
    return {
        "rewritten_query": query,
        "detected_language": "Arabic" if has_arabic else "English",
    }
