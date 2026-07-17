import logging
import re
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4

import numpy as np
import spacy
from transformers import AutoTokenizer
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

TOKENIZER = AutoTokenizer.from_pretrained("BAAI/bge-m3")
CHILD_MIN_TOKENS = 250
CHILD_MAX_TOKENS = 600
SIMILARITY_THRESHOLD = 0.65

HEADING_SPLIT_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
FAQ_Q_PATTERN = re.compile(r"^\*{0,2}Q\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
FAQ_A_PATTERN = re.compile(r"^\*{0,2}A\s*[:：]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
SECTION_NUM_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)\s*[\.\)\-]\s+")

SEARCHABLE_TYPES = {"child", "single", "table", "summary"}
CONTEXT_TYPES = {"parent", "single"}

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


# ---------------------------------------------------------------------------
# Tree data structures
# ---------------------------------------------------------------------------

@dataclass
class _SectionNode:
    heading: str
    level: int
    breadcrumb: str
    content: str
    children: List["_SectionNode"] = field(default_factory=list)
    parent: Optional["_SectionNode"] = None
    page_number: Optional[int] = None
    source_file: Optional[str] = None
    is_parent: bool = False
    uuid: Optional[str] = None
    leaf_type: Optional[str] = None
    parent_id: Optional[str] = None
    leaf_tokens: int = 0

    def text(self) -> str:
        if self.heading:
            return f"{self.heading}\n\n{self.content}" if self.content else self.heading
        return self.content

    def full_subtree_text(self) -> str:
        parts = []
        if self.heading:
            parts.append(self.heading)
        if self.content:
            parts.append(self.content)
        for c in self.children:
            child_text = c.full_subtree_text()
            if child_text:
                parts.append(child_text)
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# spaCy sentencizer
# ---------------------------------------------------------------------------

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


def get_last_sentence(text: str, n: int = 2) -> str:
    sents = split_sentences(text)
    return " ".join(sents[-n:]).strip() if len(sents) >= n else (sents[-1] if sents else "")


def _infer_heading_depth(heading: str) -> int:
    m = SECTION_NUM_PATTERN.match(heading)
    if m:
        return len(m.group(1).split("."))
    return 0


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _split_markdown_into_sections(text: str) -> List[Tuple[int, str, str]]:
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


# ---------------------------------------------------------------------------
# Content classification
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Table helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# FAQ helper
# ---------------------------------------------------------------------------

def _extract_qa_pairs(lines: List[str]) -> List[Tuple[str, str]]:
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


# ---------------------------------------------------------------------------
# BGE-M3 embedder for semantic splitting (lazy, freed after use)
# ---------------------------------------------------------------------------

def _get_semantic_embedder():
    from FlagEmbedding import BGEM3FlagModel
    return BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device="cpu")


# ---------------------------------------------------------------------------
# Tree building
# ---------------------------------------------------------------------------

def _build_heading_tree(all_sections: List[Tuple]) -> _SectionNode:
    root = _SectionNode(heading="", level=0, breadcrumb="", content="")
    stack: List[Tuple[int, _SectionNode]] = [(0, root)]

    for level, heading, body, page_number, source_file in all_sections:
        if level == 0:
            if root.content:
                root.content += "\n\n" + body
            else:
                root.content = body
            continue

        while stack and stack[-1][0] >= level:
            stack.pop()

        parent_node = stack[-1][1] if stack else root
        breadcrumb = f"{parent_node.breadcrumb} > {heading}" if parent_node.breadcrumb else heading

        node = _SectionNode(
            heading=heading,
            level=level,
            breadcrumb=breadcrumb,
            content=body,
            parent=parent_node,
            page_number=page_number,
            source_file=source_file,
        )
        parent_node.children.append(node)
        stack.append((level, node))

    return root


def _merge_continuations(all_sections: List[Tuple]) -> List[Tuple]:
    merged = []
    for sec in all_sections:
        level, heading, body, page, src = sec
        if level == 0 and not heading and merged:
            prev_lvl, prev_hdg, prev_body, prev_page, prev_src = merged[-1]
            if prev_lvl > 0:
                merged[-1] = (prev_lvl, prev_hdg, prev_body + "\n" + body, prev_page, prev_src)
                continue
        merged.append(sec)
    return merged


def _count_leaves(node: _SectionNode) -> int:
    count = 0
    if node.content.strip():
        count += 1
    for child in node.children:
        count += _count_leaves(child)
    return count


def _resolve_parents(node: _SectionNode) -> None:
    leaf_count = _count_leaves(node)
    subtree_text = node.full_subtree_text()
    subtree_tokens = len(TOKENIZER.encode(subtree_text))
    if node.heading and (leaf_count > 1 or subtree_tokens > CHILD_MAX_TOKENS):
        node.is_parent = True
        node.uuid = str(uuid4())
    for child in node.children:
        _resolve_parents(child)


def _assign_parent_ids(node: _SectionNode, nearest_parent_id: Optional[str] = None) -> None:
    if node.is_parent:
        nearest_parent_id = node.uuid
    for child in node.children:
        _assign_parent_ids(child, nearest_parent_id)
    if node.content.strip():
        node.parent_id = nearest_parent_id


def _collect_leaves(node: _SectionNode) -> List[_SectionNode]:
    leaves = []
    if node.content.strip():
        leaves.append(node)
    for child in node.children:
        leaves.extend(_collect_leaves(child))
    return leaves


def _collect_parents(node: _SectionNode) -> List[_SectionNode]:
    parents = []
    if node.is_parent:
        parents.append(node)
    for child in node.children:
        parents.extend(_collect_parents(child))
    return parents


# ---------------------------------------------------------------------------
# Semantic splitting for prose leaves
# ---------------------------------------------------------------------------

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


def _semantic_split_text(
    text: str,
    breadcrumb: str,
    parent_id: str,
    document_id: UUID,
    school_id: UUID,
    embedder,
    page_number: Optional[int] = None,
    source_file: Optional[str] = None,
    parent_text: Optional[str] = None,
) -> List[Document]:
    sentences = split_sentences(text)
    if len(sentences) <= 1:
        return [_make_child(text.strip(), breadcrumb, parent_id, document_id, school_id,
                            page_number, source_file, parent_text=parent_text)]

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
        children.append(_make_child(child_text, breadcrumb, parent_id, document_id, school_id,
                                    page_number, source_file, parent_text=parent_text))
        overlap = get_last_sentence(" ".join(group))

    return children


# ---------------------------------------------------------------------------
# Chunk creation helpers
# ---------------------------------------------------------------------------

def _make_child(
    text: str, breadcrumb: str, parent_id: str,
    document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
    parent_text: Optional[str] = None,
) -> Document:
    searchable = f"{breadcrumb}: {text}" if breadcrumb else text
    doc = Document(
        page_content=text,
        metadata={
            "chunk_type": "child",
            "breadcrumb": breadcrumb,
            "parent_id": parent_id,
            "parent_text": parent_text,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": searchable,
        },
    )
    doc.metadata["page_number"] = page_number
    doc.metadata["source_file"] = source_file
    return doc


def _create_single(
    text: str, breadcrumb: str, parent_id: Optional[str],
    document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
    parent_text: Optional[str] = None,
) -> Document:
    searchable = f"{breadcrumb}: {text}" if breadcrumb else text
    doc = Document(
        page_content=text,
        metadata={
            "chunk_type": "single",
            "breadcrumb": breadcrumb,
            "parent_id": parent_id,
            "parent_text": parent_text,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": searchable,
        },
    )
    doc.metadata["page_number"] = page_number
    doc.metadata["source_file"] = source_file
    return doc


def _get_parent_text(node: _SectionNode) -> Optional[str]:
    if node.is_parent:
        return node.full_subtree_text()
    p = node.parent
    while p:
        if p.is_parent:
            return p.full_subtree_text()
        p = p.parent
    return None


def _create_parent_chunk(
    node: _SectionNode,
    document_id: UUID,
    school_id: UUID,
) -> Document:
    # Sub-parents link to their grandparent via parent_id for future use
    # (e.g., escalating to broader context). Currently unused in retrieval —
    # only the nearest (>1 leaf) parent is fetched per child chunk.
    text = node.full_subtree_text()
    # Store the node's UUID so retrieval can look up parent text by parent_id
    parent_uuid = node.uuid if node.is_parent else None
    doc = Document(
        page_content=text,
        metadata={
            "chunk_type": "parent",
            "breadcrumb": node.breadcrumb,
            "parent_id": node.parent.uuid if node.parent and node.parent.is_parent else None,
            "uuid": parent_uuid,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": None,
        },
    )
    doc.metadata["page_number"] = node.page_number
    doc.metadata["source_file"] = node.source_file
    return doc


def _create_table_chunk(
    text: str, breadcrumb: str, parent_id: Optional[str],
    document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
    parent_text: Optional[str] = None,
) -> Document:
    searchable = _table_to_sentence(text)
    doc = Document(
        page_content=text,
        metadata={
            "chunk_type": "table",
            "breadcrumb": breadcrumb,
            "parent_id": parent_id,
            "parent_text": parent_text,
            "document_id": str(document_id),
            "school_id": str(school_id),
            "searchable_text": searchable,
        },
    )
    doc.metadata["page_number"] = page_number
    doc.metadata["source_file"] = source_file
    return doc


def _create_faq_chunks(
    text: str, breadcrumb: str, parent_id: Optional[str],
    document_id: UUID, school_id: UUID,
    page_number: Optional[int] = None, source_file: Optional[str] = None,
    parent_text: Optional[str] = None,
) -> List[Document]:
    q_matches = list(FAQ_Q_PATTERN.finditer(text))
    a_matches = list(FAQ_A_PATTERN.finditer(text))

    if not q_matches:
        doc = Document(
            page_content=text,
            metadata={
                "chunk_type": "faq",
                "breadcrumb": breadcrumb,
                "parent_id": parent_id,
                "parent_text": parent_text,
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
                "parent_id": parent_id,
                "parent_text": parent_text,
                "document_id": str(document_id),
                "school_id": str(school_id),
                "searchable_text": searchable,
            },
        )
        doc.metadata["page_number"] = page_number
        doc.metadata["source_file"] = source_file
        chunks.append(doc)
    return chunks


# ---------------------------------------------------------------------------
# Leaf chunking
# ---------------------------------------------------------------------------

def _chunk_leaf(
    node: _SectionNode,
    document_id: UUID,
    school_id: UUID,
    embedder=None,
) -> List[Document]:
    if not node.content.strip():
        return []

    content = node.text()
    breadcrumb = node.breadcrumb
    parent_id = node.parent_id
    page_number = node.page_number
    source_file = node.source_file
    parent_text = _get_parent_text(node)

    if _is_table(content):
        return [_create_table_chunk(content, breadcrumb, parent_id, document_id, school_id,
                                    page_number, source_file, parent_text=parent_text)]

    if _is_faq(content):
        return _create_faq_chunks(content, breadcrumb, parent_id, document_id, school_id,
                                  page_number, source_file, parent_text=parent_text)

    tokens = TOKENIZER.encode(content)
    token_count = len(tokens)

    if token_count <= CHILD_MAX_TOKENS:
        return [_create_single(content, breadcrumb, parent_id, document_id, school_id,
                               page_number, source_file, parent_text=parent_text)]

    if embedder is None:
        embedder = _get_semantic_embedder()
    children = _semantic_split_text(content, breadcrumb, parent_id, document_id, school_id,
                                    embedder, page_number, source_file, parent_text=parent_text)

    node.leaf_type = "prose"
    node.leaf_tokens = token_count
    return children


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

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
        breadcrumb = chunk.metadata.get("breadcrumb", "")

        # Preamble-drop rule: if this is a root-level orphan with no breadcrumb,
        # drop it rather than merging into a neighbouring section.
        if is_fragment and not breadcrumb:
            logger.info("Dropping preamble fragment (%d tokens): %.80s", len(tokens), text)
            dropped += 1
            i += 1
            continue

        if is_fragment and i + 1 < len(chunks):
            next_is_table = chunks[i + 1].metadata.get("chunk_type") == "table"
            if not next_is_table:
                chunks[i + 1].page_content = text + "\n\n" + chunks[i + 1].page_content
                logger.info("Merged fragment forward (%d tokens): %.80s -> chunk %d",
                            len(tokens), text, i + 1)
                merged_forward += 1
                i += 1
                continue
            else:
                if filtered:
                    filtered[-1].page_content += "\n" + text
                    logger.info("Merged fragment backward (next is table, %d tokens): %.80s",
                                len(tokens), text)
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

    # --- Merge small consecutive single chunks ---
    if filtered:
        merged = []
        buffer = None
        for chunk in filtered:
            ctype = chunk.metadata.get("chunk_type", "")
            if ctype != "single":
                if buffer:
                    merged.append(buffer)
                    buffer = None
                merged.append(chunk)
                continue
            tokens = len(TOKENIZER.encode(chunk.page_content))
            if buffer is None or tokens >= CHILD_MIN_TOKENS:
                if buffer:
                    merged.append(buffer)
                buffer = chunk
            else:
                buffer.page_content += "\n\n" + chunk.page_content
        if buffer:
            merged.append(buffer)
        filtered = merged
    # --- End merge ---

    for j, doc in enumerate(filtered):
        doc.metadata["chunk_order"] = j

    if dropped or merged_forward or merged_backward:
        logger.info(
            "Post-process: %d dropped, %d merged forward, %d merged backward (final %d chunks)",
            dropped, merged_forward, merged_backward, len(filtered),
        )

    return filtered


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def chunk_documents(
    blocks: List[Dict[str, Any]],
    document_id: UUID,
    school_id: UUID,
    extra_boilerplate: Optional[List[re.Pattern]] = None,
    document_version: Optional[str] = None,
    effective_date: Optional[str] = None,
) -> List[Document]:
    all_sections: List[Tuple] = []
    heading_stack: List[str] = []
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
            elif level > 1:
                effective_level = level
            else:
                effective_level = level

            while len(heading_stack) >= effective_level and effective_level > 0:
                heading_stack.pop()
            if heading:
                heading_stack.append(heading)

            all_sections.append((level, heading, body, page_number, source_file))

    all_sections = _merge_continuations(all_sections)

    root = _build_heading_tree(all_sections)

    _resolve_parents(root)
    _assign_parent_ids(root)

    leaves = _collect_leaves(root)
    parent_nodes = _collect_parents(root)

    large_prose_leaves = sum(
        1 for lf in leaves
        if not _is_table(lf.text()) and not _is_faq(lf.text())
        and len(TOKENIZER.encode(lf.text())) > CHILD_MAX_TOKENS
    )

    embedder = _get_semantic_embedder() if large_prose_leaves > 0 else None

    all_chunks: List[Document] = []

    for node in parent_nodes:
        chunk = _create_parent_chunk(node, document_id, school_id)
        all_chunks.append(chunk)

    for leaf in leaves:
        chunks = _chunk_leaf(leaf, document_id, school_id, embedder=embedder)
        all_chunks.extend(chunks)

    for chunk in all_chunks:
        meta = chunk.metadata
        if document_version is not None:
            meta["document_version"] = document_version
        if effective_date is not None:
            meta["effective_date"] = effective_date

    all_chunks = post_process_chunks(all_chunks, auto_boilerplate_patterns=extra_boilerplate)

    return all_chunks
