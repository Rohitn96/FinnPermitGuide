"""
FinnPermit Guide — HTTP API.

    GET  /          health and corpus metadata
    POST /ask       answer a question from official sources
    POST /feedback  record a thumbs up/down on an answer

Requests are logged to stdout as single-line JSON. On Cloud Run that lands in
Cloud Logging, where it can be queried and charted — the only place usage
numbers for this service actually exist.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import ask, is_too_short
from rag import config as rag_config

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("finnpermit")

VERSION = "2.0.0"

app = FastAPI(
    title="FinnPermit Guide API",
    description="Finnish immigration questions, answered from official government sources.",
    version=VERSION,
)


# ── Event logging ─────────────────────────────────────────────────────────────
def event(name: str, **fields) -> None:
    """Emit one structured event line for downstream analytics.

    Deliberately not the Python log message — a single JSON object per line is
    what makes these queryable in Cloud Logging rather than grep-only.
    """
    print(json.dumps({
        "event": name,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }, ensure_ascii=False), flush=True)


# ── CORS ──────────────────────────────────────────────────────────────────────
# The browser never calls this API directly; the site's own edge route proxies
# server-side and server-side fetches ignore CORS. This only stops other
# websites calling the API from a visitor's browser. It does not stop curl —
# the edge secret and the rate limiter below are what protect the OpenAI spend.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS", "https://finnpermit.com,https://www.finnpermit.com"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Edge-Auth"],
    max_age=600,
)

# ── Input caps ────────────────────────────────────────────────────────────────
# Two tiers: HARD_* are enforced by Pydantic so oversized payloads are rejected
# before any handler or model call runs. The softer limits are handled in the
# route and answered with a normal sentence, because a 4xx is a worse
# experience than being told the message is too long.
MAX_QUESTION_CHARS   = int(os.getenv("MAX_QUESTION_CHARS", "2000"))
MAX_MESSAGE_CHARS    = int(os.getenv("MAX_MESSAGE_CHARS", "4000"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))   # 10 exchanges

HARD_QUESTION_CHARS   = MAX_QUESTION_CHARS * 4
HARD_MESSAGE_CHARS    = MAX_MESSAGE_CHARS * 4
HARD_HISTORY_MESSAGES = 100


# ── Caller identity ───────────────────────────────────────────────────────────
def client_ip(request: Request) -> str:
    """The real caller's address.

    Every request arrives from the site's edge, so request.client.host is the
    same proxy address for everyone. CF-Connecting-IP is forwarded by our own
    edge route and is the only header that identifies the actual visitor. It is
    trustworthy only because require_edge_secret() has already established the
    caller is that route — otherwise anyone could rotate it per request and walk
    straight through the per-IP limits.
    """
    if forwarded := request.headers.get("cf-connecting-ip", "").strip():
        return forwarded
    if xff := request.headers.get("x-forwarded-for", ""):
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Edge authentication ───────────────────────────────────────────────────────
# The Cloud Run URL is publicly reachable, so any rate limiting at the CDN can
# be bypassed by calling it directly. This shared secret is what makes the
# per-IP limits below mean anything.
#
# DEPLOY ORDER MATTERS: set EDGE_SHARED_SECRET on the frontend and redeploy it
# FIRST, then set it here. The other order 401s every live user until the
# frontend catches up.
#
# Fails closed: with no secret and no explicit opt-out, /ask rejects everything.
# A forgotten environment variable should be a visible outage, not a silently
# open endpoint billing someone else's OpenAI account.
EDGE_SHARED_SECRET    = os.getenv("EDGE_SHARED_SECRET", "").strip()
ALLOW_UNAUTHENTICATED = os.getenv("ALLOW_UNAUTHENTICATED", "").strip().lower() == "true"

if EDGE_SHARED_SECRET:
    log.info("edge secret enforced on /ask")
elif ALLOW_UNAUTHENTICATED:
    log.warning("ALLOW_UNAUTHENTICATED=true and no edge secret — /ask is open to direct callers")
else:
    log.error(
        "EDGE_SHARED_SECRET is unset and ALLOW_UNAUTHENTICATED is not 'true' — "
        "/ask will reject every request with 401. Set EDGE_SHARED_SECRET in "
        "production, or ALLOW_UNAUTHENTICATED=true for local development."
    )


def require_edge_secret(request: Request) -> None:
    if EDGE_SHARED_SECRET:
        presented = request.headers.get("x-edge-auth", "")
        if not hmac.compare_digest(presented, EDGE_SHARED_SECRET):
            event("auth_rejected", ip=client_ip(request), path=request.url.path)
            raise HTTPException(status_code=401, detail="Unauthorized.")
        return
    if ALLOW_UNAUTHENTICATED:
        return
    event("auth_misconfigured", path=request.url.path)
    raise HTTPException(status_code=401, detail="Unauthorized.")


# ── Rate limiting ─────────────────────────────────────────────────────────────
# Sliding windows held in memory, so limits are per instance. With N instances
# the real ceiling is N times these numbers — fine as a spend backstop. Move to
# a shared store only if this ever runs wide under real load.
#
# Per-IP limits are generous on purpose: Finnish carriers and workplaces put
# many users behind one NAT address. The global limits are the actual ceiling
# on model spend.
RATE_LIMIT_PER_MIN   = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
RATE_LIMIT_PER_DAY   = int(os.getenv("RATE_LIMIT_PER_DAY", "150"))
GLOBAL_LIMIT_PER_MIN = int(os.getenv("GLOBAL_LIMIT_PER_MIN", "60"))
GLOBAL_LIMIT_PER_DAY = int(os.getenv("GLOBAL_LIMIT_PER_DAY", "2000"))

_MINUTE, _DAY = 60, 86_400

_lock = threading.Lock()
_ip_minute:  dict[str, deque] = defaultdict(deque)
_ip_day:     dict[str, deque] = defaultdict(deque)
_all_minute: deque = deque()
_all_day:    deque = deque()


def _window(bucket: deque, now: float, seconds: int) -> deque:
    """Drop timestamps that have fallen out of the window, in place."""
    while bucket and now - bucket[0] > seconds:
        bucket.popleft()
    return bucket


def enforce_rate_limit(request: Request) -> None:
    """Raise 429 if this caller, or the service as a whole, is over budget."""
    ip, now = client_ip(request), time.time()

    with _lock:
        checks = (
            (_window(_all_day, now, _DAY), GLOBAL_LIMIT_PER_DAY,
             "The service has reached its daily limit. Please try again tomorrow.", "3600"),
            (_window(_all_minute, now, _MINUTE), GLOBAL_LIMIT_PER_MIN,
             "The service is busy right now. Please try again in a minute.", "60"),
            (_window(_ip_day[ip], now, _DAY), RATE_LIMIT_PER_DAY,
             "You have reached today's question limit. Please try again tomorrow.", "3600"),
            (_window(_ip_minute[ip], now, _MINUTE), RATE_LIMIT_PER_MIN,
             "Too many questions in a short time. Please wait a minute and try again.", "60"),
        )

        for bucket, limit, message, retry_after in checks:
            if len(bucket) >= limit:
                event("rate_limited", ip=ip, limit=limit, retry_after=retry_after)
                raise HTTPException(status_code=429, detail=message,
                                    headers={"Retry-After": retry_after})

        for bucket, *_ in checks:
            bucket.append(now)

        if len(_ip_day) > 10_000:      # keep the per-IP maps bounded
            for stale in [k for k, v in _ip_day.items() if not v or now - v[-1] > _DAY]:
                _ip_day.pop(stale, None)
                _ip_minute.pop(stale, None)


# ── Models ────────────────────────────────────────────────────────────────────
class Message(BaseModel):
    role:    str                                            # "human" | "ai"
    content: str = Field(..., max_length=HARD_MESSAGE_CHARS)


class AskRequest(BaseModel):
    question:     str = Field(..., max_length=HARD_QUESTION_CHARS)
    chat_history: list[Message] = Field(default_factory=list,
                                        max_length=HARD_HISTORY_MESSAGES)


class Source(BaseModel):
    url:       str
    title:     str
    domain:    str
    authority: str = ""


class AskResponse(BaseModel):
    answer:         str
    sources:        list[Source]
    category:       str | None
    quality:        str
    low_confidence: bool
    follow_ups:     list[str] = []
    chat_history:   list[Message]      # send this back on the next turn


class FeedbackRequest(BaseModel):
    message_id: str
    vote:       Literal["up", "down"]
    question:   str = ""
    answer:     str = ""


def clamp_history(messages: list[Message]) -> list[Message]:
    """Trim history to the recent turns and cap each message's length.

    The full history round-trips through the client every turn, so without this
    it grows without bound and is entirely caller-controlled.
    """
    return [
        Message(role=m.role, content=m.content[:MAX_MESSAGE_CHARS])
        for m in messages[-MAX_HISTORY_MESSAGES:]
    ]


# ── Routes ────────────────────────────────────────────────────────────────────
def corpus_date() -> str | None:
    """When the live corpus was collected, read from the index name.

    pipeline/index.py builds into migri-guide-YYYYMMDD, so the name itself
    carries the collection date. Deriving it here means the freshness shown on
    the site cannot drift from the data being served — the old site displayed a
    hardcoded "Data: May 2026" long after that stopped being true.
    """
    suffix = rag_config.PINECONE_INDEX.rsplit("-", 1)[-1]
    if len(suffix) == 8 and suffix.isdigit():
        return f"{suffix[:4]}-{suffix[4:6]}-{suffix[6:]}"
    return None


@app.get("/")
def health() -> dict:
    """Health check, and the corpus metadata the frontend shows as data freshness."""
    return {
        "status":      "ok",
        "service":     "FinnPermit Guide API",
        "version":     VERSION,
        "model":       rag_config.ANSWER_MODEL,
        "index":       rag_config.PINECONE_INDEX,
        "corpus_date": corpus_date(),
    }


@app.head("/")
def health_head() -> dict:
    return {}


@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest, http_request: Request) -> AskResponse:
    # Auth first — an unauthenticated caller should not consume rate-limit quota.
    require_edge_secret(http_request)
    enforce_rate_limit(http_request)

    history = clamp_history(request.chat_history)
    started = time.monotonic()

    if len(request.question) > MAX_QUESTION_CHARS:
        return AskResponse(
            answer=(
                f"That message is longer than I can process ({MAX_QUESTION_CHARS} "
                "characters). Could you shorten it to the key question — your permit "
                "type, how long you have been in Finland, and what you need to know?"
            ),
            sources=[], category=None, quality="needs_clarification",
            low_confidence=False, chat_history=history,
        )

    if is_too_short(request.question):
        return AskResponse(
            answer=(
                "Could you add a bit more detail? For example: 'How do I extend my "
                "work permit?' or 'What Kela benefits can I get on a B permit?'"
            ),
            sources=[], category=None, quality="needs_clarification",
            low_confidence=False, chat_history=history,
        )

    try:
        result = ask(
            request.question,
            [{"role": m.role, "content": m.content} for m in history],
        )
    except Exception:
        log.exception("ask failed")
        raise HTTPException(status_code=500, detail="Could not answer that question.")

    event(
        "ask",
        ip=client_ip(http_request),
        question_chars=len(request.question),
        turn=len(history) // 2 + 1,
        category=result["category"],
        quality=result["quality"],
        low_confidence=result["low_confidence"],
        sources=len(result["sources"]),
        duration_ms=round((time.monotonic() - started) * 1000),
    )

    return AskResponse(
        answer=result["answer"],
        sources=[Source(**source) for source in result["sources"]],
        category=result["category"],
        quality=result["quality"],
        low_confidence=result["low_confidence"],
        follow_ups=result["follow_ups"],
        chat_history=[Message(**turn) for turn in result["chat_history"]],
    )


@app.post("/feedback")
def submit_feedback(request: FeedbackRequest, http_request: Request) -> dict:
    """Record a vote on an answer.

    Emitted as a log event rather than written to a file: the container's disk
    is ephemeral, so anything written locally is lost on the next deploy.
    """
    event(
        "feedback",
        vote=request.vote,
        message_id=request.message_id,
        question=request.question[:500],
        answer=request.answer[:1000],
    )
    return {"ok": True}
