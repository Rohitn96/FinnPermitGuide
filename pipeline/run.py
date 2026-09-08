"""
Run the whole knowledge-base rebuild: collect → process → index.

    python -m pipeline.run                  # full rebuild into a dated index
    python -m pipeline.run --skip-scrape    # reprocess and reindex what is on disk
    python -m pipeline.run --into NAME      # build into a named index

Takes roughly 15 minutes end to end, most of it crawling. The new corpus goes
into its own index; production keeps serving the previous one until you point
it at the new one, so a bad rebuild is never a live outage.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def stage(label: str, module: str, *args: str) -> None:
    log.info("%s", "=" * 64)
    log.info("%s", label)
    log.info("%s", "=" * 64)

    result = subprocess.run([sys.executable, "-m", module, *args], cwd=BASE_DIR)
    if result.returncode != 0:
        raise SystemExit(f"{module} failed with exit code {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--into", default=f"migri-guide-{date.today():%Y%m%d}",
                        help="target Pinecone index (default: migri-guide-YYYYMMDD)")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="reuse the pages already in data/raw")
    args = parser.parse_args()

    started = time.time()

    if args.skip_scrape:
        log.info("skipping the crawl — reusing data/raw")
    else:
        stage("Stage 1 of 3 — collect pages", "pipeline.scrape")

    stage("Stage 2 of 3 — process and chunk", "pipeline.process")
    stage("Stage 3 of 3 — embed and index",   "pipeline.index", "--into", args.into)

    log.info("%s", "=" * 64)
    log.info("rebuild complete in %.1f minutes", (time.time() - started) / 60)
    log.info("index: %s", args.into)
    log.info("")
    log.info("Verify, then switch production over:")
    log.info("  python -m eval.run --index %s", args.into)
    log.info("  See README.md § Deploying")
    log.info("%s", "=" * 64)


if __name__ == "__main__":
    main()
