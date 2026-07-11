import logging
import re
import sys
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4

import spacy
from transformers import AutoTokenizer
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

TOKENIZER = AutoTokenizer.from_pretrained("BAAI/bge-m3")
CHILD_MIN_TOKENS = 250
CHILD_MAX_TOKENS = 400

HEADING_SPLIT_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
FAQ_Q_PATTERN = re.compile(r"^\*{0,2}Q\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
FAQ_A_PATTERN = re.compile(r"^\*{0,2}A\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
SECTION_NUM_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)\s*[\.\)\-]\s+")

# Chunk-type constants shared across the pipeline
SEARCHABLE_TYPES = {"child", "single"}
CONTEXT_TYPES = {"parent", "single"}

# Hardcoded boilerplate blocklist — low false-positive, always-on
BOILERPLATE_BLOCKLIST: List[re.Pattern] = [
    re.compile(r"^Curtin University Dubai$"),
    re.compile(r"^RAS AL KHAIMAH DEPARTMENT OF KNOWLEDGE$"),
    re.compile(r"^Ras Al Khaimah Department of Knowledge$"),
    re.compile(r"^Ras Al Khaimah Department of Knowledge - Government of Ras Al Khaimah$"),
    re.compile(r"^Page \d+ of \d+ Issue Date:.*$"),
    re.compile(r"^\d+ of \d+ CRICOS Provider Code.*$"),
    re.compile(r"^©?Open Training College Page \d+ of \d+$"),
    re.compile(r"^\d+ \| P a g e$"),
    re.compile(r"^Effective Date:.*$"),
    re.compile(r"^Last Review date:.*$"),
    re.compile(r"^Policy Number:.*$"),
    re.compile(r"^Next Review date:.*$"),
    re.compile(r"^Responsible Entity:.*$"),
]

AUTO_BOILERPLATE_MIN_WORDS = 4
AUTO_BOILERPLATE_MIN_CHARS = 25
TINY_CHUNK_TOKEN_THRESHOLD = 25

_nlp = None


def _get_sentencizer():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("xx_sent_ud_sm")
        except OSError:
            logger.info("Downloading spaCy model xx_sent_ud_sm...")
            import subprocess
            subprocess.run(
                [sys.executable, "-m", "spacy", "download", "xx_sent_ud_sm"],
                check=True,
            )
            _nlp = spacy.load("xx_sent_ud_sm")
    return _nlp


def split_sentences(text: str) -> List[str]:
    doc = _get_sentencizer()(text)
    return [sent.text.strip() for sent in doc.sents]


def get_last_sentence(text: str) -> str:
    sents = split_sentences(text)
    return sents[-1] if len(sents) > 1 else ""


def _infer_heading_depth(heading: str) -> int:
    m = SECTION_NUM_PATTERN.match(heading)
    if m:
        return len(m.group(1).split("."))
    return 0


def _split_markdown_into_sections(text: str) -> List[tuple]:
    parts = HEADING_SPLIT_PATTERN.split(text)
    sections = []
    if parts[0].strip():
        sections.append((0, "", parts[0].strip()))
    for i in range(1, len(parts) - 1, 3):
        level = len(parts[i])
        heading = parts[i + 1].strip()
        body = parts[i + 2].strip() if i + 2 < len(parts) else ""
        sections.append((level, heading, body))
    return sections


def _is_table(text: str) -> bool:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    pipe_lines = sum(1 for l in lines if l.startswith("|") and l.endswith("|"))
    return pipe_lines >= 2 and (pipe_lines / len(lines)) > 0.5


def _is_faq(text: str) -> bool:
    has_q = bool(FAQ_Q_PATTERN.search(text))
    has_a = bool(FAQ_A_PATTERN.search(text))
    return has_q or has_a


def _is_boilerplate(text: str, extra_patterns: Optional[List[re.Pattern]] = None) -> bool:
    all_patterns = list(BOILERPLATE_BLOCKLIST)
    if extra_patterns:
        all_patterns.extend(extra_patterns)
    stripped = text.strip()
    if not stripped:
        return False

    for pattern in all_patterns:
        if pattern.fullmatch(stripped):
            return True

    lines = [l.strip() for l in stripped.split("\n") if l.strip()]
    if len(lines) >= 2:
        non_empty_lines = len(lines)
        matched_lines = 0
        for line in lines:
            for pattern in all_patterns:
                if pattern.fullmatch(line):
                    matched_lines += 1
                    break
        if matched_lines == non_empty_lines:
            return True

    # Multi-line auto-detected patterns won't fullmatch individual lines, so
    # try a search-based check: if an auto-detected pattern matches anywhere
    # in the full text, the chunk contains known boilerplate sequence(s).
    if extra_patterns:
        for pattern in extra_patterns:
            if pattern.search(stripped):
                return True

    return False


def _prev_chunk_incomplete(chunks: List[Document]) -> bool:
    if not chunks:
        return False
    last = chunks[-1].page_content.strip()
    return bool(last) and not last.endswith((".", "?", "!"))


def _is_structural_fragment(text: str) -> bool:
    return bool(text) and not text.strip().endswith((".", "?", "!"))


def post_process_chunks(
    chunks: List[Document],
    auto_boilerplate_patterns: Optional[List[re.Pattern]] = None,
) -> List[Document]:
    if not chunks:
        return chunks

    extra_patterns = []
    if auto_boilerplate_patterns:
        for p in auto_boilerplate_patterns:
            extra_patterns.append(p)

    filtered: List[Document] = []
    i = 0
    dropped = 0
    merged_forward = 0
    merged_backward = 0

    while i < len(chunks):
        chunk = chunks[i]
        if chunk.metadata.get("chunk_type") == "table":
            filtered.append(chunk)
            i += 1
            continue

        text = chunk.page_content.strip()
        tokens = TOKENIZER.encode(text)

        if _is_boilerplate(text, extra_patterns):
            logger.info("Dropping boilerplate chunk (%d tokens): %.80s", len(tokens), text)
            dropped += 1
            i += 1
            continue

        if len(tokens) >= TINY_CHUNK_TOKEN_THRESHOLD:
            filtered.append(chunk)
            i += 1
            continue

        is_fragment = _is_structural_fragment(text)

        if is_fragment and i + 1 < len(chunks):
            next_is_table = chunks[i + 1].metadata.get("chunk_type") == "table"
            if not next_is_table:
                chunks[i + 1].page_content = text + "\n\n" + chunks[i + 1].page_content
                logger.info("Merged fragment forward (%d tokens): %.80s -> chunk %d", len(tokens), text, i + 1)
                merged_forward += 1
                i += 1
                continue
            else:
                if filtered:
                    filtered[-1].page_content += "\n" + text
                    logger.info("Merged fragment backward (next is table, %d tokens): %.80s", len(tokens), text)
                    merged_backward += 1
                    i += 1
                    continue

        if _prev_chunk_incomplete(filtered):
            filtered[-1].page_content += "\n" + text
            logger.info("Merged fragment backward (%d tokens): %.80s", len(tokens), text)
            merged_backward += 1
            i += 1
            continue

        logger.info("Dropping orphan chunk (%d tokens): %.80s", len(tokens), text)
        dropped += 1
        i += 1

    for j, doc in enumerate(filtered):
        doc.metadata["chunk_order"] = j

    if dropped or merged_forward or merged_backward:
        logger.info(
            "Post-process: %d dropped, %d merged forward, %d merged backward (final %d chunks)",
            dropped, merged_forward, merged_backward, len(filtered),
        )

    return filtered


def chunk_documents(
    blocks: List[Dict[str, Any]],
    document_id: UUID,
    school_id: UUID,
    extra_boilerplate: Optional[List[re.Pattern]] = None,
) -> List[Document]:
    heading_stack: List[str] = []
    section_root_depth: int = 0
    all_chunks: List[Document] = []
    pending_heading: Optional[str] = None

    for block in blocks:
        if block.get("type") != "raw_markdown":
            continue

        content = block["content"]
        src = block.get("source_metadata", {})
        page_number = src.get("page_number")
        source_file = src.get("source_file")

        sections = _split_markdown_into_sections(content)

        if pending_heading and sections:
            lvl, hdg, body = sections[0]
            if hdg == "" and body.strip() == pending_heading:
                sections.pop(0)
            elif lvl > 0 and hdg == pending_heading and not body.strip():
                sections.pop(0)
            pending_heading = None

        for level, heading, body in sections:
            numeric_depth = _infer_heading_depth(heading) if heading else 0

            if heading and not body.strip():
                pending_heading = heading
                continue

            if numeric_depth > 0:
                effective_level = numeric_depth
                section_root_depth = numeric_depth
            elif level > 1:
                effective_level = level
            else:
                effective_level = (section_root_depth + 1) if section_root_depth > 0 and heading else level

            while len(heading_stack) >= effective_level and effective_level > 0:
                heading_stack.pop()
            if heading:
                heading_stack.append(heading)

            breadcrumb = " > ".join(heading_stack) if heading_stack else ""
            section_content = f"{heading}\n\n{body}" if heading else body

            if _is_table(section_content):
                chunk = _chunk_table(section_content, breadcrumb, document_id, school_id, page_number, source_file)
                all_chunks.append(chunk)
            elif _is_faq(section_content):
                faq_chunks = _chunk_faq(section_content, breadcrumb, document_id, school_id, page_number, source_file)
                all_chunks.extend(faq_chunks)
            else:
                prose_chunks = _chunk_section(section_content, breadcrumb, document_id, school_id, page_number, source_file)
                all_chunks.extend(prose_chunks)

    all_chunks = post_process_chunks(all_chunks, auto_boilerplate_patterns=extra_boilerplate)

    return all_chunks


def _chunk_table(
    text: str, breadcrumb: str, document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
) -> Document:
    searchable = _table_to_sentence(text)
    doc = Document(
        page_content=text,
        metadata={
            "chunk_type": "table",
            "breadcrumb": breadcrumb,
            "parent_id": None,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": searchable,
        },
    )
    doc.metadata["page_number"] = page_number
    doc.metadata["source_file"] = source_file
    return doc


def _table_to_sentence(table_md: str) -> str:
    lines = [l.strip() for l in table_md.split("\n") if l.strip()]
    if not lines:
        return table_md
    header_line = None
    for l in lines:
        if l.startswith("|") and l.endswith("|") and "---" not in l:
            header_line = l
            break
    if not header_line:
        return table_md
    headers = [h.strip() for h in header_line.strip("|").split("|")]

    data_lines = [l for l in lines if l.startswith("|") and "---" not in l and l != header_line]
    sentences = []
    for dl in data_lines:
        cells = [c.strip() for c in dl.strip("|").split("|")]
        parts = []
        for i, cell in enumerate(cells):
            if i < len(headers) and cell and headers[i]:
                parts.append(f"{headers[i]} is {cell}")
        if parts:
            sentences.append(". ".join(parts))
    return " ".join(sentences)


def _chunk_faq(
    text: str, breadcrumb: str, document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
) -> List[Document]:
    q_matches = list(FAQ_Q_PATTERN.finditer(text))
    a_matches = list(FAQ_A_PATTERN.finditer(text))

    if not q_matches:
        doc = Document(
            page_content=text,
            metadata={
                "chunk_type": "faq",
                "breadcrumb": breadcrumb,
                "parent_id": None,
                "document_id": str(document_id),
                "school_id": str(school_id),
                "searchable_text": text,
            },
        )
        doc.metadata["page_number"] = page_number
        doc.metadata["source_file"] = source_file
        return [doc]

    lines = text.split("\n")
    qa_pairs = _extract_qa_pairs(lines)
    chunks = []
    for q, a in qa_pairs:
        combined = f"Q: {q}\nA: {a}"
        searchable = f"Question: {q} Answer: {a}"
        doc = Document(
            page_content=combined,
            metadata={
                "chunk_type": "faq",
                "breadcrumb": breadcrumb,
                "parent_id": None,
                "document_id": str(document_id),
                "school_id": str(school_id),
                "searchable_text": searchable,
            },
        )
        doc.metadata["page_number"] = page_number
        doc.metadata["source_file"] = source_file
        chunks.append(doc)
    return chunks


def _extract_qa_pairs(lines: List[str]) -> List[tuple[str, str]]:
    pairs = []
    current_q = None
    current_a_lines = []

    for line in lines:
        q_match = FAQ_Q_PATTERN.match(line)
        a_match = FAQ_A_PATTERN.match(line)

        if q_match:
            if current_q and current_a_lines:
                pairs.append((current_q, "\n".join(current_a_lines).strip()))
                current_a_lines = []
            current_q = q_match.group(1).strip()
        elif a_match:
            current_a_lines.append(a_match.group(1).strip())
        elif current_q is not None:
            current_a_lines.append(line)

    if current_q:
        pairs.append((current_q, "\n".join(current_a_lines).strip()))
    return pairs


def _chunk_section(
    text: str, breadcrumb: str, document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
) -> List[Document]:
    tokens = TOKENIZER.encode(text)
    token_count = len(tokens)

    if token_count <= CHILD_MIN_TOKENS:
        doc = Document(
            page_content=text,
            metadata={
                "chunk_type": "single",
                "breadcrumb": breadcrumb,
                "parent_id": None,
                "document_id": str(document_id),
                "school_id": str(school_id),
                "searchable_text": None,
            },
        )
        doc.metadata["page_number"] = page_number
        doc.metadata["source_file"] = source_file
        return [doc]

    if token_count <= CHILD_MAX_TOKENS:
        doc = Document(
            page_content=text,
            metadata={
                "chunk_type": "single",
                "breadcrumb": breadcrumb,
                "parent_id": None,
                "document_id": str(document_id),
                "school_id": str(school_id),
                "searchable_text": None,
            },
        )
        doc.metadata["page_number"] = page_number
        doc.metadata["source_file"] = source_file
        return [doc]

    parent_id = str(uuid4())
    parent = Document(
        page_content=text,
        metadata={
            "chunk_type": "parent",
            "breadcrumb": breadcrumb,
            "parent_id": None,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": None,
        },
    )
    parent.metadata["page_number"] = page_number
    parent.metadata["source_file"] = source_file

    children = _split_into_children(text, breadcrumb, parent_id, document_id, school_id, page_number, source_file)
    return [parent] + children


def _split_into_children(
    text: str, breadcrumb: str, parent_id: str,
    document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
) -> List[Document]:
    sentences = split_sentences(text)
    children = []
    current_sents = []
    current_tokens = []
    overlap = ""

    for sent in sentences:
        sent_tokens = TOKENIZER.encode(sent)
        if current_tokens and len(current_tokens) + len(sent_tokens) > CHILD_MAX_TOKENS:
            child_text = " ".join(current_sents).strip()
            if child_text:
                if overlap:
                    child_text = overlap + " " + child_text
                children.append(_make_child(child_text, breadcrumb, parent_id, document_id, school_id, page_number, source_file))
            overlap = get_last_sentence(" ".join(current_sents)) if current_sents else ""
            current_sents = [sent]
            current_tokens = sent_tokens
        else:
            current_sents.append(sent)
            current_tokens.extend(sent_tokens)

    if current_sents:
        child_text = " ".join(current_sents).strip()
        if child_text:
            if overlap:
                child_text = overlap + " " + child_text
            children.append(_make_child(child_text, breadcrumb, parent_id, document_id, school_id, page_number, source_file))

    return children


def _make_child(
    text: str, breadcrumb: str, parent_id: str,
    document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
) -> Document:
    doc = Document(
        page_content=text,
        metadata={
            "chunk_type": "child",
            "breadcrumb": breadcrumb,
            "parent_id": parent_id,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": None,
        },
    )
    doc.metadata["page_number"] = page_number
    doc.metadata["source_file"] = source_file
    return doc
