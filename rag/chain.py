"""
MigriGuide — RAG Intelligence Layer v3
rag/chain.py

Vectorstore backend is selected by .env:
  USE_PINECONE=true   → Pinecone (production)
  USE_PINECONE=false  → ChromaDB (local dev, default)
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOP_K             = 10      # chunks returned per sub-query retrieval
FETCH_K           = 40      # MMR candidate pool size
DIVERSITY         = 0.65    # MMR lambda (0=similarity, 1=diversity)
CONF_THRESHOLD    = 0.22    # relevance score below this triggers low-confidence warning
BOOST_K           = 4       # extra chunks added for topic-boosted queries
MAX_HISTORY_TURNS = 6       # conversation turns passed to query rewrite step
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# MODELS & VECTORSTORE
# ─────────────────────────────────────────────
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

_use_pinecone = os.getenv("USE_PINECONE", "false").lower() == "true"

if _use_pinecone:
    import numpy as np
    from pinecone import Pinecone as _PineconeClient
    from langchain_core.documents import Document as _Document

    class _PineconeStore:
        """Minimal ChromaDB-compatible wrapper around the Pinecone SDK."""

        def __init__(self, index, embed_fn):
            self._index = index
            self._embed = embed_fn

        def _query(self, query: str, top_k: int, include_values: bool = False):
            vec = self._embed.embed_query(query)
            return self._index.query(
                vector=vec, top_k=top_k,
                include_metadata=True, include_values=include_values,
            ), vec

        @staticmethod
        def _to_doc(match) -> _Document:
            meta = dict(match.metadata)
            text = meta.pop("text", "")
            return _Document(page_content=text, metadata=meta)

        def similarity_search(self, query: str, k: int = 4) -> list:
            res, _ = self._query(query, top_k=k)
            return [self._to_doc(m) for m in res.matches]

        def similarity_search_with_relevance_scores(self, query: str, k: int = 4) -> list:
            res, _ = self._query(query, top_k=k)
            return [(self._to_doc(m), float(m.score)) for m in res.matches]

        def max_marginal_relevance_search(
            self, query: str, k: int = 4, fetch_k: int = 20, lambda_mult: float = 0.5
        ) -> list:
            res, q_vec = self._query(query, top_k=fetch_k, include_values=True)
            if not res.matches:
                return []
            candidate_vecs = np.array([m.values for m in res.matches], dtype=np.float32)
            q_arr = np.array(q_vec, dtype=np.float32)
            selected, remaining = [], list(range(len(res.matches)))
            for _ in range(min(k, len(res.matches))):
                if not remaining:
                    break
                q_sims = candidate_vecs[remaining] @ q_arr / (
                    np.linalg.norm(candidate_vecs[remaining], axis=1) * np.linalg.norm(q_arr) + 1e-9
                )
                if selected:
                    sel_vecs = candidate_vecs[selected]
                    red_sims = (candidate_vecs[remaining] @ sel_vecs.T).max(axis=1) / (
                        np.linalg.norm(candidate_vecs[remaining], axis=1)[:, None]
                        * np.linalg.norm(sel_vecs, axis=1)[None, :] + 1e-9
                    )
                else:
                    red_sims = np.zeros(len(remaining))
                scores = lambda_mult * q_sims - (1 - lambda_mult) * red_sims
                best = remaining[int(np.argmax(scores))]
                selected.append(best)
                remaining.remove(best)
            return [self._to_doc(res.matches[i]) for i in selected]

    _pc    = _PineconeClient(api_key=os.getenv("PINECONE_API_KEY"))
    _index = _pc.Index(os.getenv("PINECONE_INDEX_NAME", "migri-guide"))
    vectorstore = _PineconeStore(_index, embeddings)
    print("[INFO] Using Pinecone vectorstore")
else:
    from langchain_chroma import Chroma
    vectorstore = Chroma(
        collection_name="migri_guide",
        embedding_function=embeddings,
        persist_directory="data/chroma_db",
    )
    print("[INFO] Using local ChromaDB vectorstore")

# gpt-4o-mini is used for all inference (synthesis of retrieved text, query rewriting).
# 95% of gpt-4o quality at 10% of the cost for retrieval-augmented tasks.
# Swap llm back to gpt-4o below only if answer quality measurably degrades.
llm      = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────
CONTEXTUALIZE_SYSTEM = (
    "You rewrite follow-up questions for a Finnish immigration assistant. "
    "Given the conversation history and the user's latest message, produce a single "
    "self-contained search query that includes all relevant personal context from the history "
    "(permit type, personal situation, employment, education, goals, duration of stay in Finland). "
    "Output ONLY the rewritten query — no explanation, no preamble."
)

CONTEXTUALIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", CONTEXTUALIZE_SYSTEM),
    MessagesPlaceholder("chat_history"),
    ("human", "{question}"),
])

MULTI_QUERY_SYSTEM = (
    "You decompose complex Finnish immigration questions into focused sub-queries "
    "for a vector knowledge base. Given a question, output a JSON array of 1–3 strings. "
    "Each string must target ONE distinct aspect of the question "
    "(e.g. permit type eligibility, tax rules, DVV registration, Kela benefits, citizenship requirements). "
    "For a simple single-topic question, output a 1-item array. "
    "Output ONLY the raw JSON array — no markdown, no explanation."
)

SYSTEM_PROMPT = """\
You are MigriGuide, an AI assistant that answers Finnish immigration questions exclusively from official source chunks provided below. Never use your own training knowledge about Finnish immigration law.

RULES:

1. SOURCE CONSTRAINT: Answer using ONLY the provided context chunks. If your training knowledge conflicts with a chunk, always follow the chunk.

2. DEFLECTION THRESHOLD — CRITICAL: Use the deflection response ONLY when the question topic is COMPLETELY absent from ALL chunks — meaning zero chunks even partially address the subject. If any chunk contains relevant partial information, use it and clearly note what remains uncertain ("For complete details on this specific point, verify at migri.fi"). NEVER deflect when chunks exist but require synthesis across multiple topics. Synthesizing across chunks is your core job.
   Deflection (ONLY when topic is fully absent from all chunks):
   "I don't have enough official information on this. Please check migri.fi or call Migri: 0295 419 700 (weekdays 8:00–16:00)."

3. PERSONALIZATION — CRITICAL: When the user describes their personal situation (permit type, years in Finland, education level, employment status, language test score, income, goals), apply the retrieved requirements directly to their specific case. Do NOT list all generic paths. Reason explicitly: "Based on what you've told me — [X] — you qualify under [condition Y] because [Z]." If a requirement is clearly met by what the user stated, confirm it. If unmet or uncertain, state it clearly. Filter requirements to those actually relevant to the user.

4. THRESHOLDS: Always quote specific thresholds verbatim when they appear in the chunks — language levels (A2, B1, B2), income amounts, years of residence, fees. These are exactly what users need. Never omit or soften them.

5. COMPLETENESS: Scan ALL provided chunks before answering. Do not stop at the first relevant chunk — lower-ranked chunks often contain the specific threshold or condition the user needs.

6. MULTIPLE PATHS: If multiple application paths exist (e.g., two routes to permanent residence), list all applicable paths clearly and state which one applies to the user's situation if they have described it.

7. FORMAT: Use a numbered list when there are 3 or more distinct requirements or steps. Use plain prose otherwise. Never use bullet points for 1–2 items.

8. LANGUAGE: Plain English. Direct and clear. Suitable for non-native speakers. No legal jargon, no Latin, no unexplained abbreviations.

9. ATTRIBUTION: Attribute facts: "According to Migri..." or "Migri states..." or "Kela states...". Never say "you should" or give personal legal advice.

10. CONTRADICTIONS: If two chunks directly contradict each other, say: "Note: official sources differ on this — check migri.fi for the current rule."

11. SCOPE: If the question is entirely outside Finnish immigration, residence, registration, benefits, or tax for immigrants, respond: "This is outside MigriGuide's scope. I only cover Finnish immigration questions."

12. CONCISENESS: No padding, no footers, no repetition of the question. Get to the answer.

13. INTEGRATION REQUIREMENTS: When chunks mention integration requirements (language level, work history, years of residence) for permanent residence or citizenship, always include those specifics — they are the core of what users need.

CONTEXT CHUNKS:
{context}

Respond ONLY with a valid JSON object. No markdown fences. No text before or after the JSON.

{{"answer": "your answer here — plain text, no HTML. Numbered list only for 3+ distinct requirements or steps.",
  "category": "pick exactly one: work | family | study | permanent | asylum | temporary_protection | benefits | citizenship | tax | registration | eu_citizen | appeals | processing | overstay | general",
  "cited_urls": ["every URL from context chunks that contributed facts to this answer"],
  "follow_ups": ["2 specific actionable follow-up questions the user is most likely to ask next, based on natural next steps or gaps in the answer"]
}}"""

# ─────────────────────────────────────────────
# CONSTANTS  (exported for use by api/main.py)
# ─────────────────────────────────────────────
OUT_OF_SCOPE_REPLY = (
    "This is outside MigriGuide's scope. "
    "I can only answer questions about Finnish immigration, "
    "residence permits, registration, benefits, and related topics."
)

# ─────────────────────────────────────────────
# OFF-TOPIC & VAGUE CHECKS
# ─────────────────────────────────────────────
OFF_TOPIC_KEYWORDS = [
    "recipe", "weather", "football", "sport", "stock market", "crypto",
    "movie", "music", "song", "dating", "relationship advice",
    "hotel", "restaurant recommendation", "flight booking", "tourism",
]

def check_off_topic(question: str) -> tuple:
    q = question.lower()
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in q:
            print(f"[DEBUG] Off-topic keyword fired: {kw!r}")
            return True, kw
    return False, ""

def is_too_vague(question: str) -> bool:
    return len(question.strip().split()) < 4


# ─────────────────────────────────────────────
# CATEGORY DETECTION (keyword fallback)
# Used only if LLM JSON parse fails completely.
# ─────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "work":                 ["work permit", "ttol", "employee", "employer", "job permit", "employed person", "seasonal work", "specialist"],
    "family":               ["family", "spouse", "child", "reunification", "family member", "dependent"],
    "study":                ["student", "study", "university", "degree", "thesis", "scholarship", "exchange"],
    "permanent":            ["permanent", "p permit", "pr permit", "indefinite", "long-term"],
    "asylum":               ["asylum", "refugee", "international protection", "persecution"],
    "temporary_protection": ["temporary protection", "ukraine", "mass influx"],
    "benefits":             ["kela", "benefit", "social assistance", "unemployment", "allowance", "social security"],
    "citizenship":          ["citizenship", "citizen", "naturali", "passport", "finnish national"],
    "tax":                  ["tax", "vero", "verotus", "income tax", "tax card", "verokortti"],
    "registration":         ["register", "dvv", "municipality", "home municipality", "population register"],
    "eu_citizen":           ["eu citizen", "eea", "nordic", "freedom of movement", "right of residence"],
    "appeals":              ["appeal", "objection", "administrative court", "hallinto-oikeus", "negative decision"],
    "processing":           ["processing time", "waiting", "how long", "status", "fast track"],
    "overstay":             ["overstay", "expired", "illegal stay", "deport", "removal", "leave the country"],
}

def detect_category(text: str) -> str:
    t = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return category
    return "general"


# ─────────────────────────────────────────────
# SESSION CONTEXT EXTRACTION
# ─────────────────────────────────────────────
def extract_session_facts(chat_history: list) -> str:
    human_text = " ".join(
        m["content"].lower()
        for m in chat_history
        if isinstance(m, dict) and m.get("role") in ("human", "user")
    )
    if not human_text:
        return ""

    facts = []

    permit_checks = [
        ("job search",      "job search permit holder"),
        ("startup permit",  "startup permit holder"),
        ("student permit",  "student residence permit holder"),
        ("specialist",      "specialist work permit holder"),
        ("work permit",     "work permit holder"),
        ("b permit",        "B permit holder (temporary residence)"),
        ("a permit",        "A permit holder (continuous residence)"),
        ("d permit",        "D permit holder (long-term EU resident)"),
    ]
    for key, label in permit_checks:
        if key in human_text:
            facts.append(label)
            break

    if any(w in human_text for w in ["master", "msc", "bachelor", "degree", "graduated", "thesis", "phd", "doctorate"]):
        facts.append("completed degree in Finland")

    if any(w in human_text for w in ["contract", "60h", "part-time", "full-time", "employed", "working", "job offer"]):
        facts.append("has employment contract in Finland")

    if any(w in human_text for w in ["permanent residence", "pr permit", " pr ", "p permit", "perm res"]):
        facts.append("goal: permanent residence permit")
    if any(w in human_text for w in ["citizen", "citizenship", "naturali"]):
        facts.append("goal: Finnish citizenship")

    return " | ".join(facts)


# ─────────────────────────────────────────────
# TOPIC BOOST QUERIES
# Supplementary retrieval to ensure specific requirement chunks
# (language level, income thresholds, years of residence) are present.
# ─────────────────────────────────────────────
TOPIC_BOOST = {
    "permanent": (
        "permanent residence permit language skills requirement A2 Finnish Swedish "
        "period of residence years continuous work history integration requirement paths"
    ),
    "citizenship": (
        "Finnish citizenship requirements years of residence language test naturalization "
        "conditions income integration declaration dual citizenship"
    ),
    "work": (
        "work permit requirements employer employee salary income requirement TTOL "
        "employed person collective agreement minimum wage specialist permit"
    ),
    "family": (
        "family reunification requirements sponsor income financial resources documents "
        "spouse child residence permit Finland"
    ),
    "eu_citizen": (
        "EU citizen permanent right of residence D permit five years registration "
        "right of residence family member EU free movement"
    ),
    "benefits": (
        "Kela benefits eligibility residence permit B permit A permit permanent "
        "social assistance housing allowance unemployment entitlement Finland"
    ),
    "tax": (
        "Finland income tax rate work permit progressive tax vero.fi tax card registration "
        "tax number foreign employee Finland verotoimisto"
    ),
    "registration": (
        "DVV Digital Population Data Services Agency municipality registration home municipality "
        "Finnish population register residence permit holder registration Finland"
    ),
}

def _detect_boost_topic(text: str) -> str:
    t = text.lower()
    # Evaluate most specific/targeted topics first to avoid misrouting
    if any(w in t for w in ["permanent", "perm res", "p permit", "pr permit", " pr ", "language skills requirement", "work history requirement"]):
        return "permanent"
    if any(w in t for w in ["citizen", "citizenship", "naturali"]):
        return "citizenship"
    # Benefits before family — kela/benefits keywords should not be overridden by "spouse" in same question
    if any(w in t for w in ["kela", "benefit", "social assistance", "housing allowance", "unemployment allowance", "social security"]):
        return "benefits"
    if any(w in t for w in ["tax", "vero", "income tax", "tax card", "tax rate", "verotus"]):
        return "tax"
    if any(w in t for w in ["dvv", "population register", "home municipality", "municipality register"]):
        return "registration"
    if any(w in t for w in ["work permit", "ttol", "employed person", "salary requirement", "income requirement for work", "specialist permit", "specialist work"]):
        return "work"
    if any(w in t for w in ["family reunif", "family permit", "spouse permit", "family member permit"]):
        return "family"
    if any(w in t for w in ["eu citizen", "eea citizen", "d permit", "permanent right of residence", "right of residence"]):
        return "eu_citizen"
    return ""


# ─────────────────────────────────────────────
# JSON EXTRACTION — robust parser
# Handles: markdown fences, array-wrapped objects,
# trailing commas, and partial output failures.
# ─────────────────────────────────────────────
def _parse_llm_json(raw: str) -> dict:
    """Try multiple strategies to extract a JSON object from LLM output."""
    # Strip markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    # Strategy 1: direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
        # LLM sometimes wraps in an array: [{...}]
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]
    except json.JSONDecodeError:
        pass

    # Strategy 2: find the first {...} block
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: strip trailing commas (common LLM mistake) then retry
    fixed = re.sub(r',\s*([}\]])', r'\1', cleaned)
    try:
        result = json.loads(fixed)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Could not extract JSON from LLM output: {cleaned[:300]}")


# ─────────────────────────────────────────────
# MULTI-QUERY RETRIEVAL
# Decomposes complex multi-aspect questions into focused sub-queries,
# retrieves for each, then merges and deduplicates results.
# Single-topic questions return a 1-item array and behave identically
# to the old single-query retrieval.
# ─────────────────────────────────────────────
def _multi_query_retrieve(query: str) -> list:
    try:
        resp = llm_fast.invoke([
            {"role": "system", "content": MULTI_QUERY_SYSTEM},
            {"role": "user",   "content": query},
        ])
        raw_sq = resp.content.strip()
        # Strip fences if model wraps in ```json
        raw_sq = re.sub(r"^```(?:json)?\s*\n?", "", raw_sq, flags=re.MULTILINE)
        raw_sq = re.sub(r"\n?```\s*$", "", raw_sq, flags=re.MULTILINE).strip()
        sub_qs = json.loads(raw_sq)
        if not isinstance(sub_qs, list):
            sub_qs = [query]
    except Exception as e:
        print(f"[DEBUG] Multi-query decomposition failed: {e}")
        sub_qs = [query]

    sub_qs = [q for q in sub_qs if isinstance(q, str) and q.strip()][:3] or [query]
    print(f"[DEBUG] Sub-queries: {sub_qs}")

    seen, all_docs = set(), []
    # Allocate chunks fairly across sub-queries, minimum 4 per query
    per_k = max(4, TOP_K // len(sub_qs))

    for sq in sub_qs:
        try:
            docs = vectorstore.max_marginal_relevance_search(
                sq, k=per_k, fetch_k=FETCH_K, lambda_mult=DIVERSITY
            )
            for doc in docs:
                # Deduplicate by first 120 chars of content
                key = doc.page_content[:120]
                if key not in seen:
                    seen.add(key)
                    all_docs.append(doc)
        except Exception as e:
            print(f"[DEBUG] Sub-query retrieval error ({sq!r}): {e}")

    return all_docs


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _to_lc_history(chat_history: list) -> list:
    """Convert list of {role, content} dicts to LangChain message objects."""
    msgs = []
    for m in chat_history:
        role    = m.get("role", "")
        content = m.get("content", "")
        if role in ("human", "user"):
            msgs.append(HumanMessage(content=content))
        elif role in ("ai", "assistant"):
            msgs.append(AIMessage(content=content))
    return msgs


def _format_context(docs: list) -> str:
    """Format retrieved Document objects as XML chunks for the system prompt."""
    if not docs:
        return "<context>No relevant chunks retrieved.</context>"
    parts = []
    for i, doc in enumerate(docs, 1):
        meta   = doc.metadata if hasattr(doc, "metadata") else {}
        url    = meta.get("source", meta.get("url", "unknown"))
        domain = meta.get("domain", "").upper()
        title  = meta.get("title", "")
        text   = doc.page_content.strip()
        parts.append(
            f'<chunk index="{i}" url="{url}" domain="{domain}" title="{title}">\n'
            f'{text}\n'
            f'</chunk>'
        )
    return "\n\n".join(parts)


def _extract_all_sources(docs: list) -> list:
    """Build deduplicated source metadata list from retrieved docs."""
    seen    = set()
    sources = []
    for doc in docs:
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        url  = meta.get("source", meta.get("url", ""))
        if url and url not in seen:
            seen.add(url)
            sources.append({
                "url":      url,
                "title":    meta.get("title", url),
                "domain":   meta.get("domain", "").upper(),
                "category": meta.get("permit_category", ""),
            })
    return sources


# ─────────────────────────────────────────────
# CONFIDENCE CHECK
# ─────────────────────────────────────────────
def check_confidence(query: str) -> bool:
    try:
        results = vectorstore.similarity_search_with_relevance_scores(query, k=1)
        if not results:
            return True
        _, score = results[0]
        print(f"[DEBUG] Top relevance score: {score:.4f}")
        return score < CONF_THRESHOLD
    except Exception as e:
        print(f"[DEBUG] Confidence check error: {e}")
        return False


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
def log_entry(
    question:      str,
    standalone:    str,
    answer:        str,
    sources:       list,
    category:      str,
    low_conf:      bool,
    session_facts: str  = "",
    follow_ups:    list = None,
    feedback:      str  = "",
):
    log_file = LOG_DIR / f"session_{datetime.now().strftime('%Y%m%d')}.jsonl"
    entry = {
        "timestamp":     datetime.now().isoformat(),
        "question":      question,
        "standalone":    standalone,
        "session_facts": session_facts,
        "answer":        answer,
        "sources":       [s.get("url", "") for s in sources],
        "category":      category,
        "low_conf":      low_conf,
        "follow_ups":    follow_ups or [],
        "feedback":      feedback,
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[LOG ERROR] {e}")


# ─────────────────────────────────────────────
# MAIN ask() FUNCTION
# ─────────────────────────────────────────────
def ask(question: str, chat_history: list = None) -> dict:
    if chat_history is None:
        chat_history = []

    def _early_return(answer_text: str, cat: str = "general") -> dict:
        updated = chat_history + [
            {"role": "human", "content": question},
            {"role": "ai",    "content": answer_text},
        ]
        return {
            "answer":       answer_text,
            "sources":      [],
            "category":     cat,
            "low_conf":     False,
            "standalone":   question,
            "chat_history": updated,
            "follow_ups":   [],
        }

    # ── Pre-filter: too vague ────────────────
    if is_too_vague(question):
        return _early_return(
            "Could you give me a bit more detail? The more context you share — "
            "such as your current permit type, how long you have been in Finland, "
            "and what you are trying to do — the more accurate my answer will be."
        )

    # ── Pre-filter: off topic ────────────────
    off_topic, _ = check_off_topic(question)
    if off_topic:
        return _early_return(OUT_OF_SCOPE_REPLY)

    # ── Contextualize: rewrite follow-ups to standalone queries ──
    standalone = question
    recent     = chat_history[-(MAX_HISTORY_TURNS * 2):]
    lc_history = _to_lc_history(recent)

    if lc_history:
        try:
            ctx_chain  = CONTEXTUALIZE_PROMPT | llm_fast
            standalone = ctx_chain.invoke({
                "chat_history": lc_history,
                "question":     question,
            }).content.strip()
            print(f"[DEBUG] Standalone query: {standalone!r}")
        except Exception as e:
            print(f"[DEBUG] Contextualize error: {e}")
            standalone = question

    # ── Session context enrichment ───────────
    session_facts  = extract_session_facts(chat_history)
    enriched_query = f"{standalone} {session_facts}".strip() if session_facts else standalone
    print(f"[DEBUG] Enriched query: {enriched_query!r}")

    # ── Confidence check (separate fast lookup) ───────────
    low_conf = check_confidence(enriched_query)

    # ── Multi-query retrieval ─────────────────
    # Decomposes complex questions into focused sub-queries, merges results.
    # For simple questions the decomposer returns a 1-item array — no extra cost.
    try:
        docs = _multi_query_retrieve(enriched_query)
    except Exception as e:
        print(f"[DEBUG] Multi-query retrieval error: {e}")
        docs = []

    # ── Topic boost retrieval ─────────────────
    # Ensures specific requirement chunks (language level, income thresholds,
    # years of residence) are always present for key topic areas.
    boost_topic = _detect_boost_topic(question) or _detect_boost_topic(standalone)
    if boost_topic and boost_topic in TOPIC_BOOST:
        try:
            boost_query = TOPIC_BOOST[boost_topic]
            boost_docs  = vectorstore.similarity_search(boost_query, k=BOOST_K)
            existing    = {d.page_content for d in docs}
            for bd in boost_docs:
                if bd.page_content not in existing:
                    docs.append(bd)
                    existing.add(bd.page_content)
            print(f"[DEBUG] Topic boost ({boost_topic}): added up to {BOOST_K} extra chunks")
        except Exception as e:
            print(f"[DEBUG] Boost retrieval error: {e}")

    # ── Format context ────────────────────────
    context_str = _format_context(docs)
    all_sources = _extract_all_sources(docs)

    # ── Build message list for LLM ────────────
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{context}", context_str)}
    ]
    for msg in lc_history:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user",      "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})
    messages.append({"role": "user", "content": question})

    # ── LLM call ─────────────────────────────
    raw    = ""
    parsed = {}
    try:
        response = llm.invoke(messages)
        raw      = response.content.strip()
        parsed   = _parse_llm_json(raw)
    except ValueError as e:
        # JSON extraction failed — raw text is not valid JSON.
        # Use raw as answer ONLY if it looks like human-readable text (not JSON).
        raw_str = str(e)
        fallback_text = raw if raw and not raw.lstrip().startswith(("{", "[", "`")) else ""
        print(f"[DEBUG] JSON parse failed. Raw output:\n{raw[:300]}")
        parsed = {
            "answer":     fallback_text or "An error occurred processing the response. Please try again.",
            "category":   detect_category(question),
            "cited_urls": [],
            "follow_ups": [],
        }
    except Exception as e:
        print(f"[DEBUG] LLM call failed: {e}")
        parsed = {
            "answer":     "Something went wrong on my end. Please try your question again.",
            "category":   "general",
            "cited_urls": [],
            "follow_ups": [],
        }

    # ── Parse structured output ───────────────
    answer     = parsed.get("answer",     "").strip()
    category   = parsed.get("category",   "general").strip()
    cited_urls = set(parsed.get("cited_urls", []))
    follow_ups = [f.strip() for f in parsed.get("follow_ups", []) if f.strip()][:2]

    # Sanitize: if answer is still JSON-like (parse failed gracefully but returned JSON),
    # replace it with a generic error rather than exposing raw JSON in the chat.
    if answer.lstrip().startswith(("{", "[")) and len(answer) > 50:
        print(f"[DEBUG] Answer looks like raw JSON — replacing with error message")
        answer = "Something went wrong processing this response. Please try again."
        category = "general"

    # ── Filter sources to cited-only ──────────
    sources = [s for s in all_sources if s["url"] in cited_urls]
    if not sources and all_sources:
        sources = all_sources[:2]

    # ── Update conversation history ───────────
    updated_history = chat_history + [
        {"role": "human", "content": question},
        {"role": "ai",    "content": answer},
    ]

    print(f"\n{'─'*60}")
    print(f"[ANSWER]   {answer[:200]}{'...' if len(answer) > 200 else ''}")
    print(f"[CATEGORY] {category}  |  [LOW_CONF] {low_conf}")
    print(f"[SOURCES]  {[s['url'] for s in sources]}")
    print(f"{'─'*60}\n")

    log_entry(
        question, standalone, answer, sources,
        category, low_conf, session_facts, follow_ups, "",
    )

    return {
        "answer":       answer,
        "sources":      sources,
        "category":     category,
        "low_conf":     low_conf,
        "standalone":   standalone,
        "chat_history": updated_history,
        "follow_ups":   follow_ups,
    }
