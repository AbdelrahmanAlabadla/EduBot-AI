"""
Test page expansion: ingest into Qdrant, then test retrieval expansion.
"""
import sys, logging, time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PDF_PATH = Path(__file__).resolve().parents[1] / "test_document" / "undergraduate.pdf"
SCHOOL_ID = uuid4()
DOC_ID = uuid4()

# ========== Step 1: Ingest ==========
print("=== STEP 1: Ingest document into Qdrant ===")
from app.pipeline.offline_phase.pipeline import run_offline_pipeline
from app.database.connection import engine
from sqlalchemy.orm import Session
from app.database.base import Base
Base.metadata.create_all(bind=engine)

t0 = time.time()
with Session(engine) as db:
    chunks = run_offline_pipeline(
        file_path=str(PDF_PATH),
        school_id=SCHOOL_ID,
        document_id=DOC_ID,
        db=db,
    )
t1 = time.time()
print(f"Ingested {len(chunks)} chunks in {t1-t0:.1f}s")

# ========== Step 2: Test retrieval expansion ==========
print("\n=== STEP 2: Test page expansion ===")
from app.pipeline.online_phase.retrieval import hybrid_search, expand_by_page

test_queries = [
    "List all courses taught in the First Year of AI Engineering",
    "What is the total credit hours for the AI Engineering program?",
    "What is the tuition fee per credit hour for Engineering at Abu Dhabi campus?",
    "What are the admission requirements from the British curriculum?",
]

for q in test_queries:
    print(f"\n{'='*60}")
    print(f"Query: {q}")
    print(f"{'='*60}")
    
    raw = hybrid_search(q, SCHOOL_ID)
    raw_pages = {c["payload"].get("page_number") for c in raw if c["payload"].get("page_number")}
    print(f"  Before expansion: {len(raw)} chunks from {len(raw_pages)} pages")
    print(f"  Pages: {sorted(raw_pages)[:20]}")
    
    expanded = expand_by_page(raw, SCHOOL_ID)
    exp_pages = {c["payload"].get("page_number") for c in expanded if c["payload"].get("page_number")}
    print(f"  After expansion:  {len(expanded)} chunks from {len(exp_pages)} pages")
    print(f"  Pages: {sorted(exp_pages)[:20]}")
    print(f"  New pages: {sorted(exp_pages - raw_pages)[:20]}")
    
    # Show breadcrumbs of chunks from the most represented page
    from collections import Counter
    page_counts = Counter(c["payload"].get("page_number") for c in expanded if c["payload"].get("page_number"))
    if page_counts:
        top_page = page_counts.most_common(1)[0][0]
        print(f"\n  All chunks from page {top_page}:")
        for c in expanded:
            if c["payload"].get("page_number") == top_page:
                p = c["payload"]
                preview = p.get("page_content", "")[:100].replace("\n", " ")
                print(f"    type={p.get('chunk_type','?'):8s} breadcrumb={p.get('breadcrumb','?'):50s} | {preview}")
