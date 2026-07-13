# Online Pipeline (RAG Query Phase)

## Overview

The online pipeline processes user questions in real-time against documents already indexed by the offline pipeline. It is an 8-stage RAG pipeline: query rewrite, embedding, hybrid Qdrant search, retrieval judge + reranker, context assembly, answer generation, response validation, and persistence.

```
query_rewrite  →  embed  →  rrf_search  →  judge+rerank  →  context_build  →  generate  →  validate  →  persist
```

## Pipeline Stages

### Step 1: Query Rewrite & Language Detection (`query_rewrite.py`)

**Input:** `current_query` + last 4 conversation turns (Q&A pairs)

Uses a lightweight LLM call (LM Studio) to:

- **Coreference Resolution**: Resolves pronouns and incomplete phrases using conversation history
  - "What about scholarships?" → "What scholarships are available for the Computer Science program?"
- **Language Detection**: Detects Arabic/English. If mixed, defaults to Arabic (UAE context).
- **No Translation**: Outputs rewritten query in its original language — BGE-M3's cross-lingual embedding space handles matching.

**Output (JSON):**
```json
{
  "rewritten_query": "What scholarships are available for the Computer Science program?",
  "detected_language": "English"
}
```

**Input Caps:**
- Max 4 conversation turns
- Per-turn truncation: 400 chars for assistant messages
- Total history budget: 2000 chars

### Step 2: Query Embedding (`retrieval.py` — via `offline_phase/embedding.py`)

Uses `BGEM3FlagModel` (BAAI/bge-m3) via the `FlagEmbedding` library to produce both vectors in a single `encode()` call:

```python
from FlagEmbedding import BGEM3FlagModel
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=False)
output = model.encode([query], return_dense=True, return_sparse=True)
dense_vec = output['dense_vecs'][0]         # 1024-dim float vector
sparse = output['lexical_weights'][0]        # token→weight dict
```

The sparse weights dict is converted to Qdrant's `SparseVector` format (`indices` + `values` arrays).

### Step 3: Hybrid Qdrant Search (`retrieval.py`)

Single Qdrant `query_points()` call with dual prefetch + RRF fusion:

```
prefetch: [
  { query: dense_vec, using: "",       limit: RAG_DENSE_LIMIT  },  # dense search
  { query: sparse_vec, using: "sparse", limit: RAG_SPARSE_LIMIT },  # sparse search
]
query: FusionQuery(fusion=Fusion.RRF)   # Reciprocal Rank Fusion
limit: RAG_DENSE_LIMIT + RAG_SPARSE_LIMIT
```

- Dense vector stored under `""` (default), sparse under `"sparse"`
- RRF merges both result sets server-side
- Parent chunks fetched from Postgres for full section context

### Step 4: Retrieval Judge & Reranker (`reranker.py`)

**Phase 4.1 — Initial Judge:**
- Checks if any chunks were retrieved
- If ALL results are completely irrelevant → halts pipeline, returns fallback response immediately

**Phase 4.2 — RRF & Reranker Fusion:**
- Cross-encoder: `BAAI/bge-reranker-v2-m3` via `FlagReranker`
- Scores each (query, passage) pair
- Applies `RAG_SCORE_THRESHOLD` filter
- Selects top `RAG_FINAL_K` (default 5) chunks

### Step 5: Context Assembly (`context_builder.py`)

- Assigns `[doc_1], [doc_2], ...` IDs to each chunk
- Builds `allowed_citation_ids` list for Tier 1 validation
- Formats context with breadcrumb, source file, relevance score
- Passes `detected_language` forward to generator

### Step 6: Answer Generation (`generator.py`)

Calls LM Studio LLM with language-aware system prompt:

```
System: "Always match the user's language. If detected_language is 'Arabic',
respond completely in fluent Arabic, even if source text is in English.
Synthesize across languages naturally. Cite sections as [doc_1], [doc_2]."
```

- Configurable model via `LLM_MODEL` (default: `google/gemma-4-e2b`)
- LM Studio endpoint: `POST /api/v1/chat`
- Temperature: 0.3, max tokens: 1024

### Step 7: Response Validation (`validator.py`)

Two-tier validation with targeted retry:

| Tier | Check | Method | Max Retries |
|---|---|---|---|
| **Tier 1 (Hard Gate)** | Citation IDs exist in `allowed_citation_ids` | Regex extraction + set comparison | 1 targeted retry |
| **Tier 2 (Lenient)** | Numbers, AED, deadlines, fees match context | Extract numeric claims, check against source text | 1 targeted retry |

**Retry mechanism:** Appends specific corrective instruction to the prompt (not full re-generation):
- Tier 1: "You cited `[doc_5]` but only `[doc_1, doc_2]` exist in context."
- Tier 2: "You stated 54,000 AED but source says 45,000 AED — recheck."

If either tier fails after 1 retry → graceful fallback (tenant-customizable message).

### Step 8: Persistence (`pipeline.py`)

- Creates or continues a `Conversation`
- Saves user `Message` + bot `Message`
- Logs `AnalyticsEvent` (`question_asked` or `failed_answer`)
- Tracks `detected_language` in event data

## API Endpoints

All endpoints require `Authorization: Bearer <jwt>` header, scoped to the user's school.

### `POST /chatbot/ask`

Primary RAG Q&A endpoint.

**Request:**
```json
{
  "question": "What scholarships are available?",
  "conversation_id": "uuid-optional",
  "visitor_id": "anonymous",
  "language": "en"
}
```

**Response:**
```json
{
  "answer": "We offer merit-based scholarships... [doc_1]",
  "sources": [
    { "doc_id": "doc_1", "breadcrumb": "Financial Aid > Scholarships", "source_file": "policy.pdf", "score": 0.92 }
  ],
  "conversation_id": "uuid",
  "detected_language": "English"
}
```

### `GET /chatbot/conversations?limit=50`

List conversations for the school, with message count.

### `GET /chatbot/conversations/{id}/messages`

Get all messages in a conversation (ordered by creation time).

### `POST /chatbot/conversations/{id}/close`

Close a conversation (sets status to `closed` + `ended_at` timestamp).

### Chatbot Settings

- `GET /chatbot/settings` — get settings (auto-creates defaults)
- `PUT /chatbot/settings` — update settings (includes `fallback_message_en`, `fallback_message_ar`)

## Configuration

| Env Var | Default | Description |
|---|---|---|
| `LLM_BASE_URL` | `http://127.0.0.1:1234/api/v1` | LM Studio API base URL |
| `LLM_MODEL` | `google/gemma-4-e2b` | Model name for generation + rewrite |
| `LLM_MAX_TOKENS` | `1024` | Max output tokens for generation |
| `RAG_DENSE_LIMIT` | `20` | Top-K for dense vector prefetch |
| `RAG_SPARSE_LIMIT` | `20` | Top-K for sparse vector prefetch |
| `RAG_FINAL_K` | `5` | Final chunks after reranker |
| `RAG_SCORE_THRESHOLD` | `0.0` | Minimum reranker score threshold |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-encoder reranker model |
| `FALLBACK_MESSAGE_EN` | *(generic)* | Global default English fallback |
| `FALLBACK_MESSAGE_AR` | *(generic)* | Global default Arabic fallback |
| `REWRITE_MAX_HISTORY_CHARS` | `2000` | Total history character budget |
| `REWRITE_MAX_TURN_CHARS` | `400` | Per-turn truncation for assistant msgs |

## Fallback Strategy

```
Priority: per-tenant > global default > hardcoded generic
```

- Per-tenant fallbacks stored in `chatbot_settings.fallback_message_en` / `fallback_message_ar`
- Global defaults in `Settings.FALLBACK_MESSAGE_EN` / `FALLBACK_MESSAGE_AR`
- Fallback respects `detected_language` — serves the matching language version

## Language Handling

| Step | Language behavior |
|---|---|
| Query Rewrite | Detect Arabic/English. Mixed → Arabic tiebreak. Output `detected_language`. |
| Embedding | Embed as-is. No translation. BGE-M3 cross-lingual space handles matching. |
| Retrieval | Search with rewritten query in original language. |
| Generation | System prompt: "Answer in {detected_language}. Synthesize regardless of source chunk language." |
| Validation | Fallback answers respect detected language. |
| Response | `detected_language` returned to frontend for `dir="rtl"` / `dir="ltr"` rendering. |

## Dependencies

```
FlagEmbedding>=1.2.0    # BGEM3FlagModel + FlagReranker (dense+sparse embed + cross-encoder)
qdrant-client>=1.12.0   # Qdrant hybrid search with prefetch + RRF
openai>=1.0.0           # (optional) Alternative LLM provider
```

All other dependencies inherited from the offline pipeline.

## File Structure

```
backend/app/pipeline/online_phase/
    __init__.py              # Re-exports run_online_pipeline
    pipeline.py              # Orchestrator (steps 1-8)
    query_rewrite.py         # Step 1: LLM rewrite + language detection
    retrieval.py             # Steps 2-3: Embed + hybrid Qdrant search + Postgres parent fetch
    reranker.py              # Step 4: Initial judge + cross-encoder rerank + filter
    rrf.py                   # Step 3b: RRF fusion search (dense + sparse)
    context_builder.py       # Step 5: Citation IDs + context formatting
    generator.py             # Step 6: Language-aware LLM generation
    validator.py             # Step 7: Tier 1 + Tier 2 validation with targeted retry
```

## Offline Pipeline Changes

The embedding model was replaced from `HuggingFaceBgeEmbeddings` (sentence-transformers, dense-only) to `BGEM3FlagModel` (FlagEmbedding, dense + sparse in one `encode()` call):

| Before | After |
|---|---|
| `HuggingFaceBgeEmbeddings('BAAI/bge-m3')` | `BGEM3FlagModel('BAAI/bge-m3')` |
| Dense only | Dense + sparse in one forward pass |
| `QdrantVectorStore.add_texts()` | Raw `client.upsert()` with `PointStruct(vectors={"": dense, "sparse": sparse})` |
| Collection: dense only | Collection: dense + sparse vector config |

## DB Migration

Migration `f6e5d4c3b2a1` adds to `chatbot_settings`:
- `fallback_message_en` (TEXT, nullable)
- `fallback_message_ar` (TEXT, nullable)

## How to Run

```powershell
cd backend
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\alembic upgrade head
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Ensure LM Studio is running with your chosen model on `http://127.0.0.1:1234`.

## Known Design Decisions

| Decision | Rationale |
|---|---|
| `FlagEmbedding` over raw `transformers` | `BGEM3FlagModel` produces dense + sparse in one call; `FlagReranker` unified under same dep |
| Qdrant hybrid with RRF, not two separate searches | Single Qdrant call, server-side fusion, no client-side merge logic |
| No translation at any step | BGE-M3 cross-lingual space handles ar/en matching; translation adds failure point |
| Tier 2 validates only numbers/fees/dates | These are high-stakes claims; descriptive text hallucination is low-harm for admissions |
| Targeted retry, not full regenerate | Appends corrective instruction to prompt instead of cold restart — narrower fix |
| 1 retry max, then fallback | Uncapped retries risk unbounded latency; 2 failures → deficiency in retrieved context |
