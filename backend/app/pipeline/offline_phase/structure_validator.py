import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class StructureReport:
    score: int = 0
    heading_count: int = 0
    level_consistency: float = 0.0
    invalid_jumps: int = 0
    avg_section_size: float = 0.0
    orphan_ratio: float = 0.0
    coverage_ratio: float = 0.0
    empty_sections: int = 0


def _extract_headings(text: str) -> List[tuple]:
    return [(len(m.group(1)), m.group(2).strip()) for m in HEADING_RE.finditer(text)]


def _compute_level_consistency(levels: List[int]) -> float:
    if len(levels) < 2:
        return 1.0
    valid = 0
    for i in range(1, len(levels)):
        prev, curr = levels[i - 1], levels[i]
        if curr <= prev + 1:
            valid += 1
    return valid / (len(levels) - 1)


def _compute_invalid_jumps(levels: List[int]) -> int:
    if len(levels) < 2:
        return 0
    jumps = 0
    for i in range(1, len(levels)):
        prev, curr = levels[i - 1], levels[i]
        if curr > prev + 1:
            jumps += 1
    return jumps


def _compute_orphan_ratio(text: str, match_positions: List[int]) -> float:
    if not text.strip() or not match_positions:
        return 1.0 if text.strip() else 0.0
    first_heading = min(match_positions)
    total_len = len(text.strip())
    pre_heading_len = first_heading
    return pre_heading_len / total_len if total_len > 0 else 0.0


def _compute_coverage(text: str, sections: List[tuple]) -> float:
    if not text.strip() or not sections:
        return 0.0
    total_len = len(text.strip())
    inside = 0
    sorted_sections = sorted(sections, key=lambda x: x[2])
    for i, (level, heading, pos) in enumerate(sorted_sections):
        start = pos + len(heading) + len("#" * level) + 1
        if i + 1 < len(sorted_sections):
            end = sorted_sections[i + 1][2]
        else:
            end = total_len
        inside += (end - start)
    return inside / total_len


def validate_structure(blocks: List[Dict[str, Any]]) -> StructureReport:
    text = "\n\n".join(b.get("content", "") for b in blocks if b.get("content"))

    headings = _extract_headings(text)
    heading_count = len(headings)
    levels = [h[0] for h in headings]

    level_consistency = _compute_level_consistency(levels)
    invalid_jumps = _compute_invalid_jumps(levels)

    total_chars = len(text.strip()) if text.strip() else 1
    avg_section_size = total_chars / heading_count if heading_count > 0 else total_chars

    match_positions = []
    sections = []
    for m in HEADING_RE.finditer(text):
        h = m.group(0)
        match_positions.append(m.start())
        sections.append((len(m.group(1)), h, m.start()))

    orphan_ratio = _compute_orphan_ratio(text, match_positions)
    coverage_ratio = _compute_coverage(text, sections)

    empty_sections = 0
    sorted_sections = sorted(sections, key=lambda x: x[2])
    for i, (level, heading, pos) in enumerate(sorted_sections):
        start = pos + len(heading)
        if i + 1 < len(sorted_sections):
            end = sorted_sections[i + 1][2]
        else:
            end = len(text)
        body = text[start:end].strip()
        if not body or len(body) < 10:
            empty_sections += 1

    # --- Score computation (0-100) ---
    score = 0

    if heading_count == 0:
        score = max(0, min(100,
            # No headings at all: severely penalized
            # Only points come from limited section size and empty sections
            (10 if 500 < avg_section_size < 10000 else 5 if avg_section_size < 20000 else 0) +
            (10 if empty_sections == 0 else 0)
        ))
        # Cap at 30 for completely heading-less documents
        score = min(score, 30)
    else:
        # 1. Heading count (0-15 points)
        if heading_count >= 5:
            score += 15
        elif heading_count >= 3:
            score += 12
        elif heading_count >= 1:
            score += 8

        # 2. Level consistency (0-20 points)
        score += int(level_consistency * 20)

        # 3. Invalid jumps penalty (0-15 points)
        if invalid_jumps == 0:
            score += 15
        elif invalid_jumps == 1:
            score += 10
        elif invalid_jumps == 2:
            score += 5

        # 4. Average section size (0-10 points)
        if 100 <= avg_section_size <= 5000:
            score += 10
        elif avg_section_size > 5000:
            score += 5

        # 5. Orphan text ratio (0-15 points)
        if orphan_ratio <= 0.05:
            score += 15
        elif orphan_ratio <= 0.15:
            score += 12
        elif orphan_ratio <= 0.30:
            score += 8
        elif orphan_ratio <= 0.50:
            score += 4

        # 6. Coverage ratio (0-15 points)
        score += int(coverage_ratio * 15)

        # 7. Empty sections penalty (0-10 points)
        if empty_sections == 0:
            score += 10
        elif empty_sections <= 1:
            score += 7
        elif empty_sections <= 3:
            score += 4
        elif empty_sections <= 5:
            score += 2

    score = max(0, min(100, score))

    report = StructureReport(
        score=score,
        heading_count=heading_count,
        level_consistency=round(level_consistency, 3),
        invalid_jumps=invalid_jumps,
        avg_section_size=round(avg_section_size, 1),
        orphan_ratio=round(orphan_ratio, 4),
        coverage_ratio=round(coverage_ratio, 4),
        empty_sections=empty_sections,
    )

    logger.info(
        "Structure report — score=%d/100 | headings=%d | consistency=%.3f | jumps=%d "
        "| avg_section=%.0f | orphan=%.2f%% | coverage=%.0f%% | empty=%d",
        report.score,
        report.heading_count,
        report.level_consistency,
        report.invalid_jumps,
        report.avg_section_size,
        report.orphan_ratio * 100,
        report.coverage_ratio * 100,
        report.empty_sections,
    )

    return report
