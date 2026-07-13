import logging
from pathlib import Path
from typing import List

from llama_parse import LlamaParse
from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {f".{ext}" for ext in settings.ALLOWED_FILE_TYPES}


def _validate_file(file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{path.suffix}'. Allowed: {settings.ALLOWED_FILE_TYPES}"
        )
    return path


def ingest_file(file_path: str | Path) -> List[Document]:
    path = _validate_file(file_path)
    logger.info("Ingesting file with LlamaParse: %s", path.name)

    loader = LlamaParse(
        api_key=settings.LLAMA_PARSE_API,
        result_type="markdown",
        verbose=False,
        language="en",
    )

    try:
        docs = loader.load_langchain_documents(file_path=str(path))
    except Exception:
        logger.exception("LlamaParse failed for: %s", path.name)
        raise

    if not docs:
        logger.warning("LlamaParse returned no documents for: %s", path.name)
        return []

    for i, doc in enumerate(docs):
        doc.metadata["page_number"] = i + 1
        doc.metadata["source_file"] = path.name

    logger.info("LlamaParse returned %d pages for: %s", len(docs), path.name)
    return docs
