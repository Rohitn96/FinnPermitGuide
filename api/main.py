from __future__ import annotations

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Make sure Python can find rag/chain.py from api/main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response Models ─────────────────────────────────────────────
class Message(BaseModel):
    """A single turn in the conversation history."""
    role:    str   # "human" or "ai"
    content: str

class AskRequest(BaseModel):
    question:     str
    chat_history: list[Message] = []   # empty on first message

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
def ask_question(request: AskRequest):
    """
    Main endpoint. Accepts a question and optional conversation history.
    Returns an answer with source citations and updated history.
    """

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
            chat_history=request.chat_history,
            follow_ups=[],
        )

    # Off-topic check only applies to cold (first-turn) messages.
    # Mid-conversation questions inherit immigration context — blocking them
    # causes false rejections on valid follow-ups ("salary requirements per month"
    # is clearly about a permit when it follows three turns about PR requirements).
    # The LLM handles any genuinely off-topic parts via Rule 8 of the system prompt.
    if len(request.chat_history) == 0:
        off_topic, _ = check_off_topic(request.question)
        if off_topic:
            return AskResponse(
                answer=OUT_OF_SCOPE_REPLY,
                sources=[],
                category=None,
                low_confidence=False,
                chat_history=request.chat_history,
                follow_ups=[],
            )

    # ── Run the RAG chain ─────────────────────────────────────────────────
    try:
        history = deserialise(request.chat_history)
        result  = ask(request.question, history)
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