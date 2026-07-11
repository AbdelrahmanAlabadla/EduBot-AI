import logging
from pathlib import Path
from typing import List
from uuid import UUID

from langchain_core.documents import Document
from sqlalchemy.orm import Session

from app.pipeline.offline_phase.ingestion import ingest_file
from app.pipeline.offline_phase.parser import parse_documents
from app.pipeline.offline_phase.boilerplate import detect_boilerplate
from app.pipeline.offline_phase.clean_norm import clean_and_normalize, STRUCTURAL_PATTERNS
from app.pipeline.offline_phase.chunking import chunk_documents
from app.pipeline.offline_phase.embedding import embed_chunks
from app.pipeline.offline_phase.qdrant import store_in_qdrant

logger = logging.getLogger(__name__)


def run_offline_pipeline(
    file_path: str | Path,
    school_id: UUID,
    document_id: UUID,
    db: Session,
) -> List[Document]:
    logger.info("=== Starting offline pipeline ===")
    logger.info("File: %s | School: %s | Doc: %s", file_path, school_id, document_id)

    raw_docs = ingest_file(file_path)
    if not raw_docs:
        logger.warning("No documents returned from ingestion, aborting pipeline.")
        return []

    blocks = parse_documents(raw_docs)
    logger.info("Parsed %d blocks from document.", len(blocks))

    # Strip known structural patterns FIRST so boilerplate detection operates on clean content
    for block in blocks:
        text = block["content"]
        for pattern in STRUCTURAL_PATTERNS:
            text = pattern.sub("", text)
        block["content"] = text

    boilerplate_patterns = detect_boilerplate(blocks)
    if boilerplate_patterns:
        logger.info("Detected %d boilerplate pattern(s).", len(boilerplate_patterns))

    cleaned = clean_and_normalize(blocks, extra_patterns=boilerplate_patterns)
    logger.info("Cleaned %d blocks.", len(cleaned))

    chunks = chunk_documents(cleaned, document_id, school_id, extra_boilerplate=boilerplate_patterns)
    logger.info("Created %d chunks (%d child).",
                len(chunks),
                sum(1 for c in chunks if c.metadata.get("chunk_type") == "child"))

    embedded = embed_chunks(chunks)

    store_in_qdrant(embedded, school_id, db=db)

    logger.info("=== Offline pipeline complete ===")
    return embedded
