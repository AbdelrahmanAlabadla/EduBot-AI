import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.pipeline.offline_phase.ingestion import ingest_file
from app.pipeline.offline_phase.parser import parse_documents
from app.pipeline.offline_phase.boilerplate import detect_boilerplate
from app.pipeline.offline_phase.clean_norm import clean_and_normalize, STRUCTURAL_PATTERNS
from app.pipeline.offline_phase.chunking import chunk_documents, SEARCHABLE_TYPES, CONTEXT_TYPES
from app.pipeline.offline_phase.structure_validator import validate_structure, StructureReport
from app.pipeline.offline_phase.fallback_chunking import fallback_chunk_documents
from app.pipeline.offline_phase.summarizer import generate_parent_summaries
from app.pipeline.offline_phase.embedding import embed_chunks
from app.pipeline.online_phase.rrf import rrf_search

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, PointStruct, SparseIndexParams, SparseVectorParams, VectorParams,
)

NEW_CHUNK_TYPES = {"list", "callout", "contact", "procedure"}
SEARCHABLE_DISPLAY_TYPES = {"table", "faq"} | NEW_CHUNK_TYPES


def process_file(pdf_path: Path, out):
    doc_id = uuid4()
    school_id = uuid4()
    print(f"\nProcessing {pdf_path.name}...")

    # --- Step 1: Ingestion ---
    print("  [1/7] Ingesting with LlamaParse (may take 1-5 min)...", flush=True)
    raw_docs = ingest_file(str(pdf_path))
    print(f"  [1/7] Done — {len(raw_docs)} pages", flush=True)

    blocks = parse_documents(raw_docs)

    # --- Step 2: Clean ---
    print("  [2/7] Stripping structural patterns...", flush=True)
    for block in blocks:
        text = block["content"]
        for pattern in STRUCTURAL_PATTERNS:
            text = pattern.sub("", text)
        block["content"] = text

    print("  [3/7] Detecting boilerplate...", flush=True)
    boilerplate_patterns = detect_boilerplate(blocks)
    print(f"  [3/7] Done — {len(boilerplate_patterns)} patterns", flush=True)

    cleaned = clean_and_normalize(blocks, extra_patterns=boilerplate_patterns)
    print(f"  Cleaned — {len(cleaned)} blocks remain", flush=True)

    # --- Step 4: Structure validation ---
    print("  [4/7] Validating document structure...", flush=True)
    report = validate_structure(cleaned)
    _print_structure_report(report, out, indent="  ")

    # --- Step 5: Routing + Chunking ---
    print("  [5/7] Chunking (loading BGE-M3 if needed, ~2-5 min first time)...", flush=True)

    STRUCTURE_THRESHOLD = 0  # log-only mode for now
    thresholding = "yes" if STRUCTURE_THRESHOLD > 0 else "NO (log-only)"

    out.write(f"\n  STRUCTURE SCORE: {report.score}/100  |  Threshold: {STRUCTURE_THRESHOLD}  |  Fallback routing: {thresholding}\n")
    out.write(f"\n  --- Routing decision ---\n")

    if STRUCTURE_THRESHOLD > 0 and report.score < STRUCTURE_THRESHOLD:
        out.write(f"  ROUTE: fallback chunking (score {report.score} < threshold {STRUCTURE_THRESHOLD})\n")
        print(f"    Structure score {report.score} < {STRUCTURE_THRESHOLD} — using fallback", flush=True)
        chunks = fallback_chunk_documents(
            cleaned, doc_id, school_id,
        )
        print(f"  [5/7] Done — {len(chunks)} chunks via fallback", flush=True)
    else:
        out.write(f"  ROUTE: hierarchical chunking (score {report.score})\n")
        print(f"    Structure score {report.score} >= {STRUCTURE_THRESHOLD} — using hierarchical", flush=True)
        chunks = chunk_documents(
            cleaned, doc_id, school_id,
            extra_boilerplate=boilerplate_patterns,
        )
        print(f"  [5/7] Done — {len(chunks)} chunks via hierarchical", flush=True)

    # Write base chunks immediately so testoutput.txt has data even if later steps fail
    _write_report(out, pdf_path, blocks, chunks, report, [], {})
    out.flush()

    if not chunks:
        print("  No chunks created — embedding and Qdrant skipped", flush=True)
        return

    # --- Step 6: Summarizer ---
    print("  [6/7] Generating parent summaries via LM Studio (3 concurrent)...", flush=True)
    parent_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "parent"]
    if parent_chunks:
        summary_chunks = generate_parent_summaries(parent_chunks, doc_id, school_id)
        chunks.extend(summary_chunks)
        # Append summary chunks to output
        base_count = len(chunks) - len(summary_chunks)
        for i, sc in enumerate(summary_chunks):
            _write_single_chunk(out, base_count + i, sc)
        out.flush()
        print(f"  [6/7] Done — {len(summary_chunks)} summaries generated", flush=True)
    else:
        print("  [6/7] No parent chunks to summarize", flush=True)

    # --- Step 7: Embedding ---
    print("  [7/7] Embedding with BGE-M3 (may take 2-5 min)...", flush=True)
    embedded = embed_chunks(chunks, batch_size=128)
    print(f"  [7/7] Done — {len(embedded)} chunks processed", flush=True)

    # --- Step 8: Qdrant (in-memory) ---
    print("  [8/8] Storing in in-memory Qdrant...", flush=True)
    to_store = [c for c in embedded if c.metadata.get("chunk_type") in SEARCHABLE_TYPES]
    qdrant_hits = {}
    if to_store:
        client = QdrantClient(location=":memory:")
        client.create_collection(
            collection_name="test_collection",
            vectors_config={"": VectorParams(size=1024, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
        )
        points = []
        for chunk in to_store:
            meta = chunk.metadata
            dense = meta.get("embedding")
            sparse = meta.get("sparse_vector")
            if dense is None:
                continue
            vectors = {"": dense}
            if sparse:
                vectors["sparse"] = sparse
            payload = {k: v for k, v in meta.items() if k not in ("embedding", "sparse_vector")}
            payload["page_content"] = chunk.page_content
            points.append(PointStruct(id=str(uuid4()), vector=vectors, payload=payload))
            qdrant_hits[id(chunk)] = True
        if points:
            client.upsert(collection_name="test_collection", points=points)
        print(f"  [8/8] Done — {len(points)} points stored in Qdrant", flush=True)

        # Sample query to verify retrieval
        print("\n  --- Sample query: \"admission requirements\" ---", flush=True)
        try:
            sample_results = rrf_search(client, "test_collection", "admission requirements")
            print(f"  Retrieved {len(sample_results)} chunks via RRF search", flush=True)
            for i, r in enumerate(sample_results[:5]):
                payload = r.get("payload", {})
                score = r.get("score", 0)
                ctype = payload.get("chunk_type", "?")
                breadcrumb = payload.get("breadcrumb", "")
                sev = payload.get("severity", "")
                sev_tag = f" severity={sev}" if sev else ""
                print(f"    #{i+1} [{ctype}]{sev_tag} score={score:.4f} breadcrumb={breadcrumb[:80]}", flush=True)
        except Exception as e:
            print(f"  Sample query failed: {e}", flush=True)
    else:
        print("  [8/8] No embeddable chunks", flush=True)

    # Append stats footer
    embeddable = [c for c in embedded if c.metadata.get("chunk_type") in SEARCHABLE_TYPES]
    embedded_count = sum(1 for c in embeddable if c.metadata.get("embedding") is not None)
    qdrant_count = len(qdrant_hits)
    out.write(f"\n  Embedded:   {embedded_count} / {len(embeddable)} chunks\n")
    out.write(f"  In Qdrant:  {qdrant_count} points\n")

    print("  Done — wrote to testoutput.txt", flush=True)


def _print_structure_report(report: StructureReport, out, indent=""):
    lines = [
        f"{indent}Structure score:  {report.score}/100",
        f"{indent}  Headings:        {report.heading_count}",
        f"{indent}  Level consistency: {report.level_consistency:.3f}",
        f"{indent}  Invalid jumps:   {report.invalid_jumps}",
        f"{indent}  Avg section size: {report.avg_section_size:.0f} chars",
        f"{indent}  Orphan text:     {report.orphan_ratio*100:.1f}%",
        f"{indent}  Coverage:        {report.coverage_ratio*100:.0f}%",
        f"{indent}  Empty sections:  {report.empty_sections}",
    ]
    for line in lines:
        print(line, flush=True)
        out.write(line + "\n")


def _write_report(out, pdf_path, blocks, chunks, report, embedded, qdrant_hits):
    # Count by type
    type_counts = {}
    for c in chunks:
        t = c.metadata.get("chunk_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    embeddable = [c for c in embedded if c.metadata.get("chunk_type") in SEARCHABLE_TYPES]
    embedded_count = sum(1 for c in embeddable if c.metadata.get("embedding") is not None)
    qdrant_count = len(qdrant_hits)

    pipeline_type = "hierarchical"
    if not any(c.metadata.get("chunk_type") == "parent" for c in chunks):
        pipeline_type = "fallback"

    out.write("=" * 90 + "\n")
    out.write(f"FILE: {pdf_path.name}\n")
    out.write(f"PAGES: {len(blocks)}  |  TOTAL CHUNKS: {len(chunks)}\n")
    out.write(f"SCORE: {report.score}/100  |  PIPELINE: {pipeline_type}\n")
    out.write("-" * 90 + "\n")

    hierarchy_types = {"parent", "child", "single"}
    classified_types = {"table", "faq", "list", "callout", "contact", "procedure"}
    for t in sorted(type_counts):
        marker = " *" if t in classified_types else ""
        marker2 = " [hierarchy]" if t in hierarchy_types else ""
        out.write(f"  {t:12s}: {type_counts[t]}{marker}{marker2}\n")
    out.write(f"\n")
    out.write(f"  Classified chunks: {sum(type_counts.get(t,0) for t in classified_types)}\n")
    out.write(f"  Hierarchy chunks:  {sum(type_counts.get(t,0) for t in hierarchy_types)}\n")
    out.write(f"\n  Embedded:   {embedded_count} / {len(embeddable)} chunks\n")
    out.write(f"  In Qdrant:  {qdrant_count} points\n")
    out.write("=" * 90 + "\n")

    for i, chunk in enumerate(chunks):
        meta = chunk.metadata
        ctype = meta.get("chunk_type", "?")
        breadcrumb = meta.get("breadcrumb", "")
        has_emb = "yes" if meta.get("embedding") else "no"
        in_q = "yes" if id(chunk) in qdrant_hits else "no"
        pid = meta.get("parent_id", "")
        dv = meta.get("document_version", "")
        ed = meta.get("effective_date", "")
        sev = meta.get("severity", "")

        out.write(f"\n--- Chunk {i} [{ctype}] ---\n")
        out.write(f"  Breadcrumb: {breadcrumb}\n")
        out.write(f"  Parent ID:  {pid}\n")
        out.write(f"  Embedded:   {has_emb}  |  In Qdrant: {in_q}\n")
        out.write(f"  Version:    {dv}  |  Effective: {ed}\n")
        if sev:
            out.write(f"  Severity:   {sev}\n")
        st = meta.get("searchable_text")
        if ctype in SEARCHABLE_DISPLAY_TYPES and st:
            out.write(f"  Searchable: {st[:150]}...\n" if len(st) > 150 else f"  Searchable: {st}\n")
        out.write("  Content:\n")
        text = chunk.page_content
        out.write(text[:2000] + ("\n  ... (truncated)" if len(text) > 2000 else "") + "\n")
        out.write("  Metadata:\n")
        meta_out = {k: v for k, v in meta.items() if k not in ("embedding", "sparse_vector")}
        out.write(json.dumps(meta_out, default=str, indent=2) + "\n")


def _write_single_chunk(out, idx, chunk):
    meta = chunk.metadata
    ctype = meta.get("chunk_type", "?")
    breadcrumb = meta.get("breadcrumb", "")
    pid = meta.get("parent_id", "")
    dv = meta.get("document_version", "")
    ed = meta.get("effective_date", "")
    sev = meta.get("severity", "")
    out.write(f"\n--- Chunk {idx} [{ctype}] ---\n")
    out.write(f"  Breadcrumb: {breadcrumb}\n")
    out.write(f"  Parent ID:  {pid}\n")
    out.write(f"  Embedded:   no  |  In Qdrant: no\n")
    out.write(f"  Version:    {dv}  |  Effective: {ed}\n")
    if sev:
        out.write(f"  Severity:   {sev}\n")
    st = meta.get("searchable_text")
    if ctype in SEARCHABLE_DISPLAY_TYPES and st:
        out.write(f"  Searchable: {st[:150]}...\n" if len(st) > 150 else f"  Searchable: {st}\n")
    out.write("  Content:\n")
    text = chunk.page_content
    out.write(text[:2000] + ("\n  ... (truncated)" if len(text) > 2000 else "") + "\n")
    out.write("  Metadata:\n")
    meta_out = {k: v for k, v in meta.items() if k not in ("embedding", "sparse_vector")}
    out.write(json.dumps(meta_out, default=str, indent=2) + "\n")


def main():
    test_dir = Path(__file__).resolve().parent / "test_document"
    pdfs = sorted(test_dir.glob("*.pdf"))

    if not pdfs:
        print(f"No PDF files found in {test_dir}")
        sys.exit(1)

    output_path = Path(__file__).resolve().parent / "testoutput.txt"
    mode = "w"
    with open(output_path, mode, encoding="utf-8") as out:
        for pdf_path in pdfs:
            try:
                process_file(pdf_path, out)
            except Exception as e:
                import traceback
                msg = f"\nERROR processing {pdf_path.name}: {e}\n"
                print(msg)
                traceback.print_exc()
                out.write(msg)
                traceback.print_exc(file=out)
            out.write("\n")

        print(f"\nDone. Output saved to {output_path}")


if __name__ == "__main__":
    main()
