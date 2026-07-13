#!/usr/bin/env python
"""Interactive chatbot. Reads chunks from testoutput.txt, embeds once, then chats."""

import json, os, pickle, re, sys, time, warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore", message=".*XLMRobertaTokenizerFast.*")
warnings.filterwarnings("ignore", message=".*tokenizer.*faster.*")
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, PointStruct, SparseIndexParams, SparseVectorParams,
    VectorParams,
)
from app.pipeline.offline_phase.embedding import embed_chunks
from app.core.config import settings
from app.pipeline.online_phase.rrf import rrf_search
from app.pipeline.online_phase.reranker import rerank_and_filter, initial_judge
from app.pipeline.online_phase.query_rewrite import rewrite_query
from app.pipeline.online_phase.context_builder import build_context
from app.pipeline.online_phase.generator import generate_answer
from app.pipeline.online_phase.validator import validate_and_repair

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "testoutput.txt"
CACHE_FILE = ROOT / ".embed_cache.pkl"
SCHOOL_ID = uuid4()
COLLECTION = f"school_{SCHOOL_ID}"


def load_chunks() -> list[Document]:
    text = CHUNKS_FILE.read_text(encoding="utf-8")
    raw = re.split(r"\n--- Chunk (\d+) ---\n", text)
    docs = []
    for i in range(1, len(raw), 2):
        block = raw[i + 1]
        cm = re.search(r"Content:\n(.*?)\nMetadata:\n", block, re.DOTALL)
        mm = re.search(r"Metadata:\n(\{.*\})", block, re.DOTALL)
        if not cm or not mm:
            continue
        meta = json.loads(mm.group(1))
        doc = Document(page_content=cm.group(1).strip(), metadata=meta)
        doc.metadata["document_id"] = meta.get("document_id") or str(uuid4())
        doc.metadata["school_id"] = str(SCHOOL_ID)
        docs.append(doc)
    return docs


def build_index():
    if CACHE_FILE.exists():
        print("Loading cached embeddings...", flush=True)
        points = pickle.loads(CACHE_FILE.read_bytes())
    else:
        docs = load_chunks()
        print(f"Embedding {len(docs)} chunks (first time only, ~5min on CPU)...", flush=True)
        print("  Subsequent launches will be instant (cache).\n", flush=True)
        t0 = time.time()
        embedded = embed_chunks(docs, batch_size=64)
        print(f"\n  Done in {time.time()-t0:.0f}s", flush=True)
        points = []
        for c in embedded:
            dense = c.metadata.get("embedding")
            if dense is None:
                continue
            sparse = c.metadata.get("sparse_vector")
            payload = {k: v for k, v in c.metadata.items() if k not in ("embedding","sparse_vector")}
            payload["page_content"] = c.page_content
            vectors = {"": dense}
            if sparse:
                vectors["sparse"] = sparse
            points.append(PointStruct(id=str(uuid4()), vector=vectors, payload=payload))
        CACHE_FILE.write_bytes(pickle.dumps(points))

    client = QdrantClient(location=":memory:")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={"": VectorParams(size=1024, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
    )
    client.upsert(collection_name=COLLECTION, points=points)
    print(f"  Indexed {len(points)} chunks\n", flush=True)
    return client


def answer(client, q: str, history: list) -> dict:
    rw = rewrite_query(q, history[-4:])
    rewritten, lang = rw["rewritten_query"], rw["detected_language"]
    raw = rrf_search(client, COLLECTION, rewritten)
    print(f"\n  [debug] Retrieved {len(raw)} chunks, top RRF score={raw[0]['score']:.4f}" if raw else f"\n  [debug] No chunks retrieved", flush=True)
    if not initial_judge(raw, rewritten):
        uni = settings.UNIVERSITY_NAME or "the university"
        contact = settings.CONTACT_EMAIL or "the university admissions office"
        fallback = (
            f"I'm sorry, I couldn't find enough information to answer your question. "
            f"Please contact {contact} at {uni} for assistance."
        )
        return {"answer": fallback, "lang": lang, "sources": [], "recommended": []}
    for c in raw:
        payload = c.get("payload", {})
        st = payload.get("searchable_text")
        c["full_context"] = st if st else payload.get("page_content", "")
        c["breadcrumb"] = payload.get("breadcrumb", "")
    final = rerank_and_filter(raw, rewritten)
    print(f"  [debug] After rerank: {len(final)} chunks kept", flush=True)
    if final:
        score_pct = final[0].get("rerank_score", 0) * 100
        print(f"  [debug] Top chunk: \"{final[0].get('breadcrumb', 'N/A')}\"  (relevance: {score_pct:.0f}%)", flush=True)
    context, ids = build_context(final)
    answer_text = generate_answer(rewritten, context, detected_language=lang)
    answer_text, _ = validate_and_repair(answer_text, ids, final, rewritten, context, lang)

    recommended = []
    marker = "**Recommended questions:**"
    if marker in answer_text:
        parts = answer_text.split(marker)
        answer_text = parts[0].strip()
        rec_section = parts[1].strip()
        for line in rec_section.split("\n"):
            line = line.strip().lstrip("- ")
            if line:
                recommended.append(line)

    sources = [{"doc_id": f"doc_{i+1}", "breadcrumb": c["breadcrumb"],
                "page": c["payload"].get("page_number",""),
                "rerank_score_pct": round(c.get("rerank_score", 0) * 100, 1),
                "url": c["payload"].get("url","")} for i, c in enumerate(final[:3])]
    return {"answer": answer_text, "lang": lang, "sources": sources, "recommended": recommended}


def main():
    client = build_index()

    print("Chatbot ready! Type 'quit' to exit.\n", flush=True)

    history = []
    while True:
        q = input("You: ").strip()
        if not q:
            continue
        if q.lower() in ("quit", "exit"):
            break
        t0 = time.time()
        result = answer(client, q, history)
        print(f"\nBot [{result['lang']}]: {result['answer']}", flush=True)
        recs = result.get("recommended", [])
        if recs:
            print("\n  Recommended questions:", flush=True)
            for r in recs[:3]:
                print(f"    - {r}", flush=True)
        if result.get("sources"):
            print("  Sources:", json.dumps(result["sources"], indent=2), flush=True)
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": result["answer"]})
        print(f"  ({time.time()-t0:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
