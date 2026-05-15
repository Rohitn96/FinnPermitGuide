"""
MigriGuide — Migrate to Pinecone
==================================
Uses the Pinecone SDK directly (langchain-pinecone has a simsimd dep conflict on Py3.14).

Pre-requisites:
  pip install pinecone   (already done)
  PINECONE_API_KEY in .env   — get a free key at https://app.pinecone.io/
  PINECONE_INDEX_NAME in .env  (defaults to "migri-guide")

Run AFTER patch_and_rebuild.py:
    .venv\\Scripts\\python.exe scripts/migrate_pinecone.py

Cost: ~$0.03 USD to embed ~2000-2500 chunks (text-embedding-3-small)

After migration, set USE_PINECONE=true in .env and restart the API.
"""

import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CHUNKS_JSON  = BASE_DIR / "data" / "cleaned" / "all_chunks.json"
INDEX_NAME   = os.getenv("PINECONE_INDEX_NAME", "migri-guide")
EMBED_MODEL  = "text-embedding-3-small"
DIMENSION    = 1536
BATCH_SIZE   = 100       # Pinecone upsert batch size
EMBED_BATCH  = 50        # OpenAI embedding batch size (stay under rate limits)


def load_chunks() -> list[dict]:
    if not CHUNKS_JSON.exists():
        raise FileNotFoundError(f"{CHUNKS_JSON} not found — run patch_and_rebuild.py first")
    with open(CHUNKS_JSON, encoding="utf-8") as f:
        chunks = json.load(f)
    log.info("Loaded %d chunks from %s", len(chunks), CHUNKS_JSON)
    return chunks


def ensure_index(pc) -> None:
    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME in existing:
        log.info("Index '%s' already exists", INDEX_NAME)
        return
    log.info("Creating serverless index '%s' (cosine / 1536d, aws us-east-1) ...", INDEX_NAME)
    from pinecone import ServerlessSpec
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    # Wait for index to be ready
    for _ in range(30):
        desc = pc.describe_index(INDEX_NAME)
        if desc.status.get("ready", False):
            break
        time.sleep(2)
    log.info("Index ready.")


def upsert_chunks(pc, chunks: list[dict], embeddings: OpenAIEmbeddings) -> None:
    index = pc.Index(INDEX_NAME)
    total = len(chunks)
    log.info("Embedding and upserting %d chunks in batches ...", total)

    for embed_start in range(0, total, EMBED_BATCH):
        embed_batch = chunks[embed_start : embed_start + EMBED_BATCH]
        texts = [c["text"] for c in embed_batch]

        # Embed
        vectors = embeddings.embed_documents(texts)

        # Build Pinecone records — store full text + metadata so retrieval can reconstruct Documents
        records = []
        for i, (chunk, vec) in enumerate(zip(embed_batch, vectors)):
            chunk_id = f"{embed_start + i:06d}"
            meta = {**chunk["metadata"], "text": chunk["text"]}
            # Pinecone metadata values must be str/int/float/bool/list-of-str
            meta = {k: (str(v) if not isinstance(v, (str, int, float, bool, list)) else v)
                    for k, v in meta.items()}
            records.append({"id": chunk_id, "values": vec, "metadata": meta})

        # Upsert in sub-batches
        for up_start in range(0, len(records), BATCH_SIZE):
            batch = records[up_start : up_start + BATCH_SIZE]
            index.upsert(vectors=batch)

        done = min(embed_start + EMBED_BATCH, total)
        log.info("  %d / %d chunks upserted ...", done, total)

    stats = index.describe_index_stats()
    log.info("Pinecone index stats: %s", stats)


def main():
    api_key    = os.getenv("PINECONE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "PINECONE_API_KEY not set in .env\n"
            "  Get a free key at https://app.pinecone.io/\n"
            "  Then add: PINECONE_API_KEY=your_key_here"
        )
    if not openai_key:
        raise EnvironmentError("OPENAI_API_KEY not set in .env")

    from pinecone import Pinecone
    pc = Pinecone(api_key=api_key)

    log.info("=" * 60)
    log.info("MigriGuide — Migrate to Pinecone")
    log.info("Index: %s", INDEX_NAME)
    log.info("=" * 60)

    chunks = load_chunks()
    ensure_index(pc)
    embeddings = OpenAIEmbeddings(model=EMBED_MODEL, openai_api_key=openai_key)
    upsert_chunks(pc, chunks, embeddings)

    log.info("")
    log.info("Migration complete.")
    log.info("Next: add these to .env and restart the API:")
    log.info("  USE_PINECONE=true")
    log.info("  PINECONE_API_KEY=%s...", api_key[:8])
    log.info("  PINECONE_INDEX_NAME=%s", INDEX_NAME)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
