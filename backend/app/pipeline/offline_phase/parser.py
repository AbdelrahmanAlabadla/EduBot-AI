import logging
from typing import List, Dict, Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def parse_documents(docs: List[Document]) -> List[Dict[str, Any]]:
    blocks = []
    for doc in docs:
        content = doc.page_content.strip()
        if content:
            blocks.append({
                "type": "raw_markdown",
                "content": content,
                "source_metadata": doc.metadata,
            })
    return blocks
