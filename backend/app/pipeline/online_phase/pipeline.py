import logging
import re
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.pipeline.online_phase.query_rewrite import rewrite_query
from app.pipeline.online_phase.retrieval import hybrid_search, fetch_parent_chunks
from app.pipeline.online_phase.reranker import initial_judge, rerank_and_filter
from app.pipeline.online_phase.context_builder import build_context
from app.pipeline.online_phase.generator import generate_answer
from app.pipeline.online_phase.validator import validate_and_repair
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.analytics_event import AnalyticsEvent
from app.models.chatbot_setting import ChatbotSetting
from app.core.config import settings

logger = logging.getLogger(__name__)


def run_online_pipeline(
    question: str,
    school_id: UUID,
    visitor_id: str = "anonymous",
    conversation_id: Optional[UUID] = None,
    language: str = "en",
    db: Optional[Session] = None,
) -> dict:
    logger.info("=== Starting online pipeline (step 1/8) ===")

    # --- Step 1: Query Rewrite & Language Detection (multi-query expansion) ---
    history = _load_conversation_history(conversation_id, db) if db and conversation_id else []
    rewrite_result = rewrite_query(question, history)
    rewritten_queries = rewrite_result["rewritten_queries"]
    detected_language = rewrite_result["detected_language"]
    logger.info("Step 1 done — %d rewritten queries, lang=%s", len(rewritten_queries), detected_language)

    # --- Step 2+3: Embed + Hybrid Qdrant Search (for each query, merged) ---
    all_raw = {}
    for i, q in enumerate(rewritten_queries):
        chunks = hybrid_search(q, school_id)
        for c in chunks:
            cid = str(c.get("id"))
            if cid and cid not in all_raw:
                all_raw[cid] = c
    raw_chunks = sorted(all_raw.values(), key=lambda x: x.get("score", 0), reverse=True)[:settings.RAG_RRF_LIMIT]
    logger.info("Step 2+3 done — %d raw chunks from %d queries", len(raw_chunks), len(rewritten_queries))

    expanded_chunks = raw_chunks

    # --- Step 4: Retrieval Judge & Rerank ---
    if not initial_judge(expanded_chunks, rewritten_queries[0]):
        logger.info("Step 4.1 — no relevant chunks, returning fallback")
        fallback = _get_fallback_answer(detected_language, school_id, db)
        return _build_response(fallback, [], None, detected_language)

    parent_chunks = fetch_parent_chunks(expanded_chunks, db) if db else expanded_chunks

    # Use wider top_k for broad/list-style questions
    _list_keywords = r"list|programs?|degrees?|kinds?|types?|offered|available|what.*(?:program|degree|major|course|field|option)"
    is_broad = bool(re.search(_list_keywords, question, re.IGNORECASE))
    rerank_k = settings.RAG_FALLBACK_K if is_broad else settings.RAG_FINAL_K
    if is_broad:
        logger.info("Broad/list question detected — using top_k=%d for reranker", rerank_k)

    final_chunks = rerank_and_filter(parent_chunks, rewritten_queries[0], top_k=rerank_k)
    logger.info("Step 4 done — %d final chunks", len(final_chunks))

    if not final_chunks:
        logger.info("Step 4.2 — no chunks passed reranker threshold, returning fallback")
        fallback = _get_fallback_answer(detected_language, school_id, db)
        return _build_response(fallback, [], None, detected_language)

    # --- Step 5: Context Assembly ---
    context, allowed_citation_ids = build_context(final_chunks)
    logger.info("Step 5 done — %d chars context, %d citations",
                len(context), len(allowed_citation_ids))

    # --- Step 6: Answer Generation ---
    question_for_llm = f"Original question: {question}\nOptimized search query: {rewritten_queries[0]}"
    answer = generate_answer(question_for_llm, context, detected_language)
    logger.info("Step 6 done — answer=%d chars", len(answer))

    # --- Step 7: Validation ---
    answer, validated = validate_and_repair(
        answer, allowed_citation_ids, final_chunks,
        rewritten_queries[0], context, detected_language,
        school_id=school_id, db=db,
    )
    logger.info("Step 7 done — validated=%s", validated)

    # --- Step 8: Persistence ---
    conv_id = None
    if db:
        conv_id = _persist(question, answer, school_id, visitor_id,
                           conversation_id, language, detected_language,
                           validated, db)
    logger.info("Step 8 done — conv_id=%s", conv_id)

    # --- Build sources ---
    sources = []
    for i, chunk in enumerate(final_chunks[:5]):
        payload = chunk.get("payload", {})
        sources.append({
            "doc_id": f"doc_{i + 1}",
            "breadcrumb": chunk.get("breadcrumb") or payload.get("breadcrumb", ""),
            "source_file": payload.get("source_file", ""),
            "score": round(chunk.get("rerank_score", chunk.get("score", 0)), 3),
        })

    logger.info("=== Online pipeline complete ===")
    return _build_response(answer, sources, conv_id, detected_language)


def _load_conversation_history(
    conversation_id: Optional[UUID],
    db: Session,
) -> List[Dict[str, str]]:
    if not conversation_id:
        return []
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(8)
        .all()
    )
    return [{"role": m.sender_type, "content": m.content} for m in messages]


def _get_fallback_answer(
    detected_language: str,
    school_id: UUID,
    db: Optional[Session],
) -> str:
    from app.core.config import settings as app_settings
    email = app_settings.CONTACT_EMAIL or "the university admissions office"
    if db:
        setting = (
            db.query(ChatbotSetting)
            .filter(ChatbotSetting.school_id == school_id)
            .first()
        )
        if setting:
            if detected_language == "Arabic" and setting.fallback_message_ar:
                return setting.fallback_message_ar
            if detected_language == "English" and setting.fallback_message_en:
                return setting.fallback_message_en
    if detected_language == "Arabic":
        return app_settings.FALLBACK_MESSAGE_AR.format(CONTACT_EMAIL=email)
    return app_settings.FALLBACK_MESSAGE_EN.format(CONTACT_EMAIL=email)


def _persist(
    question: str,
    answer: str,
    school_id: UUID,
    visitor_id: str,
    conversation_id: Optional[UUID],
    language: str,
    detected_language: str,
    validated: bool,
    db: Session,
) -> UUID:
    if conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    else:
        conversation = None

    if not conversation:
        conversation = Conversation(
            school_id=school_id,
            visitor_id=visitor_id,
            language=detected_language[:10] if detected_language else language,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = Message(
        conversation_id=conversation.id,
        sender_type="user",
        content=question,
    )
    db.add(user_msg)

    bot_msg = Message(
        conversation_id=conversation.id,
        sender_type="bot",
        content=answer,
    )
    db.add(bot_msg)

    event = AnalyticsEvent(
        school_id=school_id,
        event_type="question_asked" if validated else "failed_answer",
        question_text=question,
        event_data={
            "conversation_id": str(conversation.id),
            "detected_language": detected_language,
        },
    )
    db.add(event)
    db.commit()

    return conversation.id


def _build_response(
    answer: str,
    sources: List[Dict[str, Any]],
    conversation_id: Optional[UUID],
    detected_language: str,
) -> dict:
    return {
        "answer": answer,
        "sources": sources,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "detected_language": detected_language,
    }
