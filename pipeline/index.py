"""
Stage 3 — embed chunks and upsert them to Pinecone.

Builds into a dated index (migri-guide-YYYYMMDD) rather than overwriting the
live one, so production keeps answering from the previous corpus until the new
index is verified and deliberately switched over. Rollback is then just pointing
PINECONE_INDEX_NAME back at the old name.

    python -m pipeline.index                 # build a new dated index
    python -m pipeline.index --into NAME     # build into a specific index name

Cost: roughly $0.03 per 2,500 chunks with text-embedding-3-small.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CHUNKS_IN   = BASE_DIR / "data" / "chunks.json"
EMBED_MODEL = "text-embedding-3-small"
DIMENSION   = 1536
EMBED_BATCH = 100
UPSERT_BATCH = 100


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch, retrying on transient API failures."""
    for attempt in range(5):
        try:
            resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as exc:
            wait = 2 ** attempt
            log.warning("embedding failed (%s) — retrying in %ds", exc, wait)
            time.sleep(wait)
    raise RuntimeError("embedding failed after 5 attempts")


def ensure_index(pc: Pinecone, name: str) -> None:
    if name in [i.name for i in pc.list_indexes()]:
        index = pc.Index(name)
        existing = index.describe_index_stats().total_vector_count
        if existing:
            # Vector ids are positional, so re-running against a populated index
            # overwrites the first N and silently strands the rest. If a rebuild
            # ever yields fewer chunks than the last one, those orphans stay
            # searchable forever — dropped pages would keep answering questions.
            log.info("index '%s' holds %d vectors — clearing before rebuild",
                     name, existing)
            index.delete(delete_all=True)
            time.sleep(5)   # let the deletion propagate before upserting
        else:
            log.info("index '%s' already exists and is empty", name)
        return

    log.info("creating serverless index '%s' (%dd, cosine)", name, DIMENSION)
    pc.create_index(
        name=name,
        dimension=DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    for _ in range(60):
        if pc.describe_index(name).status.get("ready"):
            break
        time.sleep(2)
    log.info("index ready")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--into",
        default=f"migri-guide-{date.today():%Y%m%d}",
        help="target index name (default: migri-guide-YYYYMMDD)",
    )
    args = parser.parse_args()

    if not (openai_key := os.getenv("OPENAI_API_KEY")):
        raise SystemExit("OPENAI_API_KEY not set")
    if not (pinecone_key := os.getenv("PINECONE_API_KEY")):
        raise SystemExit("PINECONE_API_KEY not set")
    if not CHUNKS_IN.exists():
        raise SystemExit(f"{CHUNKS_IN} not found — run pipeline.process first")

    chunks = json.loads(CHUNKS_IN.read_text(encoding="utf-8"))
    log.info("=== Stage 3: index ===")
    log.info("%d chunks → index '%s'", len(chunks), args.into)

    client = OpenAI(api_key=openai_key)
    pc     = Pinecone(api_key=pinecone_key)
    ensure_index(pc, args.into)
    index = pc.Index(args.into)

    start = time.time()
    for offset in range(0, len(chunks), EMBED_BATCH):
        batch   = chunks[offset : offset + EMBED_BATCH]
        vectors = embed_batch(client, [c["text"] for c in batch])

        records = []
        for i, (chunk, vector) in enumerate(zip(batch, vectors)):
            # Pinecone metadata accepts str/int/float/bool/list-of-str only.
            meta = {
                k: v if isinstance(v, (str, int, float, bool, list)) else str(v)
                for k, v in chunk["metadata"].items()
            }
            meta["text"] = chunk["text"]       # stored so retrieval can rebuild the document
            records.append({"id": f"{offset + i:06d}", "values": vector, "metadata": meta})

        for up in range(0, len(records), UPSERT_BATCH):
            index.upsert(vectors=records[up : up + UPSERT_BATCH])

        done = min(offset + EMBED_BATCH, len(chunks))
        log.info("  %d / %d", done, len(chunks))

    time.sleep(5)   # let Pinecone's count catch up before reporting it
    log.info("=== Stage 3 complete in %.1f min ===", (time.time() - start) / 60)
    log.info("index '%s' now holds %d vectors",
             args.into, index.describe_index_stats().total_vector_count)
    log.info("")
    log.info("To put this corpus live:")
    log.info("  1. python -m eval.run --index %s", args.into)
    log.info("  2. printf '%s' | gcloud secrets versions add pinecone-index --data-file=-", args.into)
    log.info("  3. gcloud run services update migriguide-api --region=europe-north1")


if __name__ == "__main__":
    main()
