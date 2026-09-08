"""Runtime settings. Everything tunable lives here, read from the environment."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Models ────────────────────────────────────────────────────────────────────
ANSWER_MODEL  = os.getenv("ANSWER_MODEL",  "gpt-5.4-mini")
REWRITE_MODEL = os.getenv("REWRITE_MODEL", "gpt-5.4-mini")
EMBED_MODEL   = os.getenv("EMBED_MODEL",   "text-embedding-3-small")
RERANK_MODEL  = os.getenv("RERANK_MODEL",  "bge-reranker-v2-m3")

# ── Retrieval ─────────────────────────────────────────────────────────────────
# Fetch wide, then let the reranker decide. Embedding similarity is good at
# recall and mediocre at precision; a cross-encoder reading the query and the
# chunk together is much better at precision. Retrieving 40 and keeping the
# best 12 gets the specific threshold or grace period into the prompt without
# burying it under twelve near-duplicate overview pages.
CANDIDATES = int(os.getenv("CANDIDATES", "40"))   # pulled from Pinecone
CONTEXT_CHUNKS = int(os.getenv("CONTEXT_CHUNKS", "12"))   # kept after reranking

# Most chunks allowed from any single page.
#
# Reranking optimises relevance and is indifferent to redundancy, so a long page
# that matches well can take every slot: one question about entrepreneur permits
# AND Kela benefits filled 7 of 12 slots with consecutive chunks of Migri's
# start-up page and left no room for Kela at all, even though Kela passages were
# sitting in the candidate pool. Capping per page is what keeps a two-part
# question able to answer both parts.
MAX_PER_SOURCE = int(os.getenv("MAX_PER_SOURCE", "3"))

# Reranker scores are calibrated 0–1. Below this the corpus genuinely does not
# cover the question, and the answer is flagged low-confidence in the UI.
MIN_RELEVANCE = float(os.getenv("MIN_RELEVANCE", "0.15"))

# Conversation turns replayed to the model. Beyond a handful the older turns
# add cost and drift without improving the answer.
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "6"))

# ── Vector store ──────────────────────────────────────────────────────────────
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX   = os.getenv("PINECONE_INDEX_NAME", "migri-guide")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
