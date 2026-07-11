import math
import re
from typing import List, Dict, Any


def detect_boilerplate(
    blocks: List[Dict[str, Any]],
    min_pages_ratio: float = 0.5,
    min_consecutive: int = 2,
) -> List[re.Pattern]:
    if not blocks:
        return []

    num_pages = len(blocks)
    threshold = max(2, math.ceil(num_pages * min_pages_ratio))

    line_page_counts: Dict[str, int] = {}
    page_lines: Dict[int, List[str]] = {}

    for i, block in enumerate(blocks):
        content = block.get("content", "")
        lines = [l.strip() for l in content.split("\n")]
        non_empty = [l for l in lines if l]
        page_lines[i] = non_empty
        seen = set()
        for line in non_empty:
            if line not in seen:
                seen.add(line)
                line_page_counts[line] = line_page_counts.get(line, 0) + 1

    candidate_lines = {line for line, count in line_page_counts.items() if count >= threshold}

    seq_pages: Dict[tuple, set] = {}
    for i, lines in page_lines.items():
        run = []
        for line in lines:
            if line in candidate_lines:
                run.append(line)
            else:
                _record_subseqs(run, min_consecutive, i, seq_pages)
                run = []
        _record_subseqs(run, min_consecutive, i, seq_pages)

    patterns = []
    for seq, pages in seq_pages.items():
        if len(pages) >= threshold:
            escaped = [re.escape(line) for line in seq]
            pattern_str = r"^" + r"\s*\n\s*".join(escaped) + r"\s*$"
            patterns.append(re.compile(pattern_str, re.MULTILINE))

    patterns.sort(key=lambda p: len(p.pattern), reverse=True)

    return patterns


def _record_subseqs(
    run: list, min_len: int, page_idx: int, seq_pages: Dict[tuple, set]
) -> None:
    for start in range(len(run)):
        for end in range(start + min_len, len(run) + 1):
            seq = tuple(run[start:end])
            seq_pages.setdefault(seq, set()).add(page_idx)
