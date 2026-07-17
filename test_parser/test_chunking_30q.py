"""
Test script: runs chunking on the undergraduate PDF, dumps all chunks,
then cross-references 30 questions against chunk content to identify
whether failures are chunking vs retrieval problems.
"""
import sys, re, json, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from uuid import uuid4
from llama_parse import LlamaParse
from app.core.config import settings
from app.pipeline.offline_phase.parser import parse_documents
from app.pipeline.offline_phase.boilerplate import detect_boilerplate
from app.pipeline.offline_phase.clean_norm import clean_and_normalize, STRUCTURAL_PATTERNS
from app.pipeline.offline_phase.chunking import chunk_documents, post_process_chunks

PDF_PATH = Path(__file__).resolve().parents[1] / "test_document" / "undergraduate.pdf"
OUTPUT_DIR = Path(__file__).resolve().parent
DUMP_DIR = OUTPUT_DIR / "chunk_dump"
DUMP_DIR.mkdir(exist_ok=True)

SCHOOL_ID = uuid4()
DOC_ID = uuid4()

print("=== Step 1: Parse PDF with LlamaParse ===")
loader = LlamaParse(
    api_key=settings.LLAMA_PARSE_API,
    result_type="markdown",
    verbose=False,
    language="en",
    max_timeout=600,
)
docs = loader.load_langchain_documents(file_path=str(PDF_PATH))
print(f"  Parsed {len(docs)} pages")

print("\n=== Step 2: Parse into blocks ===")
blocks = parse_documents(docs)
print(f"  {len(blocks)} blocks")

print("\n=== Step 3: Clean + Boilerplate ===")
for block in blocks:
    text = block["content"]
    for pattern in STRUCTURAL_PATTERNS:
        text = pattern.sub("", text)
    block["content"] = text

boilerplate_patterns = detect_boilerplate(blocks)
print(f"  Detected {len(boilerplate_patterns)} boilerplate patterns")

cleaned = clean_and_normalize(blocks, extra_patterns=boilerplate_patterns)
print(f"  {len(cleaned)} blocks after cleaning")

print("\n=== Step 4: Chunking ===")
chunks = chunk_documents(cleaned, DOC_ID, SCHOOL_ID, extra_boilerplate=boilerplate_patterns)
print(f"  Produced {len(chunks)} chunks")

# Save all chunks to a file
chunks_path = DUMP_DIR / "all_chunks.txt"
with open(chunks_path, "w", encoding="utf-8") as f:
    for i, chunk in enumerate(chunks):
        meta = chunk.metadata
        f.write(f"{'='*80}\n")
        f.write(f"CHUNK {i} | type={meta.get('chunk_type')} | order={meta.get('chunk_order')} | "
                f"breadcrumb={meta.get('breadcrumb', '')} | page={meta.get('page_number', '')} | "
                f"tokens={len(chunk.page_content.split())}\n")
        f.write(f"{'='*80}\n")
        f.write(chunk.page_content)
        f.write("\n\n")

print(f"  Saved to {chunks_path}")

# Also save by chunk type
by_type = {}
for c in chunks:
    ct = c.metadata.get("chunk_type", "unknown")
    by_type.setdefault(ct, []).append(c)
for ct, clist in by_type.items():
    print(f"  {ct}: {len(clist)} chunks")

# ========================
# 30 Questions Test
# ========================
print("\n\n" + "="*80)
print("30 QUESTIONS TEST")
print("="*80)

questions = {
    "easy": [
        "What is the total credit hours for the AI Engineering program?",
        "What is the tuition fee per credit hour for Engineering at Abu Dhabi campus?",
        "What is the admission application fee for undergraduate programs?",
        "How many colleges does Abu Dhabi University have?",
        "What is the minimum CGPA to avoid academic probation?",
        "What is the minimum credit hours per semester for full-time undergraduate students?",
        "What is the refund percentage during the first academic calendar week?",
        "What international accreditation body accredited the university?",
        "How many credit hours of General Education does AI Engineering require?",
        "What is the course code for Introductory Artificial Intelligence?",
    ],
    "normal": [
        "List all courses taught in the First Year of AI Engineering.",
        "What are the program educational objectives of the AI Engineering program?",
        "What concentrations are offered by the College of Engineering?",
        "What are the major elective courses available for AI Engineering students?",
        "What are the English language proficiency requirements for admission?",
        "How are students classified based on completed credit hours?",
        "What international accreditations does Abu Dhabi University hold?",
        "What are the open elective courses available in AI Engineering?",
        "What are the admission requirements from the British curriculum?",
        "What fees are associated with Engineering labs and student services?",
    ],
    "hard": [
        "What is the total cost for an AI Engineering student taking 15 credit hours at Abu Dhabi campus (tuition + fees)?",
        "A student with 30 credits and 1.8 CGPA can they register for 15 credits next semester?",
        "If I have a British curriculum high school diploma, am I eligible for AI Engineering?",
        "Compare Engineering tuition vs Business Administration tuition at Al Ain campus.",
        "What adds up to the 140 total credit hours in AI Engineering (all components)?",
        "What are ALL prerequisites for taking CSC 406 Artificial Intelligence?",
        "Can a College of Engineering student change their major while on academic probation?",
        "What refund would a student get withdrawing in the third week of Fall semester?",
        "Which ABET commissions accredit which programs at ADU?",
        "A student transferred 24 credit hours from another university with a 2.5 GPA do they meet the minimum requirements?",
    ],
}

def search_chunks(chunks, keywords, require_all=False):
    """Search chunks for keywords, return matching chunks."""
    results = []
    for i, chunk in enumerate(chunks):
        text = chunk.page_content.lower()
        if isinstance(keywords, str):
            keywords = [keywords]
        if require_all:
            if all(kw.lower() in text for kw in keywords):
                results.append((i, chunk))
        else:
            if any(kw.lower() in text for kw in keywords):
                results.append((i, chunk))
    return results

# Analyze each question
results_path = DUMP_DIR / "30q_results.txt"
with open(results_path, "w", encoding="utf-8") as f:
    f.write("30 QUESTIONS ANALYSIS\n")
    f.write("=====================\n")
    f.write("PASS = answer content EXISTS in at least one chunk (chunking OK, retrieval may still fail)\n")
    f.write("FAIL = answer content NOT FOUND in any chunk (chunking problem)\n\n")

    for difficulty, qs in questions.items():
        f.write(f"\n{'='*60}\n")
        f.write(f"{difficulty.upper()} ({len(qs)} questions)\n")
        f.write(f"{'='*60}\n")
        for idx, q in enumerate(qs):
            # Extract keywords from question
            words = q.lower().split()
            # Remove stopwords
            stopwords = {"what","is","the","a","an","for","of","in","to","are","do","i","if","at","by","it",
                        "their","that","they","and","or","with","on","not","does","can","would","could","than"}
            keywords = [w.strip("?,.") for w in words if w not in stopwords and len(w) > 2]

            # Pick a few key phrases for broader matching
            # Use the first meaningful keywords
            top_kw = keywords[:5] if len(keywords) > 5 else keywords

            matches = search_chunks(chunks, top_kw)
            passed = len(matches) > 0

            status = "PASS" if passed else "FAIL"
            f.write(f"\n[{status}] Q{idx+1}: {q}\n")
            f.write(f"  Keywords: {top_kw[:5]}\n")
            if matches:
                for match_idx, m in matches[:5]:
                    ct = m.metadata.get("chunk_type", "?")
                    page = m.metadata.get("page_number", "?")
                    bread = m.metadata.get("breadcrumb", "")[:60]
                    preview = m.page_content[:120].replace("\n", " ")
                    f.write(f"  -> Chunk {match_idx} (type={ct}, page={page}, breadcrumb={bread})\n")
                    f.write(f"     Preview: {preview}...\n")
            else:
                f.write(f"  -> No chunk found containing keywords\n")
            f.flush()

print(f"\nResults saved to {results_path}")

# Summary
pass_count = 0
fail_count = 0
for difficulty, qs in questions.items():
    for q in qs:
        words = q.lower().split()
        stopwords = {"what","is","the","a","an","for","of","in","to","are","do","i","if","at","by","it",
                    "their","that","they","and","or","with","on","not","does","can","would","could","than"}
        keywords = [w.strip("?,.") for w in words if w not in stopwords and len(w) > 2]
        top_kw = keywords[:5]
        matches = search_chunks(chunks, top_kw)
        if matches:
            pass_count += 1
        else:
            fail_count += 1

print(f"\n\n{'='*60}")
print(f"SUMMARY: {pass_count} PASS / {fail_count} FAIL (out of 30)")
print(f"{'='*60}")
if fail_count > 0:
    print("FAILED questions likely have chunking problems (answer not in any chunk)")
if pass_count < 30:
    print(f"PASSED questions have content in chunks — retrieval may still drop them in top-k")
