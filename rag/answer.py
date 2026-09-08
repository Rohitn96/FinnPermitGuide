"""
The question-answering pipeline.

    rewrite the question  →  retrieve and rerank  →  answer from the sources

Three steps, two LLM calls. Anything that cannot be traced to a retrieved
source does not reach the user.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, TypedDict

from openai import OpenAI

from rag import config, grounding, retrieval
from rag.prompts import (
    ANSWER_SCHEMA,
    ANSWER_SYSTEM,
    OUT_OF_SCOPE_REPLY,
    REWRITE_SCHEMA,
    REWRITE_SYSTEM,
)

log = logging.getLogger(__name__)

_client = OpenAI(api_key=config.OPENAI_API_KEY)


class Turn(TypedDict):
    role: str        # "human" | "ai"
    content: str


class Answer(TypedDict):
    answer:         str
    sources:        list[dict]
    category:       str
    quality:        str
    low_confidence: bool
    follow_ups:     list[str]
    chat_history:   list[Turn]
    # The passages the answer was actually generated from. The API does not
    # serialise this; the eval harness needs it to grade grounding against the
    # same text the model saw, rather than re-retrieving and grading against
    # something slightly different.
    passages:       list


def is_too_short(question: str) -> bool:
    """A single word carries too little to retrieve on."""
    return len(question.strip().split()) < 2


# Messages that are purely social. Matched whole, so "thanks, but what about my
# spouse?" is not caught — only a message that is nothing but an acknowledgement.
_ACK_PHRASE = (
    r"thank you|thank you so much|thanks|thx|ty|cheers|great|perfect|awesome|"
    r"excellent|nice|cool|ok|okay|got it|understood|that helps|that helped|"
    r"good to know|appreciate it|hello|hi|hey|good morning|good evening|"
    r"bye|goodbye|see you|no worries|alright"
)

# The phrase group repeats so natural combinations like "ok, got it" or
# "thanks, great" match as a whole rather than only their first word.
_ACKNOWLEDGEMENT = re.compile(
    rf"^\s*(?:(?:{_ACK_PHRASE})[\s,!.?…—-]*)+"
    r"(?:(?:that|this) (?:was|is)[\s,]*)?"
    r"(?:really |very |so |super )?"
    r"(?:helpful|useful|great|clear|good|kind|much)?"
    r"[\s,!.?…—-]*$",
    re.IGNORECASE,
)


def is_acknowledgement(message: str) -> bool:
    """True for a message that is only thanks or a greeting.

    Handled without retrieval or generation. Left to the prompt, the model
    receives a dozen retrieved passages alongside "thanks!" and cannot resist
    using them — the reply came back at 316, then 256, then 170 words across
    runs. A rule the model follows only sometimes is not a rule, and this costs
    two API calls to get wrong.
    """
    return len(message.split()) <= 8 and bool(_ACKNOWLEDGEMENT.match(message.strip()))


def _history_for_model(history: list[Turn]) -> list[dict[str, str]]:
    """Recent turns as OpenAI chat messages."""
    recent = history[-(config.HISTORY_TURNS * 2):]
    return [
        {"role": "user" if turn["role"] in ("human", "user") else "assistant",
         "content": turn["content"]}
        for turn in recent
    ]


def rewrite(question: str, history: list[Turn]) -> tuple[str, str]:
    """Return (standalone English query, language the user wrote in).

    The language is decided here rather than left to the answering model. By the
    time that model runs, its system prompt and every source passage are in
    English, and a "reply in their language" rule loses to all that English
    context — Finnish questions came back answered in English. Naming the target
    language explicitly is what makes it stick.
    """
    try:
        response = _client.chat.completions.create(
            model=config.REWRITE_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM},
                *_history_for_model(history),
                {"role": "user", "content": question},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "rewrite", "schema": REWRITE_SCHEMA, "strict": True},
            },
        )
        parsed = json.loads(response.choices[0].message.content)
        return (parsed.get("query") or question).strip(), parsed.get("language") or "English"
    except Exception:
        # Retrieval on the raw question is worse but still works.
        log.exception("query rewrite failed — using the raw question")
        return question, "English"


def _generate(
    question: str, query: str, passages: list, history: list[Turn],
    language: str = "English", correction: str = "",
) -> dict[str, Any]:
    """Ask the model for a grounded answer in the response schema."""
    # The language directive goes first, before the persona and long before the
    # sources. The query the model receives is an English rewrite and every
    # source passage is English, so the same instruction placed after all that
    # English gets ignored — Finnish questions kept coming back in English even
    # with an explicit "write entirely in Finnish" at the end of the prompt.
    # Arabic obeyed from either position; Finnish only obeys from the top.
    preamble = ""
    if language.lower() != "english":
        preamble = (
            f"WRITE YOUR ENTIRE RESPONSE IN {language.upper()}.\n\n"
            f"The user asked in {language}, so the `answer` field and every "
            f"`follow_ups` entry must be written in {language} — not English. "
            "The source extracts below are in English; translate what you take "
            "from them. Keep official Finnish terms and authority names next to "
            "your translation where the reader would meet them on a form.\n\n"
        )

    system = (
        f"{preamble}{ANSWER_SYSTEM}\n\n"
        f"# Sources\n\n{retrieval.format_sources(passages)}"
    )
    if preamble:
        system += f"\n\n# Reminder\n\n{preamble.strip()}"

    user_message = query
    if question.strip().lower() != query.strip().lower():
        user_message = f'{query}\n\n[The user actually wrote: "{question}"]'
    if language.lower() != "english":
        user_message += f"\n\n[Answer in {language}.]"
    if correction:
        user_message = f"{user_message}\n\n{correction}"

    response = _client.chat.completions.create(
        model=config.ANSWER_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            *_history_for_model(history),
            {"role": "user", "content": user_message},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": ANSWER_SCHEMA, "strict": True},
        },
    )
    return json.loads(response.choices[0].message.content)


def _regenerate_without(
    question: str, query: str, passages: list, history: list[Turn],
    figures: list[str], language: str = "English",
) -> dict[str, Any] | None:
    """Retry once, naming the figures that were not in the sources.

    Pointing at the specific offending numbers works far better than repeating
    the general rule, which the model had already been given and still broke.
    """
    listed = ", ".join(figures)
    log.warning("ungrounded figures in answer, regenerating: %s", listed)
    try:
        return _generate(
            question, query, passages, history, language,
            correction=(
                f"CORRECTION: your previous answer stated {listed}, which appears in none "
                "of the sources above. Rewrite the answer. State only figures that appear "
                "verbatim in a source. Where a figure is genuinely not in the sources, say "
                "so plainly and name the official site that publishes it, rather than "
                "supplying a number."
            ),
        )
    except Exception:
        log.exception("regeneration failed")
        return None


def ask(question: str, chat_history: list[Turn] | None = None) -> Answer:
    """Answer one question. Never raises — failures come back as an Answer."""
    history: list[Turn] = list(chat_history or [])
    started = time.monotonic()

    def reply(
        text: str, *, category: str = "general", quality: str = "not_in_sources",
        sources: list[dict] | None = None, follow_ups: list[str] | None = None,
        low_confidence: bool = False, passages: list | None = None,
    ) -> Answer:
        return {
            "answer": text,
            "sources": sources or [],
            "category": category,
            "quality": quality,
            "low_confidence": low_confidence,
            "follow_ups": follow_ups or [],
            "passages": passages or [],
            "chat_history": history + [
                {"role": "human", "content": question},
                {"role": "ai", "content": text},
            ],
        }

    if is_acknowledgement(question):
        return reply(
            "You're welcome! Ask me anything else about living in or moving to Finland.",
            quality="complete",
        )

    if is_too_short(question):
        return reply(
            "Could you tell me a bit more? It helps to know your permit type, how "
            "long you have been in Finland, and what you are trying to do.",
            quality="needs_clarification",
        )

    query, language = rewrite(question, history)
    passages = retrieval.search(query)

    if not passages:
        return reply(OUT_OF_SCOPE_REPLY)  # nothing retrieved, so nothing to ground in

    # The reranker scores how well the best passage actually answers the query,
    # which is a far better confidence signal than raw embedding distance.
    low_confidence = passages[0].score < config.MIN_RELEVANCE

    try:
        result = _generate(question, query, passages, history, language)
    except Exception:
        log.exception("answer generation failed")
        return reply(
            "Something went wrong on my end. Please try asking again.",
            quality="not_in_sources", passages=passages,
        )

    # Verify every figure against the sources before this can reach anyone. The
    # prompt forbids inventing numbers and the model usually complies, but an
    # invented income threshold is the one failure worth spending a second
    # request to avoid.
    quality = result["answer_quality"]
    unsupported = grounding.ungrounded_figures(result["answer"], passages, question)
    if unsupported:
        retry = _regenerate_without(
            question, query, passages, history, unsupported, language
        )
        if retry:
            still_bad = grounding.ungrounded_figures(retry["answer"], passages, question)
            if not still_bad:
                result = retry
                unsupported = []
            else:
                # Second attempt still ungrounded. Return the retry — it is
                # usually the more cautious of the two — but flag it, so the UI
                # warns rather than presenting invented numbers confidently.
                log.error("figures still ungrounded after retry: %s", still_bad)
                result, unsupported = retry, still_bad
                quality = "partial"

    answer  = result["answer"].strip()
    cited   = set(result.get("cited_urls") or [])
    # Only ever show sources that were actually retrieved — this is what stops a
    # hallucinated URL reaching the user even if the model invents one.
    sources = [s for s in retrieval.unique_sources(passages) if s["url"] in cited]
    if not sources:
        sources = retrieval.unique_sources(passages)[:3]

    log.info(
        "answered in %.1fs  quality=%s category=%s top_score=%.3f sources=%d",
        time.monotonic() - started, quality, result["category"],
        passages[0].score, len(sources),
    )

    return reply(
        answer,
        category=result["category"],
        quality=quality,
        sources=sources,
        follow_ups=(result.get("follow_ups") or [])[:2],
        low_confidence=(
            low_confidence or quality == "not_in_sources" or bool(unsupported)
        ),
        passages=passages,
    )
