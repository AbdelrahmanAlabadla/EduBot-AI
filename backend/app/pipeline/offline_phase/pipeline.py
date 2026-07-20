import logging
import os
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from langchain_core.documents import Document
from sqlalchemy.orm import Session

from app.pipeline.offline_phase.ingestion import ingest_file
from app.pipeline.offline_phase.parser import parse_documents
from app.pipeline.offline_phase.boilerplate import detect_boilerplate
from app.pipeline.offline_phase.clean_norm import clean_and_normalize, STRUCTURAL_PATTERNS
from app.pipeline.offline_phase.chunking import chunk_documents
from app.pipeline.offline_phase.summarizer import generate_parent_summaries
from app.pipeline.offline_phase.embedding import embed_chunks
from app.pipeline.offline_phase.qdrant import store_in_qdrant
from app.pipeline.offline_phase.structure_validator import validate_structure
from app.pipeline.offline_phase.fallback_chunking import fallback_chunk_documents

logger = logging.getLogger(__name__)

# Threshold for routing to fallback chunking.
# Set STRUCTURE_THRESHOLD=<0-100> in environment to enable routing.
# Default 0 = always use hierarchical chunking (log-only mode).
STRUCTURE_THRESHOLD = int(os.environ.get("STRUCTURE_THRESHOLD", "0"))


def run_offline_pipeline(
    file_path: str | Path,
    school_id: UUID,
    document_id: UUID,
    db: Session,
    document_version: Optional[str] = None,
    effective_date: Optional[str] = None,
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

    # --- Phase 1: Structure validation ---
    report = validate_structure(cleaned)
    logger.info("Structure score: %d/100 (threshold=%d, thresholding=%s)",
                report.score, STRUCTURE_THRESHOLD,
                "enabled" if STRUCTURE_THRESHOLD > 0 else "disabled (log-only)")

    # --- Routing decision ---
    if STRUCTURE_THRESHOLD > 0 and report.score < STRUCTURE_THRESHOLD:
        logger.warning("Structure score %d < threshold %d — using fallback chunking.",
                       report.score, STRUCTURE_THRESHOLD)
        chunks = fallback_chunk_documents(
            cleaned, document_id, school_id,
            document_version=document_version,
            effective_date=effective_date,
        )
        logger.info("Fallback created %d chunks.", len(chunks))
    else:
        chunks = chunk_documents(
            cleaned, document_id, school_id,
            extra_boilerplate=boilerplate_patterns,
            document_version=document_version,
            effective_date=effective_date,
        )
        logger.info("Created %d chunks (%d child).",
                    len(chunks),
                    sum(1 for c in chunks if c.metadata.get("chunk_type") == "child"))

        # Generate summary chunks for parent sections (3 concurrent LM Studio calls)
        parent_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "parent"]
        if parent_chunks:
            summary_chunks = generate_parent_summaries(parent_chunks, document_id, school_id)
            chunks.extend(summary_chunks)
            logger.info("Generated %d summary chunks.", len(summary_chunks))

    # Re-assign chunk_order so new summary chunks get valid sequential IDs
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_order"] = i

    embedded = embed_chunks(chunks)

    store_in_qdrant(embedded, school_id, db=db)

    logger.info("=== Offline pipeline complete ===")
    return embedded
