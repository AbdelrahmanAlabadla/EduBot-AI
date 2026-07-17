import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from llama_parse import LlamaParse
from app.core.config import settings

PDF_PATH = Path(__file__).resolve().parents[1] / "test_document" / "undergraduate.pdf"
OUTPUT_DIR = Path(__file__).resolve().parent / "parser_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Parsing: {PDF_PATH}")
print(f"Output:  {OUTPUT_DIR}")
print(f"Model:   {settings.LLM_MODEL}")
print()

loader = LlamaParse(
    api_key=settings.LLAMA_PARSE_API,
    result_type="markdown",
    verbose=True,
    language="en",
    max_timeout=600,
)

docs = loader.load_langchain_documents(file_path=str(PDF_PATH))
print(f"\nParsed {len(docs)} pages")

# Dump full raw text
all_text = "\n\n========== PAGE BREAK ==========\n\n".join(
    f"--- Page {i+1} ---\n{doc.page_content}" for i, doc in enumerate(docs)
)
full_path = OUTPUT_DIR / "full_raw_output.md"
full_path.write_text(all_text, encoding="utf-8")
print(f"Full output saved: {full_path.name} ({len(all_text)} chars)")

# Dump each page
pages_dir = OUTPUT_DIR / "pages"
pages_dir.mkdir(exist_ok=True)
for i, doc in enumerate(docs):
    page_path = pages_dir / f"page_{i+1:03d}.md"
    page_path.write_text(doc.page_content, encoding="utf-8")
print(f"Individual pages saved to: {pages_dir}/ ({len(docs)} files)")

# Dump blocks as produced by parse_documents
from app.pipeline.offline_phase.parser import parse_documents

blocks = parse_documents(docs)
blocks_path = OUTPUT_DIR / "blocks_output.txt"
with open(blocks_path, "w", encoding="utf-8") as f:
    for i, block in enumerate(blocks):
        f.write(f"========== BLOCK {i} ==========\n")
        f.write(f"type: {block['type']}\n")
        f.write(f"source_metadata: {block['source_metadata']}\n")
        f.write(f"content length: {len(block['content'])} chars\n")
        f.write(block['content'][:3000])
        f.write("\n\n")
print(f"Blocks output saved: {blocks_path.name} ({len(blocks)} blocks)")

# Count some stats
total_chars = sum(len(doc.page_content) for doc in docs)
print(f"\nStats:")
print(f"  Pages:         {len(docs)}")
print(f"  Total chars:   {total_chars}")
print(f"  Avg/page:      {total_chars // len(docs)}")
