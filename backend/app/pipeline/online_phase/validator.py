import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from uuid import UUID

from app.core.config import settings
from app.models.chatbot_setting import ChatbotSetting

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_COURSE_CODE_RE = re.compile(r"[A-Za-z]{2,4}\d{3,4}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CURRENCY_TOKENS = {'aed', 'dh', 'dhs', 'usd', 'eur', 'gbp', '$', '€', '£', 'sar', 'omr', 'qar', 'bhd', 'kwd'}


def _normalize_number_str(text: str) -> str:
    normalized = re.sub(r'[\s,.\-–—()\[\]{}]', '', text).lower()
    for token in _CURRENCY_TOKENS:
        normalized = normalized.replace(token, '')
    return normalized.strip()


def validate_and_repair(
    answer: str,
    allowed_citation_ids: List[str],
    context_chunks: List[Dict[str, Any]],
    question: str,
    context: str,
    detected_language: str,
    school_id: Optional[UUID] = None,
    db: Optional[Any] = None,
) -> Tuple[str, bool]:
    max_rerank = max((c.get("rerank_score", 0) for c in context_chunks), default=0)
    if max_rerank < 0.30:
        logger.warning("Validation: max rerank score %.4f < 0.30 — abstaining", max_rerank)
        return _fallback_answer(detected_language, school_id, db), False

    tier1_passed, tier1_retry_prompt = _tier1_citation_check(answer, allowed_citation_ids)
    if not tier1_passed:
        logger.warning("Tier 1 (citation check) FAILED — attempting targeted retry")
        corrected = _retry_generation(question, context, detected_language, tier1_retry_prompt)
        tier1_passed_2, _ = _tier1_citation_check(corrected, allowed_citation_ids)
        if tier1_passed_2:
            answer = corrected
            tier1_passed = True
            logger.info("Tier 1 corrected after retry")
        else:
            logger.warning("Tier 1 still failing after retry — returning fallback")
            return _fallback_answer(detected_language, school_id, db), False

    tier2_issues = _tier2_find_unsubstantiated(answer, context_chunks)
    if tier2_issues:
        logger.warning("Tier 2 (unsubstantiated content) FAILED — attempting targeted retry")
        tier2_retry_prompt = (
            f"Your previous answer contained course codes or numbers not found in the "
            f"provided context: {', '.join(tier2_issues)}. "
            f"Only include information explicitly supported by the context. "
            f"Do not invent course codes, fees, numbers, or any specific data."
        )
        corrected = _retry_generation(question, context, detected_language, tier2_retry_prompt)
        tier2_issues_2 = _tier2_find_unsubstantiated(corrected, context_chunks)
        if not tier2_issues_2:
            answer = corrected
            logger.info("Tier 2 corrected after retry")
        else:
            logger.warning("Tier 2 still failing after retry — stripping flagged sentences")
            cleaned, stripped_count = _strip_sentences(answer, tier2_issues)
            if not cleaned.strip():
                logger.warning("Tier 2: all sentences stripped — returning fallback")
                return _fallback_answer(detected_language, school_id, db), False
            note = _get_verification_note(detected_language, school_id, db)
            answer = cleaned + "\n\n" + note
            logger.info("Tier 2: stripped %d sentence(s), appended verification note", stripped_count)

    return answer, True


def _tier1_citation_check(
    answer: str,
    allowed_ids: List[str],
) -> Tuple[bool, str]:
    found = set(re.findall(r'\[doc_\d+\]', answer, re.IGNORECASE))
    if not found:
        return True, ""

    allowed_set = {f"[{aid}]".lower() for aid in allowed_ids}
    found_lower = {x.lower() for x in found}
    invalid = found_lower - allowed_set

    if not invalid:
        return True, ""

    valid_list = sorted(allowed_set)
    retry = (
        f"Your previous answer cited {', '.join(sorted(invalid))} but these sections "
        f"do not exist in the provided context. Only cite from: {', '.join(valid_list)}."
    )
    return False, retry


def _is_trivial_number(num_str: str) -> bool:
    cleaned = num_str.replace(",", "").strip()
    try:
        val = float(cleaned)
    except ValueError:
        return False
    if val < 50:
        return True
    if 1000 <= val <= 2999:
        return True
    return False


def _tier2_find_unsubstantiated(
    answer: str,
    context_chunks: List[Dict[str, Any]],
) -> List[str]:
    numbers_in_answer = list(_NUMBER_RE.finditer(answer))
    codes_in_answer = list(_COURSE_CODE_RE.finditer(answer))

    if not numbers_in_answer and not codes_in_answer:
        return []

    ground_text = ""
    for chunk in context_chunks:
        text = chunk.get("full_context") or chunk.get("payload", {}).get("page_content", "")
        ground_text += text + "\n"

    if not ground_text:
        return []

    ground_numbers = set()
    for m in _NUMBER_RE.finditer(ground_text):
        norm = _normalize_number_str(m.group())
        if norm and not _is_trivial_number(m.group()):
            ground_numbers.add(norm)

    ground_codes = set()
    for m in _COURSE_CODE_RE.finditer(ground_text):
        norm = _normalize_number_str(m.group())
        if norm:
            ground_codes.add(norm)

    sentences = _SENTENCE_SPLIT_RE.split(answer)
    sentence_positions = []
    pos = 0
    for s in sentences:
        idx = answer.find(s, pos)
        sentence_positions.append((idx, idx + len(s), s))
        pos = idx + len(s)

    flagged_sentences = set()
    for match in numbers_in_answer:
        num_raw = match.group()
        num_norm = _normalize_number_str(num_raw)
        if not num_norm:
            continue
        if _is_trivial_number(num_raw):
            continue
        if num_norm not in ground_numbers:
            num_start = match.start()
            for start, end, sentence in sentence_positions:
                if start <= num_start < end:
                    flagged_sentences.add(sentence.strip())
                    break

    for match in codes_in_answer:
        code = match.group()
        code_norm = _normalize_number_str(code)
        if not code_norm:
            continue
        if code_norm not in ground_codes:
            code_start = match.start()
            for start, end, sentence in sentence_positions:
                if start <= code_start < end:
                    flagged_sentences.add(sentence.strip())
                    break

    return list(flagged_sentences)


def _strip_sentences(text: str, sentences_to_remove: List[str]) -> Tuple[str, int]:
    stripped = text
    count = 0
    for sentence in sentences_to_remove:
        if sentence in stripped:
            stripped = stripped.replace(sentence, "", 1)
            count += 1
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped, count


def _get_verification_note(
    detected_language: str,
    school_id: Optional[UUID],
    db: Optional[Any],
) -> str:
    if db and school_id:
        setting = (
            db.query(ChatbotSetting)
            .filter(ChatbotSetting.school_id == school_id)
            .first()
        )
        if setting:
            if detected_language == "Arabic" and setting.verification_note_ar:
                return setting.verification_note_ar
            if detected_language == "English" and setting.verification_note_en:
                return setting.verification_note_en

    if detected_language == "Arabic":
        return settings.VERIFICATION_NOTE_AR
    return settings.VERIFICATION_NOTE_EN


def _retry_generation(
    question: str,
    context: str,
    detected_language: str,
    corrective_instruction: str,
) -> str:
    from app.pipeline.online_phase.generator import generate_answer
    logger.info("Retrying generation with corrective instruction")
    return generate_answer(question, context, detected_language,
                           conversation_history=corrective_instruction)


def _fallback_answer(language: str, school_id: Optional[UUID] = None,
                     db: Optional[Any] = None) -> str:
    if db and school_id:
        setting = (
            db.query(ChatbotSetting)
            .filter(ChatbotSetting.school_id == school_id)
            .first()
        )
        if setting:
            if language == "Arabic" and setting.fallback_message_ar:
                return setting.fallback_message_ar
            if language == "English" and setting.fallback_message_en:
                return setting.fallback_message_en
    if language == "Arabic":
        return settings.FALLBACK_MESSAGE_AR
    return settings.FALLBACK_MESSAGE_EN
