# Offline Pipeline

## Overview

The offline pipeline processes uploaded documents (PDF, DOCX, TXT, HTML) through a 7-stage pipeline: ingestion, parsing, normalization, chunking, summarization, embedding, and Qdrant storage. Uses LlamaParse + spaCy + BGE-M3 + Qdrant with LangChain Documents throughout.

## Pipeline Stages

```
ingestion  →  parser  →  clean_norm  →  chunking  →  summarizer  →  embedding  →  qdrant
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

### 4. Chunking (`chunking.py`) — v2 (Hierarchical + Semantic)

Receives `"raw_markdown"` blocks (whole pages). The chunker now builds a **heading hierarchy tree** dynamically (any depth), then resolves parent sections and classifies leaves by content type.

**Tree building:**
- All pages' sections are parsed via regex `^(#+)\s+(.+)` and merged into a single tree
- Heading stack persists across pages for correct breadcrumbs
- Orphan level-0 continuations (text on a new page after a heading) are merged back into the previous heading's content

**Parent resolution:**
- A heading becomes a `parent` chunk only if its subtree contains **>1 leaf** (content block)
- Leaves point to their nearest parent ancestor via `parent_id`
- Sub-parents link to their grandparent via `parent_id` for future escalation use (currently unused)

**Content-type branching (runs before any splitting):**

| Content type | Behavior |
|---|---|
| **Table** | Atomic — one table = one chunk, never split by rows. `searchable_text` via `_table_to_sentence()` for embedding. |
| **FAQ** | Atomic — one Q&A pair = one chunk. |

**Prose sizing:**

| Token count | Chunk(s) produced |
|---|---|
| ≤600 | `single` chunk (with `parent_id` if under a >1-leaf heading) |
| >600 | `parent` chunk + multiple `child` chunks (semantically split) |

**Semantic splitting (replaces sentence-boundary token split):**
- Embeds each sentence via **BGE-M3** (same model used for retrieval embeddings)
- Computes cosine similarity between consecutive sentence embeddings
- Break threshold: **0.70** — similarity below 0.70 marks a topic-shift boundary
- Respects `CHILD_MIN_TOKENS` (250) / `CHILD_MAX_TOKENS` (600) so breakpoints don't produce tiny or oversized chunks
- Overlap: last 2 sentences from each child are prepended to the next child
- BGE-M3 model is loaded only when needed and released after chunking

**Chunk types:**
| Type | Purpose | Stored in | Embedded for search |
|---|---|---|---|
| `single` | Short block (≤600 tokens) | Postgres + Qdrant | ✅ |
| `parent` | Full section text (for LLM context, never embedded) | Postgres only | ❌ |
| `child` | Semantic sub-split (>600 token prose sections) | Qdrant only | ✅ |
| `table` | Atomic table, never split | Qdrant only | ✅ (via `searchable_text`) |
| `faq` | 1 Q&A pair = 1 chunk | Qdrant only | ✅ (via `searchable_text`) |
| `summary` | 3-4 sentence LLM-generated summary | Qdrant only | ✅ |

**Post-processing:**
- Boilerplate detection + removal (same as v1)
- **Preamble-drop:** root-level orphan fragments (<25 tokens, no breadcrumb) are **dropped** instead of merged into neighbouring sections (prevents metadata text like "Effective Date" from polluting heading content embeddings)
- Small fragments merged forward/backward (same as v1)
- Orphan fragments dropped (same as v1)

### 4a. Summarization (`summarizer.py`)

- Runs immediately after chunking, before embedding
- For each `parent` chunk, sends the full section text to **LM Studio** (3 concurrent calls via `ThreadPoolExecutor`)
- Prompt is guided: extracts named requirements, numbers, deadlines, fees, etc. — avoids generic filler
- Returns `summary` chunk type with breadcrumb prepended to embedded text
- Summary chunks go into the same Qdrant collection as child/table/faq chunks — one merged pool, similarity sorting determines which type wins per query

### 5. Embedding (`embedding.py`)
- `BAAI/bge-m3` via `BGEM3FlagModel` — multilingual (Arabic, English, French, etc.)
- Embeds all `SEARCHABLE_TYPES` = `{"child", "single", "table", "summary"}`
- **Breadcrumb prepending:** for `child` and `summary` chunks, the breadcrumb path is prepended to the embedded text (e.g. `"Admissions Policy > Undergraduate > Eligibility Requirements: ..."`) so dense retrieval doesn't lose section context
- `table` chunks embed via `searchable_text` (natural language sentence conversion)
- `faq` chunks embed via `searchable_text` (Q/A concatenated)

### 6. Qdrant Storage (`qdrant.py`)
- One Qdrant collection per school: `school_{school_id}`
- Schema conformance check before upsert
- `"parent"` and `"single"` chunks stored in Postgres for LLM context
- All other searchable types (`child`, `table`, `faq`, `summary`) stored in Qdrant only
- `document_version` and `effective_date` included in Qdrant payload and Postgres metadata for filterable query-time use

## Chunk Metadata Schema

Every chunk is a LangChain `Document` with:
```python
{
    "page_content": "Scope\n\nThis policy applies to all students...",
    "metadata": {
        "chunk_type": "single" | "parent" | "child" | "table" | "faq" | "summary",
        "breadcrumb": "Undergraduate > International > Required Documents",
        "parent_id": UUID | None,
        "document_id": UUID,
        "school_id": UUID,
        "chunk_order": int,
        "page_number": int | None,
        "source_file": str | None,
        "searchable_text": str | None,                # table/faq only
        "document_version": str | None,               # e.g. "3.2"
        "effective_date": datetime | None,            # e.g. 2026-01-15
        "embedding": List[float] | None,               # set by embedding step
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
FlagEmbedding>=1.2.0
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

## DB Migrations

| Migration | Adds to `document_chunks` |
|---|---|
| `a1b2c3d4e5f6` | `chunk_type`, `breadcrumb`, `parent_id`, `searchable_text` |
| `f7a8b9c0d1e2` | `document_version` (VARCHAR 50), `effective_date` (DateTime with tz) |

## File Structure

```
backend/app/pipeline/
    __init__.py
    offline_phase/
        __init__.py
        ingestion.py       # LlamaParse → LangChain Documents
        parser.py          # Pure extraction, no splitting
        clean_norm.py      # Structural artifacts → unicode → whitespace
        boilerplate.py     # Auto-detect boilerplate patterns across pages
        chunking.py        # Heading tree + semantic splitting (v2)
        summarizer.py      # LM Studio summary generation for parent sections
        embedding.py       # BGE-M3 embedding with breadcrumb prepending
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
