"""
Retrieval: question in, ranked official source passages out.

Two stages. Pinecone returns CANDIDATES chunks by embedding similarity (good
recall, weak precision), then a cross-encoder reranker reads the question and
each chunk together and keeps the best CONTEXT_CHUNKS (good precision).

The reranker is what replaced a hand-maintained table of per-topic keyword
"boost queries". That table needed a new entry every time a question type was
missed, and it misrouted whenever a question matched two topics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import OpenAI
from pinecone import Pinecone

from rag import config

log = logging.getLogger(__name__)

_openai   = OpenAI(api_key=config.OPENAI_API_KEY)
_pinecone = Pinecone(api_key=config.PINECONE_API_KEY)
_index    = _pinecone.Index(config.PINECONE_INDEX)

log.info("retrieval ready — index=%s", config.PINECONE_INDEX)


@dataclass
class Passage:
    """One retrieved chunk of official source text."""
    text:      str
    url:       str
    title:     str
    domain:    str
    authority: str
    score:     float

    def as_prompt_block(self, n: int) -> str:
        return (
            f'<source id="{n}" url="{self.url}" authority="{self.authority}">\n'
            f"{self.text.strip()}\n"
            f"</source>"
        )


def _embed(text: str) -> list[float]:
    return _openai.embeddings.create(model=config.EMBED_MODEL, input=text).data[0].embedding


def search(query: str) -> list[Passage]:
    """Return the most relevant passages for a query, best first."""
    try:
        response = _index.query(
            vector=_embed(query),
            top_k=config.CANDIDATES,
            include_metadata=True,
        )
    except Exception:
        log.exception("vector search failed")
        return []

    candidates = []
    for match in response.matches:
        meta = dict(match.metadata)
        text = meta.get("text", "")
        if not text:
            continue
        candidates.append(Passage(
            text=text,
            url=meta.get("source", ""),
            title=meta.get("title", ""),
            domain=meta.get("domain", ""),
            authority=meta.get("authority", "Official Finnish source"),
            score=float(match.score),
        ))

    if not candidates:
        return []

    return _rerank(query, candidates)


def _rerank(query: str, candidates: list[Passage]) -> list[Passage]:
    """Reorder by cross-encoder relevance, then select for diversity."""
    try:
        result = _pinecone.inference.rerank(
            model=config.RERANK_MODEL,
            query=query,
            documents=[{"id": str(i), "text": c.text} for i, c in enumerate(candidates)],
            # Score the whole pool, not just the slots we intend to keep — the
            # selection below needs lower-ranked passages to fall back on when a
            # page has already used its quota.
            top_n=len(candidates),
            return_documents=False,
        )
    except Exception:
        # A reranker outage should degrade quality, not take the service down.
        log.exception("rerank failed — falling back to vector similarity order")
        return _select(candidates)

    # row.index is the position in the documents list we passed in, which is
    # candidate order. row.document is None here because we asked the API not to
    # echo the text back.
    ranked = []
    for row in result.data:
        passage = candidates[row.index]
        passage.score = float(row.score)
        ranked.append(passage)
    return _select(ranked)


def _select(ranked: list[Passage]) -> list[Passage]:
    """Take the best passages, allowing only MAX_PER_SOURCE from any one page.

    Anything skipped for exceeding its quota is held back and used to fill
    remaining slots, so a narrow question that genuinely has one good source
    still gets a full context rather than being starved for the sake of variety.
    """
    chosen, overflow = [], []
    used: dict[str, int] = {}

    for passage in ranked:
        if len(chosen) >= config.CONTEXT_CHUNKS:
            break
        if used.get(passage.url, 0) < config.MAX_PER_SOURCE:
            used[passage.url] = used.get(passage.url, 0) + 1
            chosen.append(passage)
        else:
            overflow.append(passage)

    if len(chosen) < config.CONTEXT_CHUNKS:
        chosen.extend(overflow[: config.CONTEXT_CHUNKS - len(chosen)])
    return chosen


def format_sources(passages: list[Passage]) -> str:
    """Render passages as the <source> blocks the answer prompt expects."""
    if not passages:
        return "<no_sources>Nothing in the knowledge base matched this question.</no_sources>"
    return "\n\n".join(p.as_prompt_block(i) for i, p in enumerate(passages, 1))


def unique_sources(passages: list[Passage]) -> list[dict]:
    """Deduplicate passages to one entry per source URL, best-ranked first."""
    seen, out = set(), []
    for p in passages:
        if p.url and p.url not in seen:
            seen.add(p.url)
            out.append({
                "url": p.url,
                "title": p.title,
                "domain": p.domain.upper(),
                "authority": p.authority,
            })
    return out
