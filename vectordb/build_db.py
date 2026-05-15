"""
MigriGuide - Stage 3: Build Vector Database
Loads all_chunks.json, embeds each chunk with OpenAI text-embedding-3-small,
and persists the ChromaDB collection to data/chroma_db/.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# ── Env ────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
CHUNKS_IN  = BASE_DIR / "data" / "cleaned" / "all_chunks.json"
CHROMA_DIR = str(BASE_DIR / "data" / "chroma_db")

COLLECTION_NAME   = "migri_guide"
EMBEDDING_MODEL   = "text-embedding-3-small"
EMBED_BATCH_SIZE  = 100   # ChromaDB add() batch size to stay within API limits


def load_chunks() -> list[Document]:
    """Load all_chunks.json and return a list of LangChain Document objects."""
    if not CHUNKS_IN.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {CHUNKS_IN}\n"
            "Run processor/process.py first."
        )

    with open(CHUNKS_IN, encoding="utf-8") as f:
        raw = json.load(f)

    docs = [
        Document(
            page_content=chunk["text"],
            metadata=chunk["metadata"],
        )
        for chunk in raw
    ]
    log.info("Loaded %d chunks from %s", len(docs), CHUNKS_IN)
    return docs


def build_vectordb(docs: list[Document]) -> Chroma:
    """Embed all documents and persist to ChromaDB."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set. Check your .env file."
        )

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=api_key,
    )

    log.info(
        "Embedding %d documents with %s in batches of %d …",
        len(docs), EMBEDDING_MODEL, EMBED_BATCH_SIZE,
    )

    # Build in batches so large collections don't hit rate limits
    vectordb = None
    for start in range(0, len(docs), EMBED_BATCH_SIZE):
        batch = docs[start : start + EMBED_BATCH_SIZE]
        end   = min(start + EMBED_BATCH_SIZE, len(docs))
        log.info("  Batch %d–%d …", start + 1, end)

        if vectordb is None:
            vectordb = Chroma.from_documents(
                documents=batch,
                embedding=embeddings,
                collection_name=COLLECTION_NAME,
                persist_directory=CHROMA_DIR,
            )
        else:
            vectordb.add_documents(batch)

    return vectordb


def main():
    log.info("=== Stage 3: Build Vector Database ===")

    docs = load_chunks()
    vectordb = build_vectordb(docs)

    total = vectordb._collection.count()
    log.info("=== Stage 3 complete ===")
    log.info("Total vectors in ChromaDB : %d", total)
    log.info("Persisted at              : %s", CHROMA_DIR)


if __name__ == "__main__":
    main()
