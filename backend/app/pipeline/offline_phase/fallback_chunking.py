import logging
import re
from typing import List, Dict, Any, Optional
from uuid import UUID

import numpy as np
from langchain_core.documents import Document

from app.pipeline.offline_phase.chunking import (
    TOKENIZER,
    _is_table,
    _is_faq,
    _is_list,
    _is_callout,
    _is_contact,
    _is_procedure,
    _create_table_chunk,
    _create_faq_chunks,
    _create_list_chunk,
    _create_callout_chunk,
    _create_contact_chunk,
    _create_procedure_chunk,
    _create_single,
    _get_semantic_embedder,
    SEARCHABLE_TYPES,
)

logger = logging.getLogger(__name__)

CHILD_MAX_TOKENS = 600
CHILD_MIN_TOKENS = 250
SIMILARITY_THRESHOLD = 0.65


def _classify_block(text: str) -> str:
    if _is_table(text):
        return "table"
    if _is_faq(text):
        return "faq"
    if _is_procedure(text):
        return "procedure"
    if _is_callout(text):
        return "callout"
    if _is_list(text):
        return "list"
    if _is_contact(text):
        return "contact"
    return "prose"


def fallback_chunk_documents(
    blocks: List[Dict[str, Any]],
    document_id: UUID,
    school_id: UUID,
    document_version: Optional[str] = None,
    effective_date: Optional[str] = None,
) -> List[Document]:
    # Concatenate all cleaned block text with page info
    paragraphs = []
    for block in blocks:
        content = block.get("content", "").strip()
        if not content:
            continue
        src = block.get("source_metadata", {})
        page_number = src.get("page_number")
        source_file = src.get("source_file")
        for para in re.split(r"\n\s*\n", content):
            para = para.strip()
            if not para:
                continue
            paragraphs.append((para, page_number, source_file))

    if not paragraphs:
        return []

    # Group consecutive paragraphs of the same type
    groups: List[Dict] = []
    current_type = None
    current_texts: List[str] = []
    current_pages = set()
    current_files = set()

    for para_text, page, src_file in paragraphs:
        ptype = _classify_block(para_text)

        if current_type is None:
            current_type = ptype
            current_texts = [para_text]
            current_pages.add(page)
            current_files.add(src_file)
        elif ptype == current_type:
            current_texts.append(para_text)
            if page is not None:
                current_pages.add(page)
            if src_file:
                current_files.add(src_file)
        else:
            groups.append({
                "type": current_type,
                "texts": current_texts,
                "pages": sorted(current_pages) if current_pages else None,
                "files": list(current_files) if current_files else None,
            })
            current_type = ptype
            current_texts = [para_text]
            current_pages = {page} if page is not None else set()
            current_files = {src_file} if src_file else set()

    if current_texts:
        groups.append({
            "type": current_type,
            "texts": current_texts,
            "pages": sorted(current_pages) if current_pages else None,
            "files": list(current_files) if current_files else None,
        })

    # Create chunks from each group
    chunks: List[Document] = []
    for group in groups:
        group_text = "\n\n".join(group["texts"])
        page_number = group["pages"][0] if group["pages"] else None
        source_file = group["files"][0] if group["files"] else None

        if group["type"] == "prose":
            tokens = TOKENIZER.encode(group_text)
            if len(tokens) <= CHILD_MAX_TOKENS:
                chunk = _create_single(
                    group_text, "",
                    None, document_id, school_id,
                    page_number, source_file,
                )
                chunks.append(chunk)
            else:
                embedder = _get_semantic_embedder()
                child_chunks = _semantic_split_fallback(
                    group_text, "", None, document_id, school_id,
                    embedder, page_number, source_file,
                )
                chunks.extend(child_chunks)
        elif group["type"] == "table":
            chunk = _create_table_chunk(
                group_text, "", None,
                document_id, school_id,
                page_number, source_file,
            )
            chunks.append(chunk)
        elif group["type"] == "faq":
            faq_chunks = _create_faq_chunks(
                group_text, "", None,
                document_id, school_id,
                page_number, source_file,
            )
            chunks.extend(faq_chunks)
        elif group["type"] == "list":
            chunk = _create_list_chunk(
                group_text, "", None,
                document_id, school_id,
                page_number, source_file,
            )
            chunks.append(chunk)
        elif group["type"] == "callout":
            chunk = _create_callout_chunk(
                group_text, "", None,
                document_id, school_id,
                page_number, source_file,
            )
            chunks.append(chunk)
        elif group["type"] == "contact":
            chunk = _create_contact_chunk(
                group_text, "", None,
                document_id, school_id,
                page_number, source_file,
            )
            chunks.append(chunk)
        elif group["type"] == "procedure":
            chunk = _create_procedure_chunk(
                group_text, "", None,
                document_id, school_id,
                page_number, source_file,
            )
            chunks.append(chunk)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_order"] = i
        if document_version is not None:
            chunk.metadata["document_version"] = document_version
        if effective_date is not None:
            chunk.metadata["effective_date"] = effective_date

    logger.info("Fallback chunking: %d chunks created (%d prose, %d classified)",
                len(chunks),
                sum(1 for c in chunks if c.metadata.get("chunk_type") == "single"),
                sum(1 for c in chunks if c.metadata.get("chunk_type") != "single"))

    return chunks


def _semantic_split_fallback(
    text: str,
    breadcrumb: str,
    parent_id: Optional[str],
    document_id: UUID,
    school_id: UUID,
    embedder,
    page_number: Optional[int] = None,
    source_file: Optional[str] = None,
) -> List[Document]:
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
    if len(sentences) <= 1:
        return [_create_single(text.strip(), breadcrumb, parent_id, document_id, school_id,
                               page_number, source_file)]

    embeddings = embedder.encode(sentences, return_dense=True, return_sparse=False)["dense_vecs"]

    similarities = []
    for i in range(len(embeddings) - 1):
        sim = float(np.dot(embeddings[i], embeddings[i + 1]) /
                    (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i + 1])))
        similarities.append(sim)

    breakpoints = {i + 1 for i, sim in enumerate(similarities) if sim < SIMILARITY_THRESHOLD}

    groups = _build_sentence_groups(sentences, breakpoints)

    children = []
    overlap = ""
    for group in groups:
        child_text = " ".join(group).strip()
        if not child_text:
            continue
        if overlap:
            child_text = overlap + " " + child_text
        children.append(_create_single(child_text, breadcrumb, parent_id, document_id, school_id,
                                       page_number, source_file))
        overlap = _get_last_sentence(" ".join(group))

    return children


def _get_last_sentence(text: str, n: int = 2) -> str:
    sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
    return " ".join(sents[-n:]).strip() if len(sents) >= n else (sents[-1] if sents else "")


def _build_sentence_groups(
    sentences: List[str],
    breakpoints: set,
) -> List[List[str]]:
    groups = []
    current = []
    current_tokens = []

    for i, sent in enumerate(sentences):
        sent_tokens = TOKENIZER.encode(sent)
        if current_tokens and len(current_tokens) + len(sent_tokens) > CHILD_MAX_TOKENS:
            groups.append(current)
            current = [sent]
            current_tokens = sent_tokens
            continue

        current.append(sent)
        current_tokens.extend(sent_tokens)

        if (i + 1) in breakpoints and len(current_tokens) >= CHILD_MIN_TOKENS:
            groups.append(current)
            current = []
            current_tokens = []

    if current:
        groups.append(current)

    return groups
