from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 1024
    ALLOWED_FILE_TYPES: List[str] = ["pdf", "docx", "txt", "html"]
    LLAMA_PARSE_API: str
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # LLM (LM Studio)
    LLM_BASE_URL: str = "http://127.0.0.1:1234/api/v1"
    LLM_MODEL: str = "google/gemma-4-e2b"
    RAG_MODEL: str = "google/gemma-4-e2b"
    LLM_MAX_TOKENS: int = 8000
    REWRITE_MODEL: str = "mistralai/ministral-3-3b"

    # RAG
    RAG_DENSE_LIMIT: int = 50
    RAG_SPARSE_LIMIT: int = 50
    RAG_FINAL_K: int = 10
    RAG_FALLBACK_K: int = 15  # wider fallback for broad/list questions
    RAG_RRF_LIMIT: int = 35  # final fusion limit fed to reranker
    RAG_SCORE_THRESHOLD: float = 0.01  # set >0 to filter low-relevance chunks (see rerank score logs)
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # Fallback message (global default, per-tenant overrides in chatbot_settings)
    FALLBACK_MESSAGE_EN: str = "I don't have that information. Please contact {CONTACT_EMAIL} for assistance."
    FALLBACK_MESSAGE_AR: str = "ليس لدي هذه المعلومات. يرجى التواصل مع {CONTACT_EMAIL} للمساعدة."

    # Verification note (appended when Tier 2 flags unsubstantiated numbers)
    VERIFICATION_NOTE_EN: str = "\n\n---\n*Please verify the specific numbers, fees, and deadlines mentioned above with the relevant office for the most accurate and up-to-date information.*"
    VERIFICATION_NOTE_AR: str = "\n\n---\n*يرجى التحقق من الأرقام والرسوم والمواعيد النهائية المذكورة أعلاه مع الجهة المختصة للحصول على أدق وأحدث المعلومات.*"

    # University info (name is shown in bot responses)
    UNIVERSITY_NAME: str = "the university"
    CONTACT_EMAIL: str = ""
    CONTACT_PHONE: str = ""

    # Query rewrite history limits
    REWRITE_MAX_HISTORY_CHARS: int = 2000
    REWRITE_MAX_TURN_CHARS: int = 400

    class Config:
        env_file = str(Path(__file__).resolve().parents[2] / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
