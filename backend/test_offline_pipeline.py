import json
import sys
from pathlib import Path
from uuid import uuid4

# Ensure we can import from app/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pipeline.offline_phase.ingestion import ingest_file
from app.pipeline.offline_phase.parser import parse_documents
from app.pipeline.offline_phase.clean_norm import clean_and_normalize
from app.pipeline.offline_phase.chunking import chunk_documents
from app.pipeline.offline_phase.embedding import embed_chunks
from app.pipeline.offline_phase.qdrant import store_in_qdrant

TEST_FILE = Path(__file__).resolve().parents[1] / "test_document" / "frp-07-fees-collection-and-refund.pdf"
OUTPUT_FILE = Path(__file__).resolve().parents[1] / "testthetesting"
SCHOOL_ID = uuid4()
DOCUMENT_ID = uuid4()


def write_output(step_name: str, data):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{'='*80}\n")
        f.write(f"STEP: {step_name}\n")
        f.write(f"{'='*80}\n")
        if isinstance(data, str):
            f.write(data)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                f.write(f"\n--- Item {i} ---\n")
                if hasattr(item, "page_content"):
                    f.write(f"Content:\n{item.page_content[:500]}\n")
                    f.write(f"Metadata: {json.dumps(item.metadata, default=str, indent=2)}\n")
                elif isinstance(item, dict):
                    content_preview = item.get("content", "")[:500]
                    f.write(f"Type: {item.get('type')}\n")
                    f.write(f"Heading: {item.get('heading')}\n")
                    f.write(f"Heading Level: {item.get('heading_level')}\n")
                    f.write(f"Content:\n{content_preview}\n")
        f.write("\n\n")


def main():
    print(f"File: {TEST_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"School ID: {SCHOOL_ID}")
    print(f"Document ID: {DOCUMENT_ID}")

    # 1. Ingestion
    print("\n[1/6] Ingestion (LlamaParse)...", end=" ")
    raw_docs = ingest_file(str(TEST_FILE))
    print(f"done — {len(raw_docs)} pages")

    # 2. Parser
    print("[2/6] Parser...", end=" ")
    blocks = parse_documents(raw_docs)
    print(f"done — {len(blocks)} blocks")
    write_output("PARSER OUTPUT", blocks)

    # 3. Clean & Normalize
    print("[3/6] Clean & Normalize...", end=" ")
    cleaned = clean_and_normalize(blocks)
    print(f"done — {len(cleaned)} blocks (removed {len(blocks) - len(cleaned)} empty)")
    write_output("CLEAN & NORMALIZE OUTPUT", cleaned)

    # 4. Chunking
    print("[4/6] Chunking...", end=" ")
    chunks = chunk_documents(cleaned, DOCUMENT_ID, SCHOOL_ID)
    print(f"done — {len(chunks)} chunks")
    write_output("CHUNKING OUTPUT", chunks)

    # 5. Embedding
    print("[5/6] Embedding (BGE-M3)...", end=" ")
    embedded = embed_chunks(chunks)
    child_count = sum(1 for c in embedded if c.metadata.get("chunk_type") == "child")
    print(f"done — {child_count} child chunks embedded")

    # 6. Qdrant
    print("[6/6] Qdrant storage...", end=" ")
    try:
        store_in_qdrant(embedded, SCHOOL_ID, db=None)
        print("done")
    except Exception as e:
        print(f"SKIPPED (Qdrant not running?): {e}")

    print(f"\nAll output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
