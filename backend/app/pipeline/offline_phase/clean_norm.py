import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Patterns run FIRST — strip repeating canvas header/footer artifacts
# before any whitespace/formatting cleanup so the patterns match raw LlamaParse output.
# Page numbers are NEVER removed — they are kept as-is.
STRUCTURAL_PATTERNS = [
    re.compile(r"^# Policy Main Title\s*$", re.MULTILINE),
    re.compile(r"^#?\s*Fiscal Resources and Procurement\s*$", re.MULTILINE),
    re.compile(r"^Policy Subject:\s*Fees Collection and Refund\s*$", re.MULTILINE),
    re.compile(r"^#?\s*UNIVERSITY OF SHARJAH\s*$", re.MULTILINE),
    re.compile(r"^Approved By:\s*Chancellor\s*$", re.MULTILINE),
    re.compile(r"^Effective Date:.*$", re.MULTILINE),
    re.compile(r"^Last Review date:.*$", re.MULTILINE),
    re.compile(r"^Policy Number:.*$", re.MULTILINE),
    re.compile(r"^Next Review date:.*$", re.MULTILINE),
    re.compile(r"^Responsible Entity:.*$", re.MULTILINE),
    re.compile(r"^\d+ \| P a g e$", re.MULTILINE),
]

ZERO_WIDTH_CHARS = re.compile(r"[\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff]")
MULTI_NEWLINE = re.compile(r"\n{3,}")
MULTI_SPACE = re.compile(r"[ \t]{2,}")
TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)


def clean_and_normalize(
    blocks: List[Dict[str, Any]],
    extra_patterns: List[re.Pattern] = None,
) -> List[Dict[str, Any]]:
    cleaned = []
    all_patterns = extra_patterns or []

    for block in blocks:
        text = block["content"]

        # 1. Strip detected boilerplate patterns (structural patterns pre-applied in pipeline)
        for pattern in all_patterns:
            text = pattern.sub("", text)

        # 2. Unicode / zero-width char removal
        text = ZERO_WIDTH_CHARS.sub("", text)

        # 3. Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 4. Collapse trailing whitespace, excessive newlines/spaces
        text = TRAILING_WS.sub("", text)
        text = MULTI_NEWLINE.sub("\n\n", text)
        text = MULTI_SPACE.sub(" ", text)

        text = text.strip()
        if not text:
            continue

        block["content"] = text
        cleaned.append(block)

    return cleaned
