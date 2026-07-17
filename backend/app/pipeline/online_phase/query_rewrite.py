import json
import logging
import re
from typing import List, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a query normalizer for a university chatbot.
Your job: take a messy user query and output ONE clean, natural sentence,
without changing what the user is actually asking.

WHAT YOU MAY DO:
1. Fix spelling and grammar mistakes.
2. Expand shorthand, texting abbreviations, and acronyms into their full
   form WHEN the meaning is unambiguous from context (e.g. "u" -> "you",
   "bc" -> "because", "info" -> "information", "req" -> "requirement",
   "yr" -> "year", "gpa" -> "GPA", "dept" -> "department"). This applies
   to ANY shorthand of this kind, not a fixed list — use your judgement
   the same way a human proofreader would, based on what the word means
   in context.
3. If the current query is a short follow-up (e.g. starts with "i mean",
   "actually", "no i meant", or is just a noun phrase with no verb),
   attach it to the SUBJECT of the immediately preceding user turn so it
   reads as a standalone question. Use ONLY the most recent user turn for
   this — do not pull in older, unrelated turns.

WHAT YOU MUST NEVER DO (hard constraints):
- NEVER replace a word or phrase with a different word that changes what
  is being asked, even if it seems "close enough" or more common. If the
  user wrote a specific term, that exact term (or its literal expansion)
  must appear in the output. Expanding shorthand into its own full form
  is allowed; swapping it for a different concept is not.
- NEVER add a topic, subject, name, or detail that the user did not
  mention and that isn't the direct expansion of something they typed.
- NEVER answer the question, and never add explanation, lists, or extra
  keywords beyond the single rewritten sentence.

If you are unsure whether an abbreviation has a specific expansion, leave
it as-is rather than guessing — guessing wrong is worse than not expanding.

Detect the primary language of the user's latest query. Output "Arabic"
if any Arabic script is detected, otherwise "English".

Return valid JSON only with exactly these two keys: "rewritten_query"
and "detected_language". No markdown, no preamble.

Examples (illustrating the PATTERN, not a fixed list of words to memorize):
  Input: "wha kind of programing program does this university have??"
  Output: {"rewritten_query": "what kind of programming programs does this university have?", "detected_language": "English"}

  Input: "business degre"
  Output: {"rewritten_query": "business degree", "detected_language": "English"}

  Input: "wat r the gpa reqs for admission"
  Output: {"rewritten_query": "what are the GPA requirements for admission?", "detected_language": "English"}

  History: "is there a software engineering program?"
  Input: "i mean software engineering"
  Output: {"rewritten_query": "is there a software engineering program?", "detected_language": "English"}

  Input: "is there a software engineering program?"
  Output: {"rewritten_query": "is there a software engineering program?", "detected_language": "English"}
  (Note: "software engineering" stays exactly as written — never becomes
  "computer science" or any other program name.)
"""


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
    history = history or []
    prompt = _build_rewrite_prompt(current_query, history)

    url = f"{settings.LLM_BASE_URL}/chat"
    payload = {
        "model": settings.REWRITE_MODEL,
        "system_prompt": _SYSTEM_PROMPT,
        "input": [{"type": "text", "content": prompt}],
        "temperature": 0.0,  # deterministic cleanup task, not creative
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
        return _fallback(current_query)

    return _parse_rewrite_output(raw, original_query=current_query)


def _extract_text(data: dict) -> str:
    full = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            full += item.get("content", "")
    return full.strip()


def _parse_rewrite_output(raw: str, original_query: str) -> Dict[str, str]:
    try:
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        json_start = cleaned.index("{")
        json_end = cleaned.rindex("}") + 1
        parsed = json.loads(cleaned[json_start:json_end])
        rewritten = parsed.get("rewritten_query", original_query)
        lang = parsed.get("detected_language", "English")

        if lang not in ("Arabic", "English"):
            lang = "English"
        has_arabic = bool(re.search(r"[\u0600-\u06FF]", original_query))
        if lang == "Arabic" and not has_arabic:
            lang = "English"
        elif lang == "English" and has_arabic:
            lang = "Arabic"

        return {"rewritten_query": rewritten, "detected_language": lang}
    except (ValueError, json.JSONDecodeError):
        logger.warning("Could not parse rewrite output: %.120s", raw)
        return _fallback(original_query)


def _fallback(query: str) -> Dict[str, str]:
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", query))
    return {
        "rewritten_query": query,
        "detected_language": "Arabic" if has_arabic else "English",
    }