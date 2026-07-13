import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def generate_answer(
    question: str,
    context: str,
    detected_language: str = "English",
    conversation_history: Optional[str] = None,
) -> str:
    uni = settings.UNIVERSITY_NAME
    email = settings.CONTACT_EMAIL or "the university admissions office"
    system_prompt = (
        f"You are a helpful admissions assistant for **{uni}**. Your goal is to answer "
        f"the user's question using the provided context below. "
        f"Always refer to the university by name ({uni}) in your answers — "
        f"e.g. \"At {uni}, we offer...\" or \"{uni} provides...\".\n\n"
        f"Base your answer ONLY on the provided context. Do NOT suggest contacting "
        f"an academic advisor, checking a handbook, or reviewing a catalog. "
        f"If the context contains the information, answer clearly and directly. "
        f"If the context does NOT contain the information needed to answer the "
        f"question, say you don't have that information and tell the user to contact "
        f"{email} for assistance.\n\n"
        f"Do NOT invent specific numbers, fees, or policies not present in the "
        f"context. You may use general knowledge to explain terms or connect ideas, "
        f"but clearly distinguish what is from the context vs. general knowledge.\n\n"
        f"Always match the user's language. If detected_language is \"Arabic\", "
        f"respond completely in fluent Arabic, even if the source text blocks below "
        f"are in English (and vice versa). Synthesize across languages naturally.\n\n"
        f"When referencing specific information from the context, cite the section ID "
        f"like [doc_1], [doc_2]. Be positive and encouraging.\n\n"
        f"At the END of your answer, suggest 2-3 concise follow-up questions the "
        f"user might want to ask next, based on the query and context. Format them "
        f"as:\n"
        f"---\n"
        f"**Recommended questions:**\n"
        f"- <question 1>\n"
        f"- <question 2>\n"
        f"- <question 3>"
    )

    user_content = f"Context:\n{context}\n\n"
    if conversation_history:
        user_content += f"Conversation history:\n{conversation_history}\n\n"
    user_content += (
        f"Detected language for response: {detected_language}\n\n"
        f"Question: {question}\n\n"
        f"Answer in {detected_language}:"
    )

    url = f"{settings.LLM_BASE_URL}/chat"
    payload = {
        "model": settings.LLM_MODEL,
        "system_prompt": system_prompt,
        "input": [{"type": "text", "content": user_content}],
        "temperature": 0.3,
        "max_output_tokens": settings.LLM_MAX_TOKENS,
        "stream": False,
    }

    logger.info("Generating answer (%s, %s)...", settings.LLM_MODEL, detected_language)

    try:
        import requests
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        answer = _extract_text(data)
        if not answer:
            logger.warning("LLM returned empty answer")
            answer = _fallback_answer(detected_language)
        logger.info("Answer generated (%d chars)", len(answer))
        return answer
    except Exception as e:
        logger.error("Answer generation failed: %s", e)
        return _fallback_answer(detected_language)


def _extract_text(data: dict) -> str:
    full = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            full += item.get("content", "")
    return full.strip()


def _fallback_answer(language: str) -> str:
    contact = settings.CONTACT_EMAIL or "the university admissions office"
    if language == "Arabic":
        return (
            "عذرًا، حدث خطأ أثناء إنشاء الرد. يرجى إعادة المحاولة لاحقًا "
            "أو الاتصال بالمدرسة على البريد الإلكتروني: " + contact
        )
    return (
        f"I'm sorry, an error occurred while generating the response. "
        f"Please try again later or contact {contact}."
    )
