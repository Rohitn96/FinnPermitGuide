"""
FinnPermit Guide — Full Database Rebuild
==========================================
Deletes all existing Pinecone vectors, re-scrapes all sources with the
improved scraper (table extraction + link discovery), re-processes and
re-chunks the content, then re-embeds and uploads to Pinecone.

Run from the project root with the venv active:
    .venv\\Scripts\\python.exe scripts/rebuild_all.py

Expected runtime: 25-45 minutes (scraping ~800-1000 pages at 1.5s/page)
Expected vectors: 3,000-5,000 (up from ~1,543)
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

PYTHON = sys.executable  # same venv interpreter that launched this script


def step_delete_pinecone() -> None:
    """Delete every vector from the Pinecone index."""
    log.info("=" * 60)
    log.info("Step 1/4 — Deleting all Pinecone vectors")
    log.info("=" * 60)

    api_key    = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "migri-guide")

    if not api_key:
        raise EnvironmentError("PINECONE_API_KEY not set in .env")

    from pinecone import Pinecone
    pc    = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    stats = index.describe_index_stats()
    total = stats.total_vector_count
    log.info("Current vector count: %d", total)

    if total > 0:
        log.info("Deleting all vectors …")
        index.delete(delete_all=True)
        time.sleep(5)  # let Pinecone propagate the deletion
        stats = index.describe_index_stats()
        log.info("After deletion: %d vectors remaining", stats.total_vector_count)
    else:
        log.info("Index already empty — nothing to delete")


def step_run(label: str, script_rel_path: str) -> None:
    """Run a pipeline script as a subprocess and raise on failure."""
    log.info("=" * 60)
    log.info("%s", label)
    log.info("=" * 60)
    script_abs = str(BASE_DIR / script_rel_path)
    result = subprocess.run(
        [PYTHON, script_abs],
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Pipeline step failed (exit code {result.returncode}): {script_rel_path}"
        )


def main() -> None:
    log.info("=" * 60)
    log.info("FinnPermit Guide — Full Database Rebuild")
    log.info("Python: %s", PYTHON)
    log.info("=" * 60)

    start = time.time()

    step_delete_pinecone()
    step_run("Step 2/4 — Scraping all sources",          "scraper/scrape.py")
    step_run("Step 3/4 — Processing and chunking",       "processor/process.py")
    step_run("Step 4/4 — Embedding and uploading",       "scripts/migrate_pinecone.py")

    elapsed = (time.time() - start) / 60
    log.info("=" * 60)
    log.info("Full rebuild complete in %.1f minutes", elapsed)
    log.info("Next: redeploy the backend so the API uses the new vectors.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
