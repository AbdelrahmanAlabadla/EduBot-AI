import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.pipeline.offline_phase.ingestion import ingest_file
from app.pipeline.offline_phase.parser import parse_documents
from app.pipeline.offline_phase.boilerplate import detect_boilerplate
from app.pipeline.offline_phase.clean_norm import clean_and_normalize, STRUCTURAL_PATTERNS
from app.pipeline.offline_phase.chunking import chunk_documents


def process_file(pdf_path: Path, out):
    doc_id = uuid4()
    school_id = uuid4()

    raw_docs = ingest_file(str(pdf_path))
    blocks = parse_documents(raw_docs)

    for block in blocks:
        text = block["content"]
        for pattern in STRUCTURAL_PATTERNS:
            text = pattern.sub("", text)
        block["content"] = text

    boilerplate_patterns = detect_boilerplate(blocks)
    cleaned = clean_and_normalize(blocks, extra_patterns=boilerplate_patterns)
    chunks = chunk_documents(cleaned, doc_id, school_id, extra_boilerplate=boilerplate_patterns)

    out.write("=" * 80 + "\n")
    out.write(f"FILE: {pdf_path.name}\n")
    out.write(f"PAGES: {len(blocks)}  |  CHUNKS: {len(chunks)}\n")
    out.write("=" * 80 + "\n")

    for i, chunk in enumerate(chunks):
        out.write(f"\n--- Chunk {i} ---\n")
        out.write("Content:\n")
        out.write(chunk.page_content + "\n")
        out.write("Metadata:\n")
        out.write(json.dumps(chunk.metadata, default=str, indent=2) + "\n")


def main():
    test_dir = Path(__file__).resolve().parent / "test_document"
    pdfs = sorted(test_dir.glob("*.pdf"))

    if not pdfs:
        print(f"No PDF files found in {test_dir}")
        sys.exit(1)

    output_path = Path(__file__).resolve().parent / "testoutput.txt"
    with open(output_path, "w", encoding="utf-8") as out:
        for pdf_path in pdfs:
            try:
                process_file(pdf_path, out)
            except Exception as e:
                import traceback
                out.write(f"\nERROR processing {pdf_path.name}: {e}\n")
                traceback.print_exc(file=out)
            out.write("\n")

    print(f"Done. Output saved to {output_path}")


if __name__ == "__main__":
    main()
