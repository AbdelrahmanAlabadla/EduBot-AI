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

    class Config:
        env_file = str(Path(__file__).resolve().parents[2] / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
