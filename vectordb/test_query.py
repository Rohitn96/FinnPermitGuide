"""
MigriGuide - Stage 3: Test Query
Loads the existing ChromaDB (does NOT rebuild it) and runs a test retrieval.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
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

# ── Config ─────────────────────────────────────────────────────────────────────
CHROMA_DIR      = str(BASE_DIR / "data" / "chroma_db")
COLLECTION_NAME = "migri_guide"
EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K           = 5

TEST_QUERY = "What documents do I need to extend my work permit?"


def load_vectordb() -> Chroma:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set. Check your .env file.")

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=api_key,
    )

    db = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
    )

    total = db._collection.count()
    if total == 0:
        raise RuntimeError(
            "ChromaDB collection is empty. Run vectordb/build_db.py first."
        )

    log.info("Loaded ChromaDB — %d vectors in collection '%s'", total, COLLECTION_NAME)
    return db


def run_test_query(db: Chroma):
    print("\n" + "=" * 70)
    print(f"TEST QUERY: {TEST_QUERY}")
    print("=" * 70)

    results = db.similarity_search(TEST_QUERY, k=TOP_K)

    for rank, doc in enumerate(results, start=1):
        meta = doc.metadata
        print(f"\n[Result {rank}]")
        print(f"  Source   : {meta.get('source', 'N/A')}")
        print(f"  Title    : {meta.get('title', 'N/A')}")
        print(f"  Type     : {meta.get('type', 'N/A')}")
        print(f"  Category : {meta.get('permit_category', 'N/A')}")
        print(f"  Chunk ID : {meta.get('chunk_id', 'N/A')}")
        if "scraped_date" in meta:
            print(f"  Scraped  : {meta['scraped_date']}")
        print(f"\n  Text snippet:\n  {doc.page_content[:400]}")
        print("-" * 70)


def main():
    log.info("=== Stage 3: Test Query ===")
    db = load_vectordb()
    run_test_query(db)
    log.info("=== Test complete ===")


if __name__ == "__main__":
    main()
