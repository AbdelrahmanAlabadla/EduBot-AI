# Offline Pipeline

## Overview

The offline pipeline processes uploaded documents (PDF, DOCX, TXT, HTML) through a 6-stage pipeline: ingestion, parsing, normalization, chunking, embedding, and Qdrant storage. Uses LlamaParse + spaCy + BGE-M3 + Qdrant with LangChain Documents throughout.

## Pipeline Stages

```
ingestion  →  parser  →  clean_norm  →  chunking  →  embedding  →  qdrant
```

### 1. Ingestion (`ingestion.py`)
- Validates file exists and extension is in `ALLOWED_FILE_TYPES` (`["pdf", "docx", "txt", "html"]`)
- Calls `llama_parse.LlamaParse` with the API key from `.env`
- Returns `list[langchain.Document]` (pages with page_number + source_file metadata)

### 2. Parser (`parser.py`)
- Pure extraction wrapper — each page becomes one `"raw_markdown"` block
- No line-by-line iteration, no regex heading splitting, no block classification
- Passes LlamaParse markdown downstream completely unedited
- Returns `list[dict]` with keys: `type` ("raw_markdown"), `content`, `source_metadata`

### 3. Clean & Normalize (`clean_norm.py`)

Runs in this order:

**Step 1 — Structural artifact removal (FIRST):** Strips repeating canvas page headers that LlamaParse injects on every page (`# Policy Main Title`, `Fiscal Resources and Procurement`, `Policy Subject:...`, `UNIVERSITY OF SHARJAH`, `Approved By: Chancellor`). Page numbers are NEVER removed.

**Step 2 — Unicode cleanup:** Removes zero-width characters, normalizes line endings (`\r\n` → `\n`).

**Step 3 — Whitespace normalization:** Collapses excessive newlines, trailing whitespace, multiple spaces.

### 4. Chunking (`chunking.py`)

Receives `"raw_markdown"` blocks (whole pages). Uses `re.split` on `^(#+)\s+(.+)` across the full page text (not line-by-line) to split by headings. Heading stack persists across pages so breadcrumbs are correct even when a heading is on a previous page. Classifies each section as table, FAQ, or prose using inline pattern matching.

Three chunk sizes:

| Token count | Chunk(s) produced | Why |
|---|---|---|
| ≤250 | `single` | Too small to split |
| 251–400 | `parent` only | Parent fits within CHILD_MAX_TOKENS, so no redundant child copy |
| 401–1500 | `parent` + 1+ `child` | Parent stored in Postgres (LLM context), children embedded for search |
| >1500 | `parent` + multiple `child` | Multiple sentence-boundary splits with last-sentence overlap |

**Chunk types:**
| Type | Purpose | Stored in | Embedded for search |
|---|---|---|---|
| `single` | Short block (≤250 tokens) | Postgres + Qdrant | ✅ |
| `parent` | Full section | Postgres only | ❌ (LLM context) |
| `child` | Sub-split (250-400 tokens) | Postgres + Qdrant | ✅ |
| `table` | Atomic table, never split | Postgres + Qdrant | ✅ (via `searchable_text`) |
| `faq` | 1 Q&A pair = 1 chunk | Postgres + Qdrant | ✅ (via `searchable_text`) |

**Sentence-boundary splitting:** Uses spaCy's `xx_sent_ud_sm` sentencizer. Last sentence of each child is prepended as overlap to the next child for context continuity.

**Overlap example:**
```
Chunk A: "Tuition fees are paid by credit card. Refunds are processed within 30 days."
                                              ↑ last sentence → overlap
Chunk B: "Refunds are processed within 30 days. Late payments incur a 5% fee."
         ↑ same sentence — context bridge between chunks
```

### 5. Embedding (`embedding.py`)
- `BAAI/bge-m3` via `sentence-transformers` — multilingual (Arabic, English, French, etc.)
- Embeds `"child"` and `"single"` chunk types

### 6. Qdrant Storage (`qdrant.py`)
- One Qdrant collection per school: `school_{school_id}`
- Schema conformance check before upsert
- `"parent"` chunks stored in Postgres for LLM context

## Chunk Metadata Schema

Every chunk is a LangChain `Document` with:
```python
{
    "page_content": "Scope\n\nThis policy applies to all students...",
    "metadata": {
        "chunk_type": "single" | "parent" | "child" | "table" | "faq",
        "breadcrumb": "Undergraduate > International > Required Documents",
        "parent_id": UUID | None,
        "document_id": UUID,
        "school_id": UUID,
        "chunk_order": int,
        "page_number": int | None,
        "source_file": str | None,
        "searchable_text": str | None,
        "embedding": List[float] | None,
    }
}
```

## Dependencies

```
llama-parse==0.5.7
langchain==0.3.0
langchain-community==0.3.0
langchain-qdrant==0.2.0
qdrant-client==1.12.0
sentence-transformers==3.2.0
transformers==4.48.0
spacy>=3.8.0
xx_sent_ud_sm==3.8.0
```

## Environment Variables

| Variable | Description |
|---|---|
| `LLAMA_PARSE_API` | API key for LlamaParse |
| `QDRANT_HOST` | Qdrant host (default: localhost) |
| `QDRANT_PORT` | Qdrant port (default: 6333) |

## DB Migration

Migration `a1b2c3d4e5f6` adds to `document_chunks`:
- `chunk_type` (VARCHAR 20)
- `breadcrumb` (VARCHAR 500)
- `parent_id` (UUID, FK→document_chunks.id)
- `searchable_text` (TEXT)

## File Structure

```
backend/app/pipeline/
    __init__.py
    offline_phase/
        __init__.py
        ingestion.py       # LlamaParse → LangChain Documents
        parser.py          # Pure extraction, no splitting
        clean_norm.py      # Structural artifacts → unicode → whitespace
        chunking.py        # Macro split by headings, spaCy sentencizer, overlap
        embedding.py       # BGE-M3 embedding
        qdrant.py          # Qdrant upsert + Postgres parent storage
        pipeline.py        # Orchestrator
```

## How to Run

```powershell
cd backend
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m spacy download xx_sent_ud_sm
.venv\Scripts\alembic upgrade head
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Upload a document via `POST /documents/upload` — the background task runs the full offline pipeline automatically.

## Known Bug Fixes

| Bug | Root Cause | Fix |
|---|---|---|
| Text Truncation | Heading text consumed by regex, excluded from block content | Prepend `f"{heading}\n\n"` to block content |
| Redundancy | Parent+child created for tiny sections | `token_count ≤ CHILD_MIN_TOKENS` → `"single"` chunk |
| Identical Parent/Child | Section 250-400 tokens produced duplicate parent+child with same content | `token_count ≤ CHILD_MAX_TOKENS` → parent only, no child |
| Missing Metadata | `page_number`, `source_file` dropped during chunking | Propagate via params to all chunker functions |
| Hard Cut | Chunks split mid-paragraph, no context bridge | spaCy sentence-boundary split + last-sentence overlap |
| Duplicate Header Chunks | LlamaParse injects `# Policy Main Title` on every page as a canvas artifact | `STRUCTURAL_PATTERNS` in `clean_norm.py` strips repeating headers before chunking |
| Page Splitting Mid-Table | Line-by-line heading detection split table rows | `re.split` on full text, not line-by-line |
