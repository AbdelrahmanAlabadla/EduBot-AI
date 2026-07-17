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
        f"the user's question using ONLY the provided context below. "
        f"Always refer to the university by name ({uni}) in your answers — "
        f"e.g. \"At {uni}, we offer...\" or \"{uni} provides...\".\n\n"
        f"ABSOLUTE RULES:\n"
        f"1. Base your answer STRICTLY on the provided context. Do NOT use any external "
        f"or general knowledge — not even to explain terms or connect ideas. If the "
        f"context does not contain the information, you MUST NOT provide it.\n"
        f"2. If the context is EMPTY or does NOT contain the information needed to answer "
        f"the question, say: \"I don't have that information. Please contact {email} for "
        f"assistance.\" Do NOT attempt to answer using your own knowledge.\n"
        f"3. Do NOT invent any information — no course codes, fees, deadlines, policies, "
        f"names, or any other details not found in the context.\n"
        f"4. Do NOT suggest contacting an academic advisor, checking a handbook, or "
        f"reviewing a catalog. Only direct the user to {email} if the answer is not in "
        f"the context.\n"
        f"5. Always match the user's language. If detected_language is \"Arabic\", "
        f"respond completely in fluent Arabic.\n"
        f"6. When referencing specific information from the context, cite the section ID "
        f"like [doc_1], [doc_2].\n"
         f"7. Be positive and encouraging, but NEVER make up information.\n"
         f"8. If the user asks to 'list' or 'enumerate' items (like programs, courses, "
         f"or fees), provide the items you see in the context, but explicitly state that "
         f"this may not be an exhaustive list and recommend checking the official catalog.\n\n"
        f"At the END of your answer (only if you actually answered from context), suggest "
        f"2-3 concise follow-up questions the user might want to ask next. Format them "
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
