from __future__ import annotations

import hmac
import json
import sys
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

# Make sure Python can find rag/chain.py from api/main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from rag.chain import ask, check_off_topic, is_too_vague, OUT_OF_SCOPE_REPLY

FEEDBACK_LOG = Path("logs/feedback.jsonl")
FEEDBACK_LOG.parent.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MigriGuide API",
    description="AI-powered Finnish immigration assistant. Answers sourced exclusively from official Finnish government sources.",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────
# The browser never calls this API directly — frontend/src/app/api/ask/route.ts
# proxies server-side, and server-side fetches send no Origin header and ignore
# CORS entirely. This lock stops other websites calling the API from a visitor's
# browser; it does NOT stop curl. The edge secret and rate limiter below are
# what actually protect the OpenAI spend.
#
# Local dev against a directly-exposed backend: ALLOWED_ORIGINS=http://localhost:3000
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "https://finnpermit.com,https://www.finnpermit.com",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)

# ── Input caps ────────────────────────────────────────────────────────────
# Two tiers. HARD_* are enforced by Pydantic, so oversized payloads are refused
# with a 422 before any handler code or OpenAI call runs. The lower MAX_* values
# are applied in the handler and answered with a normal chat message.
MAX_QUESTION_CHARS   = int(os.getenv("MAX_QUESTION_CHARS",   "2000"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))    # 10 exchanges
MAX_MESSAGE_CHARS    = int(os.getenv("MAX_MESSAGE_CHARS",    "3000"))  # fits a full answer

HARD_QUESTION_CHARS   = MAX_QUESTION_CHARS * 4
HARD_MESSAGE_CHARS    = MAX_MESSAGE_CHARS  * 4
HARD_HISTORY_MESSAGES = 100

# ── Client identity ───────────────────────────────────────────────────────
def client_ip(request: Request) -> str:
    """Identify the real caller.

    Cloudflare Pages proxies /ask server-side, so request.client.host is a
    Cloudflare egress IP for every user. CF-Connecting-IP is forwarded by the
    edge route and is the only header here that identifies the actual person.
    It is only trustworthy because require_edge_secret() has already established
    that the caller is our own edge route — without that check any direct caller
    could rotate this header per request and walk through the per-IP limits.
    """
    cf = request.headers.get("cf-connecting-ip", "").strip()
    if cf:
        return cf
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ── Edge authentication ───────────────────────────────────────────────────
# The Cloud Run URL is publicly reachable, so Cloudflare's rate-limiting rule
# can be bypassed entirely by calling it directly. This shared secret is what
# makes the per-IP limits below mean anything.
#
# ROLLOUT ORDER MATTERS: set the secret on Cloudflare Pages FIRST and redeploy
# the frontend, THEN set it on Cloud Run. The other order 401s every live user
# until the frontend catches up.
#
# Fail CLOSED by default: with no secret configured every /ask call is rejected.
# Opening the endpoint up requires saying so out loud via ALLOW_UNAUTHENTICATED,
# so a forgotten env var is a visible outage rather than a silent open door.
EDGE_SHARED_SECRET    = os.getenv("EDGE_SHARED_SECRET", "").strip()
ALLOW_UNAUTHENTICATED = os.getenv("ALLOW_UNAUTHENTICATED", "").strip().lower() == "true"

if EDGE_SHARED_SECRET:
    print("[AUTH] edge secret enforced on /ask")
elif ALLOW_UNAUTHENTICATED:
    print("[AUTH] WARNING: ALLOW_UNAUTHENTICATED=true with no edge secret — "
          "/ask is OPEN to direct callers")
else:
    print("[AUTH] FATAL CONFIG: EDGE_SHARED_SECRET is unset and ALLOW_UNAUTHENTICATED "
          "is not 'true' — /ask will reject ALL requests with 401. Set "
          "EDGE_SHARED_SECRET (production) or ALLOW_UNAUTHENTICATED=true (local dev).")


def require_edge_secret(request: Request) -> None:
    """Reject callers that did not come through our own edge route."""
    if EDGE_SHARED_SECRET:
        presented = request.headers.get("x-edge-auth", "")
        if not hmac.compare_digest(presented, EDGE_SHARED_SECRET):
            print(f"[AUTH] rejected direct call ip={client_ip(request)} path={request.url.path}")
            raise HTTPException(status_code=401, detail="Unauthorized.")
        return

    if ALLOW_UNAUTHENTICATED:
        return

    print("[AUTH] rejected: no EDGE_SHARED_SECRET configured on this instance")
    raise HTTPException(status_code=401, detail="Unauthorized.")

# ── Rate limiting ─────────────────────────────────────────────────────────
# Sliding-window counters held in memory, so limits are PER CLOUD RUN INSTANCE.
# The service runs min-instances=1 and scales on concurrency; with N instances
# the real ceiling is N × these numbers. Fine as a spend backstop — move to
# Redis/Firestore only if this ever runs multi-instance under real load.
#
# Per-IP limits are deliberately generous: Finnish mobile carriers and
# workplaces put many users behind one NAT address, and this tool's users are
# mostly on phones. The GLOBAL limits are the true ceiling on OpenAI spend
# (~€0.0015 per /ask call, so GLOBAL_LIMIT_PER_DAY=2000 caps a bad day at ~€3).
RATE_LIMIT_PER_MIN   = int(os.getenv("RATE_LIMIT_PER_MIN",   "10"))
RATE_LIMIT_PER_DAY   = int(os.getenv("RATE_LIMIT_PER_DAY",   "150"))
GLOBAL_LIMIT_PER_MIN = int(os.getenv("GLOBAL_LIMIT_PER_MIN", "60"))
GLOBAL_LIMIT_PER_DAY = int(os.getenv("GLOBAL_LIMIT_PER_DAY", "2000"))

_MINUTE = 60
_DAY    = 86_400

_rl_lock = threading.Lock()
_ip_minute:  dict[str, deque] = defaultdict(deque)
_ip_day:     dict[str, deque] = defaultdict(deque)
_all_minute: deque = deque()
_all_day:    deque = deque()


def _window(bucket: deque, now: float, seconds: int) -> deque:
    """Drop timestamps older than the window, in place."""
    while bucket and now - bucket[0] > seconds:
        bucket.popleft()
    return bucket


def enforce_rate_limit(request: Request) -> None:
    """Raise 429 if this caller — or the service as a whole — is over budget."""
    ip  = client_ip(request)
    now = time.time()

    with _rl_lock:
        checks = (
            (_window(_all_day,       now, _DAY),    GLOBAL_LIMIT_PER_DAY,
             "The service has reached its daily limit. Please try again tomorrow.", "3600"),
            (_window(_all_minute,    now, _MINUTE), GLOBAL_LIMIT_PER_MIN,
             "The service is busy right now. Please try again in a minute.", "60"),
            (_window(_ip_day[ip],    now, _DAY),    RATE_LIMIT_PER_DAY,
             "You have reached today's question limit. Please try again tomorrow.", "3600"),
            (_window(_ip_minute[ip], now, _MINUTE), RATE_LIMIT_PER_MIN,
             "Too many questions in a short time. Please wait a minute and try again.", "60"),
        )

        for bucket, limit, message, retry_after in checks:
            if len(bucket) >= limit:
                # stdout → Cloud Logging, so this is alertable
                print(f"[RATELIMIT] blocked ip={ip} limit={limit} retry_after={retry_after}")
                raise HTTPException(
                    status_code=429,
                    detail=message,
                    headers={"Retry-After": retry_after},
                )

        for bucket, *_ in checks:
            bucket.append(now)

        # Keep the per-IP dicts from growing without bound
        if len(_ip_day) > 10_000:
            for stale in [k for k, v in _ip_day.items() if not v or now - v[-1] > _DAY]:
                _ip_day.pop(stale, None)
                _ip_minute.pop(stale, None)

# ── Request / Response Models ─────────────────────────────────────────────
class Message(BaseModel):
    """A single turn in the conversation history."""
    role:    str                                              # "human" or "ai"
    content: str = Field(..., max_length=HARD_MESSAGE_CHARS)

class AskRequest(BaseModel):
    question:     str = Field(..., max_length=HARD_QUESTION_CHARS)
    chat_history: list[Message] = Field(   # empty on first message
        default_factory=list, max_length=HARD_HISTORY_MESSAGES
    )

class Source(BaseModel):
    url:      str
    title:    str
    domain:   str
    category: str

class AskResponse(BaseModel):
    answer:          str
    sources:         list[Source]
    category:        str | None
    low_confidence:  bool
    chat_history:    list[Message]   # updated history — send this back next turn
    follow_ups:      list[str] = []  # suggested follow-up questions from chain.py
    response_type:   str | None = None  # full_answer | partial_answer | clarification_needed | ambiguous | complex_case | no_data | out_of_scope

# ── History Serialisation ─────────────────────────────────────────────────
# chain.py uses plain {role, content} dicts internally — NOT LangChain objects.
# These helpers convert between Pydantic Message models and plain dicts.

def deserialise(messages: list[Message]) -> list[dict]:
    """Convert Pydantic Message list → plain dicts for chain.py"""
    return [{"role": m.role, "content": m.content} for m in messages]

def serialise(messages: list[dict]) -> list[Message]:
    """Convert plain dicts returned by chain.py → Pydantic Message list"""
    return [Message(role=m["role"], content=m["content"]) for m in messages]

def clamp_history(messages: list[Message]) -> list[Message]:
    """Keep the most recent turns and clamp any oversized message.

    chain.py already limits what reaches the LLM (MAX_HISTORY_TURNS = 6
    exchanges), but the full history is echoed to the client every turn and
    resent on the next one — unbounded, and fully caller-controlled. 20 messages
    ≈ 10 exchanges: wider than the LLM window so extract_session_facts() still
    sees permit type or job loss mentioned earlier in the session.
    """
    return [
        Message(role=m.role, content=m.content[:MAX_MESSAGE_CHARS])
        for m in messages[-MAX_HISTORY_MESSAGES:]
    ]

# ── Routes ────────────────────────────────────────────────────────────────
@app.get("/")
def health():
    """Health check — confirms the API is running."""
    return {
        "status":  "ok",
        "service": "MigriGuide API",
        "version": "1.0.0",
    }

@app.head("/")
def health_head():
    """HEAD health check for UptimeRobot monitors."""
    return {}

@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest, http_request: Request):
    """
    Main endpoint. Accepts a question and optional conversation history.
    Returns an answer with source citations and updated history.
    """
    # Auth first: an unauthenticated caller should not consume rate-limit quota.
    require_edge_secret(http_request)
    enforce_rate_limit(http_request)

    history = clamp_history(request.chat_history)

    # ── Length cap ────────────────────────────────────────────────────────
    # Answered as a normal message rather than a 4xx: an error status is a worse
    # experience than a sentence explaining what to do.
    if len(request.question) > MAX_QUESTION_CHARS:
        return AskResponse(
            answer=(
                f"That message is too long for me to process (limit "
                f"{MAX_QUESTION_CHARS} characters). Could you shorten it to the "
                "key question — your permit type, how long you have been in "
                "Finland, and what you need to know?"
            ),
            sources=[],
            category=None,
            low_confidence=False,
            chat_history=history,
            follow_ups=[],
        )

    # ── Pre-checks ────────────────────────────────────────────────────────
    if is_too_vague(request.question):
        return AskResponse(
            answer=(
                "Could you add a bit more detail? "
                "For example: 'How do I extend my work permit?' "
                "or 'What Kela benefits can I get on a B permit?'"
            ),
            sources=[],
            category=None,
            low_confidence=False,
            chat_history=history,
            follow_ups=[],
        )

    # Off-topic check only applies to cold (first-turn) messages.
    # Mid-conversation questions inherit immigration context — blocking them
    # causes false rejections on valid follow-ups ("salary requirements per month"
    # is clearly about a permit when it follows three turns about PR requirements).
    # The LLM handles any genuinely off-topic parts via Rule 8 of the system prompt.
    if len(history) == 0:
        off_topic, _ = check_off_topic(request.question)
        if off_topic:
            return AskResponse(
                answer=OUT_OF_SCOPE_REPLY,
                sources=[],
                category=None,
                low_confidence=False,
                chat_history=history,
                follow_ups=[],
            )

    # ── Run the RAG chain ─────────────────────────────────────────────────
    try:
        result = ask(request.question, deserialise(history))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ── Return structured response ────────────────────────────────────────
    return AskResponse(
        answer=result["answer"],
        sources=[
            Source(
                url=s.get("url",       ""),
                title=s.get("title",   ""),
                domain=s.get("domain", ""),
                category=s.get("category", ""),
            )
            for s in result["sources"]
        ],
        category=result["category"],
        low_confidence=result["low_conf"],
        chat_history=serialise(result["chat_history"]),
        follow_ups=result.get("follow_ups", []),
        response_type=result.get("response_type"),
    )


# ── Feedback ──────────────────────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    message_id: str
    vote:       Literal["up", "down"]
    answer:     str = ""

@app.post("/feedback")
def submit_feedback(request: FeedbackRequest):
    entry = {
        "timestamp":  datetime.now().isoformat(),
        "message_id": request.message_id,
        "vote":       request.vote,
        "answer":     request.answer[:500],
    }
    try:
        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}