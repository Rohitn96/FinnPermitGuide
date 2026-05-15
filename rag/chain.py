"""
MigriGuide — RAG Intelligence Layer v2
rag/chain.py

Vectorstore backend is selected by .env:
  USE_PINECONE=true   → Pinecone (production, requires PINECONE_API_KEY + PINECONE_INDEX_NAME)
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
TOP_K             = 10      # chunks returned by MMR retrieval
FETCH_K           = 40      # candidate pool size for MMR
DIVERSITY         = 0.65    # MMR diversity factor (0=max similarity, 1=max diversity)
CONF_THRESHOLD    = 0.25    # relevance score below this triggers low-confidence warning
BOOST_K           = 4       # extra chunks added for topic-boosted queries
MAX_HISTORY_TURNS = 6       # conversation turns passed to query rewrite step
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# MODELS & VECTORSTORE
# Supports both ChromaDB (local) and Pinecone (production).
# Set USE_PINECONE=true in .env to switch to Pinecone.
# ─────────────────────────────────────────────
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

_use_pinecone = os.getenv("USE_PINECONE", "false").lower() == "true"

if _use_pinecone:
    # ── Pinecone: direct SDK integration (langchain-pinecone broken on Py3.14) ──
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
            # Client-side MMR using cosine similarity
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

llm      = ChatOpenAI(model="gpt-4o",      temperature=0)   # main reasoning
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)   # query rewriting only

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

SYSTEM_PROMPT = """\
You are MigriGuide, a Finnish immigration assistant. Answer ONLY from the official source chunks provided below.

RULES:
1. Use ONLY the provided context chunks. Never use your own training knowledge about Finnish immigration law.
2. If no chunk is sufficiently relevant, respond exactly:
   "I don't have enough official information on this. Please check migri.fi or call Migri: 0295 419 700 (weekdays 8:00-16:00)."
3. THRESHOLDS: State specific thresholds (language levels such as A2 or B1, income amounts, years of residence, application fees) ONLY when they appear verbatim in the provided chunks — but when they do appear, always quote them clearly. This information is exactly what users need.
4. If the answer has 3 or more distinct requirements or steps, format them as a numbered list. Otherwise write clear prose.
5. Write plain English — direct and clear, suitable for non-native speakers. No legal jargon. No Latin. No abbreviations without explanation.
6. If two context chunks contradict each other, say: "Note: official sources differ on this point. Check migri.fi for the latest."
7. For questions about processing delays or waiting times, mention Migri's Fast Track service if the context supports it.
8. Attribute claims: "According to Migri..." or "Migri states...". Never give personal legal advice or say "you should".
9. If the question is outside Finnish immigration, residence, registration, benefits, or tax for immigrants, respond:
   "This is outside MigriGuide's scope. I only answer Finnish immigration questions."
10. Scan ALL provided chunks before answering — do not stop at the first relevant one. Lower-ranked chunks often contain the specific threshold or condition the user needs.
11. If multiple application paths exist (e.g. for permanent residence), list all paths clearly — do not present only one.
12. Do not pad answers with unnecessary caveats, disclaimers, or footers. Be concise.
13. Do not repeat the user's question back to them.
14. When a chunk explicitly states integration requirements (language level, work history, years of residence) for permanent residence or citizenship, include those specifics in your answer.

CONTEXT CHUNKS:
{context}

Respond ONLY with a valid JSON object. No markdown fences. No text before or after the JSON.

{{"answer": "your answer here — plain text, no HTML. Use numbered lists only when there are 3+ distinct steps or requirements.",
  "category": "pick exactly one: work | family | study | permanent | asylum | temporary_protection | benefits | citizenship | tax | registration | eu_citizen | appeals | processing | overstay | general",
  "cited_urls": ["list every URL from context chunks that contributed facts to your answer"],
  "follow_ups": ["2 specific, actionable follow-up questions the user is most likely to ask next, based on gaps in the answer or the natural next step in their immigration journey"]
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
# Used only if LLM JSON parse fails
# ─────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "work":                 ["work permit", "ttol", "employee", "employer", "job permit", "employed person", "seasonal work"],
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
# Scans human messages for key personal facts.
# Returns compact string injected into retrieval query.
# No extra API calls — pure keyword scan.
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

    # Current permit type — check most specific first
    permit_checks = [
        ("job search",      "job search permit holder"),
        ("startup permit",  "startup permit holder"),
        ("student permit",  "student residence permit holder"),
        ("work permit",     "work permit holder"),
        ("b permit",        "B permit holder (temporary residence)"),
        ("a permit",        "A permit holder (continuous residence)"),
        ("d permit",        "D permit holder (long-term EU resident)"),
    ]
    for key, label in permit_checks:
        if key in human_text:
            facts.append(label)
            break

    # Education in Finland
    if any(w in human_text for w in ["master", "msc", "bachelor", "degree", "graduated", "thesis", "phd", "doctorate"]):
        facts.append("completed degree in Finland")

    # Employment
    if any(w in human_text for w in ["contract", "60h", "part-time", "full-time", "employed", "working", "job offer"]):
        facts.append("has employment contract in Finland")

    # Goals
    if any(w in human_text for w in ["permanent residence", "pr permit", " pr ", "p permit", "perm res"]):
        facts.append("goal: permanent residence permit")
    if any(w in human_text for w in ["citizen", "citizenship", "naturali"]):
        facts.append("goal: Finnish citizenship")

    return " | ".join(facts)


# ─────────────────────────────────────────────
# TOPIC BOOST QUERIES
# Permanent residence and citizenship questions need supplementary
# retrieval to ensure specific requirement chunks (e.g. language
# level, integration points, years of residence) are always included.
# ─────────────────────────────────────────────
TOPIC_BOOST = {
    # Pulls in the specific sub-pages: language-skills-requirement, period-of-residence, work-history
    "permanent": (
        "permanent residence permit language skills requirement A2 Finnish Swedish "
        "period of residence years continuous work history integration requirement paths"
    ),
    # Pulls citizenship requirements page with language test and years-of-residence conditions
    "citizenship": (
        "Finnish citizenship requirements years of residence language test naturalization "
        "conditions income integration declaration dual citizenship"
    ),
    # Pulls the income-requirement-for-work page with actual salary thresholds
    "work": (
        "work permit requirements employer employee salary income requirement TTOL "
        "employed person collective agreement minimum wage"
    ),
    "family": (
        "family reunification requirements sponsor income financial resources documents "
        "spouse child residence permit Finland"
    ),
    # EU citizen D permit and right of permanent residence
    "eu_citizen": (
        "EU citizen permanent right of residence D permit five years registration "
        "right of residence family member"
    ),
    # Kela benefits eligibility per permit type
    "benefits": (
        "Kela benefits eligibility residence permit B permit A permit permanent "
        "social assistance housing allowance unemployment entitlement"
    ),
}

def _detect_boost_topic(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["permanent", "perm res", "p permit", "pr permit", " pr ", "language skills requirement", "work history requirement"]):
        return "permanent"
    if any(w in t for w in ["citizen", "citizenship", "naturali", "naturali"]):
        return "citizenship"
    if any(w in t for w in ["work permit", "ttol", "employed person", "salary requirement", "income requirement for work"]):
        return "work"
    if any(w in t for w in ["family reunif", "family permit", "spouse permit", "family member permit"]):
        return "family"
    if any(w in t for w in ["eu citizen", "eea citizen", "d permit", "permanent right of residence", "right of residence"]):
        return "eu_citizen"
    if any(w in t for w in ["kela", "benefit", "social assistance", "housing allowance", "unemployment allowance"]):
        return "benefits"
    return ""


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
# Uses relevance scores (0-1, higher = more relevant).
# Returns True (low confidence) if best chunk scores below CONF_THRESHOLD.
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
# Uses stdlib json only — no jsonlines dependency needed.
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

    # ── Uniform early return helper ──────────
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
        return _early_return(
            "This is outside MigriGuide's scope. I can only answer questions "
            "about Finnish immigration, residence permits, registration, and related topics."
        )

    # ── Contextualize: rewrite to standalone query ──
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

    # ── Confidence check ─────────────────────
    low_conf = check_confidence(enriched_query)

    # ── Primary retrieval (MMR) ───────────────
    try:
        docs = vectorstore.max_marginal_relevance_search(
            enriched_query,
            k=TOP_K,
            fetch_k=FETCH_K,
            lambda_mult=DIVERSITY,
        )
    except Exception as e:
        print(f"[DEBUG] Retrieval error: {e}")
        docs = []

    # ── Topic boost retrieval ─────────────────
    # For PR, citizenship, work, family questions: add supplementary chunks
    # so requirement details like language level are always present in context.
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
    # Include recent conversation so LLM maintains thread continuity
    for msg in lc_history:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user",      "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})
    messages.append({"role": "user", "content": question})

    # ── LLM call ─────────────────────────────
    raw = ""
    try:
        response = llm.invoke(messages)
        raw      = response.content.strip()
        # Strip markdown fences if GPT wraps output in ```json ... ```
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\n?```\s*$",           "", raw, flags=re.MULTILINE)
        raw = raw.strip()
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[DEBUG] JSON parse failed. Raw output:\n{raw}")
        # Fallback: use raw text as answer, detect category with keywords
        parsed = {
            "answer":     raw if raw else "An error occurred. Please try again.",
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

    # ── Filter sources to cited-only ──────────
    sources = [s for s in all_sources if s["url"] in cited_urls]
    # Safety fallback: if LLM cited nothing, show top 2
    if not sources and all_sources:
        sources = all_sources[:2]

    # ── Update conversation history ───────────
    updated_history = chat_history + [
        {"role": "human", "content": question},
        {"role": "ai",    "content": answer},
    ]

    # ── Terminal feedback capture ─────────────
    # ── Debug output ──────────────────────────
    
    feedback = ""
    print(f"\n{'─'*60}")
    print(f"[ANSWER]   {answer[:200]}{'...' if len(answer) > 200 else ''}")
    print(f"[CATEGORY] {category}  |  [LOW_CONF] {low_conf}")
    print(f"[SOURCES]  {[s['url'] for s in sources]}")
    print(f"{'─'*60}\n")

    # ── Log ───────────────────────────────────
    log_entry(
        question, standalone, answer, sources,
        category, low_conf, session_facts, follow_ups, feedback,
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