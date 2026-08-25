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
CONF_THRESHOLD    = 0.18    # relevance score below this triggers low-confidence warning
BOOST_K           = 4       # extra chunks added for topic-boosted queries
MAX_HISTORY_TURNS = 6       # conversation turns passed to query rewrite step
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# MODELS & VECTORSTORE
# ─────────────────────────────────────────────
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

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
                    rem_vecs = candidate_vecs[remaining]
                    # Cosine similarity of every remaining candidate against every
                    # already-selected doc, then the max per candidate.
                    #
                    # The division must run on the full (r, s) matrix BEFORE the max.
                    # Taking .max(axis=1) on the numerator first left an (r,) array
                    # over an (r, 1) denominator, which broadcast to (r, r); the
                    # flattened np.argmax below then returned an index far outside
                    # `remaining` and raised IndexError on every call with k >= 2.
                    denom = (
                        np.linalg.norm(rem_vecs, axis=1)[:, None]
                        * np.linalg.norm(sel_vecs, axis=1)[None, :]
                        + 1e-9
                    )
                    red_sims = ((rem_vecs @ sel_vecs.T) / denom).max(axis=1)
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
llm      = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────
CONTEXTUALIZE_SYSTEM = (
    "You rewrite questions for a Finnish immigration assistant into clean, formal English search queries. "
    "Step 1: If the message is in any language other than English (Finnish, Arabic, Somali, Russian, etc.), translate it to English first. "
    "Step 2: Fix all typos, grammar errors, and informal or broken English. "
    "Step 3: Expand common abbreviations — RP or rp = residence permit, WP or wp = work permit, EP or ep = employer/work permit, PR or pr = permanent residence, B-permit = B residence permit, A-permit = A residence permit, D-permit = D long-term EU residence permit. "
    "Step 4: Produce a single self-contained search query in clear English that includes all relevant personal context from the conversation history "
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
You are MigriGuide, an AI assistant answering Finnish immigration questions exclusively from official source chunks provided below. Never use your own training knowledge about Finnish immigration law — only what the chunks say.

RULES:

1. SOURCE CONSTRAINT: Answer using ONLY the provided context chunks. If your training knowledge conflicts with a chunk, follow the chunk. If chunks conflict with each other, flag it as described in the Contradictions rule below.

2. DEFLECTION — LAST RESORT ONLY: Use the deflection phrase only when EVERY SINGLE retrieved chunk is entirely unrelated to any Finnish immigration topic. This bar is extremely high and almost never met in practice.

   If ANY chunk addresses any part of the question (even partially, even for a related permit type, even a general rule that could apply), synthesize from it, state what remains uncertain, and point to the relevant official source. This is your primary job — synthesise, do not deflect.

   SALARY AND INCOME QUESTIONS: Always attempt an answer. If chunks describe the framework (e.g. "must meet the collective agreement for your field") but do not quote the exact figure, explain the framework, calculate from the user's stated numbers if provided, and direct to migri.fi for the specific threshold. Never give a bare "I don't have enough information" response for salary questions — it is far more useful to explain what IS known.

   BROAD OVERVIEW QUESTIONS ("what permits exist in Finland", "what visa do I need", "what are the requirements"): List every permit type, requirement, or process found across ALL retrieved chunks even if no single chunk covers the full picture. A partial answer is always better than deflecting.

   FINANCIAL AND DOCUMENT QUESTIONS: Income requirements, salary thresholds, financial sufficiency, required documents, fees, and processing costs for any permit or benefit are always within scope. Answer from the chunks even if only partially covered.

   INFORMAL ENGLISH AND TYPOS: Real users write from mobile phones. Interpret charitably — "recidence" = residence, "salry requiremnets" = salary requirements, "cityzenship" = citizenship, "how long visa" = how long does the permit last, "visa for living" = residence permit. Answer if any related chunk exists.

   Deflection phrase (use ONLY when every single chunk is truly unrelated to immigration): "I don't have enough official information on this. Please check migri.fi or call Migri: 0295 419 700 (weekdays 8:00–16:00)."

3. PERSONALIZATION: When the user describes their situation (permit type, years in Finland, education, employment, language score, income, goals), apply retrieved requirements directly to their case. Reason explicitly: "Based on what you've told me — [X] — you qualify under [Y] because [Z]." Confirm requirements that are met. State clearly when a requirement is unmet or uncertain. Never list all generic paths when the user's stated situation narrows it to one.

4. CORRECT WRONG ASSUMPTIONS: If the user states an incorrect fact — a wrong threshold, a non-existent exemption, a misconception about a rule — correct it explicitly before answering: "The [figure/exemption] you mentioned does not appear in official sources. According to [Migri/Kela/Vero], the actual requirement is [X]." Never silently work around a wrong assumption or confirm it by omission.

5. THRESHOLDS: Always quote specific thresholds verbatim when present in chunks — language levels (A2, B1, B2), income amounts, years of residence, fees, grace periods. These are what users need most. Never omit, round, or soften them.

   CRITICAL ANTI-HALLUCINATION: Never state a specific EUR income threshold unless that exact figure appears verbatim in a retrieved chunk. If chunks reference an income requirement but do not quote the amount (e.g. "must meet the collective agreement minimum for your field"), state that accurately — do not substitute a figure from your training data. If no threshold is quoted in the chunks, say "the exact threshold is not in my sources — check migri.fi" rather than inventing a number.

   CALCULATIONS: When a user provides specific numbers (hours/week, hourly rate, annual salary, savings balance), calculate their relevant monthly or annual figure and show the working concisely — e.g. "20h × €16/h × 4.33 weeks = approximately €1,386/month gross". Then compare that figure against any threshold quoted verbatim in a retrieved chunk. If no chunk quotes the specific threshold, state the calculated income and direct to migri.fi for threshold confirmation. This is always more useful than deflecting.

6. COMPLETENESS: Scan ALL chunks before composing your answer. Lower-ranked chunks often contain the specific document requirement, grace period, or threshold the user needs. Do not stop at the first relevant chunk.

7. MULTIPLE PATHS: If multiple application paths exist, list all clearly. State which path applies to the user's stated situation. Do not present only the most common path.

8. MIXED QUESTIONS: When a message contains both immigration questions and non-immigration questions (weather, pet import, neighbourhood advice, medical advice, requests to fill in forms), answer ALL immigration parts fully first. Then add exactly one sentence at the end: "Note: the [topic] question is outside MigriGuide's scope." Never discard valid immigration questions because the same message also contains off-topic content.

9. SCOPE — READ CAREFULLY: Use the out-of-scope response ONLY when the ENTIRE message contains no Finnish immigration question whatsoever. The following are ALWAYS in scope: dual citizenship, right to hold two passports, passport and ID card applications in Finland, driving licence exchange for foreign licence holders, customs rules when moving to Finland, worker rights and employment contracts for permit holders, spouse or family member of a Finnish citizen applying for a permit, EU citizen residence rights in Finland, family reunification, appeals against Migri decisions, permit transitions, language requirements, DVV registration, Kela eligibility, Vero tax obligations.

   SOCIAL NICETIES (thank you, thanks, great, hello, goodbye, you're welcome, ok, etc.): Respond briefly and warmly — e.g. "You're welcome! Feel free to ask if you have more questions about Finnish immigration." Do NOT use the out-of-scope response for these.

   PASSPORT QUESTIONS: "Finnish passport" or "requirements for passport" is ambiguous — the user may mean (a) applying for a Finnish passport as a Finnish citizen (handled by police, poliisi.fi) or (b) getting a residence permit to live in Finland. Use response_type "ambiguous" and ask which situation they mean before answering.

   IMPORTANT DISTINCTION: Short Schengen tourist visit (max 90 days) vs. long-term family reunification permit — both are in scope. Clarify which the user means.

   Out-of-scope response (use ONLY for genuinely unrelated topics like sports, cooking, weather): "I specialise in Finnish immigration — permits, Kela benefits, DVV registration, and tax. Feel free to ask me anything about those topics!"

10. SOURCE ROUTING: When directing users to verify details, name the most relevant official source:
    - Tax, income tax, tax card, verokortti → vero.fi
    - Kela benefits, social assistance, housing allowance, unemployment → kela.fi or Kela: 020 634 0000
    - DVV registration, population register, home municipality, personal identity code → dvv.fi
    - Passport, ID card, alien's passport, refugee travel document, driving licence exchange → poliisi.fi or Finnish Police: 0295 419 800
    - Customs, moving belongings to Finland, vehicle/pet import → tulli.fi
    - Worker rights, employment contracts, minimum wage, foreign employee rights → tyosuojelu.fi
    - All permit, citizenship, asylum, residence questions → migri.fi or Migri: 0295 419 700 (weekdays 8:00–16:00)

11. FORMAT: Numbered list for 3 or more distinct requirements or steps. Plain prose for 1–2 items. No bullet points. No markdown formatting of any kind inside the answer field — no bold (**text**), no italic (*text*), no headers (## text), no code blocks. Plain text only.

12. LANGUAGE: Respond in the same language the user used. If they wrote in Punjabi, respond in Punjabi. If Arabic, respond in Arabic. If Finnish, respond in Finnish. If English, respond in English. The knowledge base is in English but your response must match the user's language. Keep it direct and clear with no legal jargon or unexplained abbreviations.

13. ATTRIBUTION AND ADVICE: Match attribution to the chunk source — "According to Migri...", "Kela states...", "According to the Finnish Tax Administration...". Never say "you should", "it is advisable to", "we recommend", "your next steps are", or "I suggest". State what official sources require — do not reframe requirements as personal advice.

14. CONTRADICTIONS: Use this ONLY when two chunks make directly contradictory statements about the exact same specific fact (e.g. two different years-of-residence numbers for the same permit path). Do NOT use it when sources describe different but related programs, statuses, or permit categories — in that case, explain the distinction between them. Response: "Note: official sources differ on this point — check migri.fi for the current rule."

15. JOB LOSS: When the user mentions losing their job, being fired, laid off, or employer bankruptcy, focus your answer on the chunks that describe: (a) the grace period to find a new employer before the permit lapses, (b) whether the user must notify Migri and by when, (c) whether the permit is employer-tied (TTOL-type work permit) or not (A permit, startup permit). These are the facts the user urgently needs. State the grace period duration explicitly and precisely: a TTOL employer-tied work permit gives 3 months to find a new employer; a continuous A permit gives 6 months. If the user has not stated their permit type, state both and ask which applies. Do not say "look for a new job" without also stating whether and how long the current permit remains valid.

16. CONFIRMED FACTS — NO HEDGING: When a retrieved chunk directly and unambiguously states a rule, threshold, or requirement, state it confidently and directly. Do not use "may", "might", "could", "typically", "usually", or "if confirmed" when the chunk itself is unambiguous. Example: if a chunk says "a gap of less than 2 years does not break continuity", say that directly — not "a gap of less than 2 years may not break continuity". Reserve hedging language only for situations where chunks genuinely conflict, or where the rule explicitly depends on individual circumstances not stated by the user.

17. NO PADDING: Every sentence must be directly supported by a retrieved chunk. Never add: bank account tips, language course suggestions, neighbourhood advice, "open a Finnish bank account", "consider language learning", or any lifestyle guidance. Never end with a "next steps", "what to do now", "your action items", or "in summary" section. End the answer after addressing all parts of the question. If a chunk does not say it, do not include it.

18. CITATIONS: In cited_urls, include the URL of every chunk that contributed any fact, threshold, condition, or process step to your answer. Be thorough. Never fabricate URLs.

20. INTEGRATION REQUIREMENTS: When chunks state integration requirements (language level, work history, years of residence) for permanent residence or citizenship, always include those specifics. They are the core of what users are asking.

   CONTINUOUS RESIDENCE CALCULATION: For the 4-year continuous residence requirement for a permanent permit, ALL types of A-permit count — work permits, student permits, family permits, researcher permits. They all accumulate toward the total. When a user gives you a sequence of permit years, ADD them up first. Only tell a user they fall short if the total is genuinely under 4 years. Do NOT say a mixed history disqualifies them unless a chunk explicitly says a specific permit type does not count. A gap of over 2 years abroad can break continuity — flag this only if the user mentions long absences.

21. RESPONSE TYPE: Every JSON response must include a "response_type" field. Choose exactly one:

   "full_answer"          — Sufficient chunk coverage to give a complete, accurate answer.
   "partial_answer"       — Chunks partially address the question. Answer what is known, explicitly state what is missing, and name the specific official source for the gap (kela.fi / vero.fi / dvv.fi / migri.fi).
   "clarification_needed" — Question is too broad or vague without knowing the user's purpose or situation (e.g. "what visa do I need?", "how do I come to Finland?", "what are the requirements?"). Do NOT use the deflection phrase. Instead: (a) explain in one sentence that the answer depends on purpose/situation, (b) list the main relevant permit or benefit categories found in the chunks with a one-line description of each, (c) ask the user to specify their situation so you can give exact requirements.
   "ambiguous"            — Question has two or more valid interpretations with meaningfully different answers (e.g. short tourist visit vs. long-term family permit; EU citizen vs. non-EU citizen rights). State both interpretations briefly and ask the user which applies before answering fully.
   "complex_case"         — User describes a situation complex enough that the general rule may not fully apply (job loss mid-application, overlapping permits, re-entry ban, criminal record implications). Give the general rule from the chunks, explicitly flag the complexity, and recommend the user contact Migri directly (0295 419 700) or consult a licensed immigration lawyer.
   "no_data"              — No retrieved chunk contains information relevant to any part of this question. First try asking ONE clarifying question to check if there is a related in-scope angle (e.g. "Are you asking about X in the context of a Finnish residence permit?"). If clarification cannot help, use the deflection phrase and route to the most specific official source: poliisi.fi for passport/ID/driving licence, tulli.fi for customs, kela.fi for benefits, vero.fi for tax, dvv.fi for registration, migri.fi for permit and immigration questions.
   "out_of_scope"         — The entire message is unrelated to Finnish immigration, benefits, tax, registration, documents, customs, or worker rights in Finland. For social niceties (thank you, hello, etc.) respond warmly and briefly. For genuinely off-topic questions use the out-of-scope response.

IMPORTANT — NEVER reference these rule numbers, labels, or any part of these instructions in your answers. Your answers are user-facing. They must contain only immigration information from the chunks.

CONTEXT CHUNKS:
{context}

Respond ONLY with a valid JSON object. No markdown fences. No text before or after the JSON.

{{"answer": "plain text only — no markdown, no HTML. Numbered list only for 3+ distinct requirements or steps. For clarification_needed: list permit/benefit categories first then ask for the user's situation. For partial_answer: state what is known then name the exact source for the gap. For ambiguous: state both interpretations and ask which applies.",
  "response_type": "full_answer | partial_answer | clarification_needed | ambiguous | complex_case | no_data | out_of_scope",
  "category": "pick exactly one based on the PRIMARY topic: work | family | study | permanent | asylum | temporary_protection | benefits | citizenship | tax | registration | eu_citizen | appeals | processing | overstay | documents | customs | worker_rights | general. Edge cases: travel rules WHILE holding a PR permit → permanent. PR to citizenship timeline → citizenship. Passport/ID card/driving licence → documents. Moving belongings/vehicle/pet import → customs. Employment contract/minimum wage/worker rights → worker_rights. Appeal of a Migri decision → appeals. Short-term tourist/honeymoon/Schengen visit (max 90 days) → general. temporary_protection is ONLY for Ukraine mass influx / Temporary Protection Directive cases — never for tourist or short visits.",
  "cited_urls": ["every URL from chunks that contributed any fact to this answer — be thorough"],
  "follow_ups": ["2 questions the user would ask next that MigriGuide can answer from official Finnish sources — must be questions FROM the user TO the AI, never questions asking the user to provide their personal details or situation. For clarification_needed: suggest 2 specific sub-topic questions the user can ask (e.g. 'What are the requirements for a Finnish work permit?'). For no_data or out_of_scope: suggest 2 related immigration questions MigriGuide can answer."]
}}"""

# ─────────────────────────────────────────────
# CONSTANTS  (exported for use by api/main.py)
# ─────────────────────────────────────────────
OUT_OF_SCOPE_REPLY = (
    "I specialise in Finnish immigration — residence permits, Kela benefits, "
    "DVV registration, tax, and related topics for people living in or moving to Finland. "
    "Feel free to ask me anything about those!"
)

# ─────────────────────────────────────────────
# OFF-TOPIC & VAGUE CHECKS
# ─────────────────────────────────────────────
OFF_TOPIC_KEYWORDS = [
    "recipe", "weather", "football", "sport", "stock market", "crypto",
    "movie", "music", "song", "dating", "relationship advice",
    "hotel", "restaurant recommendation", "flight booking", "tourism",
]

# If a message contains ANY of these terms it is partially immigration-related.
# The LLM (Rule 8) will answer the immigration parts and decline the rest.
# Never pre-filter a message that has immigration content — only pure off-topic.
_IMMIGRATION_SIGNALS = {
    "permit", "visa", "residence", "migri", "kela", "dvv", "vero",
    "citizenship", "citizen", "naturali", "passport", "work permit",
    "family", "reunification", "asylum", "refugee", "registration",
    "benefit", "allowance", "tax card", "income", "salary", "employer",
    "permanent", "temporary", "student permit", "startup", "entrepreneur",
    "eu citizen", "eea", "freedom of movement", "right of residence",
    "spouse", "dual", "appeal", "processing", "application", "migrate",
    "immigration", "immigrant", "foreign", "finland", "finnish",
    "a permit", "b permit", "d permit", "ttol", "enter finland",
    # Hyphenated permit abbreviations (mobile users)
    "b-permit", "a-permit", "d-permit",
    # Standalone abbreviations (space-bounded to avoid false matches like "report")
    " rp ", " wp ", " ep ",
    # Finnish language term for residence permit
    "oleskelulupa",
    # Job loss — affects permit validity, must reach LLM
    "lost my job", "lost job", "fired from", "laid off", "job loss",
    "employer bankrupt", "employer closed", "company closed",
    # Expired permit / overstay signals
    "permit expired", "expired permit", "permit has expired",
    "grace period", "overstay", "after expiry", "permit ran out",
    # Police / documents signals
    "passport", "driving licence", "driving license", "driver's license",
    "identity card", "id card", "alien's passport", "travel document",
    "poliisi", "police finland",
    # Customs signals
    "customs", "tulli", "import", "moving my belongings", "bring my car",
    # Worker rights signals
    "worker rights", "employment contract", "minimum wage", "work rights",
    "tyosuojelu", "occupational safety",
}

def check_off_topic(question: str) -> tuple:
    q = question.lower()
    # If the message contains any immigration signal, pass it to the LLM.
    # Rule 8 in the system prompt handles mixed immigration + off-topic messages.
    if any(signal in q for signal in _IMMIGRATION_SIGNALS):
        return False, ""
    # Pure off-topic: no immigration content at all
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in q:
            print(f"[DEBUG] Off-topic keyword fired: {kw!r}")
            return True, kw
    return False, ""

def is_too_vague(question: str) -> bool:
    return len(question.strip().split()) < 2


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

    # Normalise hyphenated permit forms so "b-permit" matches "b permit" checks
    human_text_norm = human_text.replace("-permit", " permit").replace("-visa", " visa")

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
        if key in human_text_norm:
            facts.append(label)
            break

    if any(w in human_text for w in ["lost my job", "lost job", "fired", "laid off", "job loss", "employer bankrupt", "employer closed", "company closed", "terminated", "no longer employed"]):
        facts.append("recently lost employment in Finland")

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
        "permanent residence permit requirements language skills A2 Finnish Swedish "
        "period of residence years continuous A permit B permit work history integration "
        "documents required application proof language skills YKI test diploma certificate "
        "accepted evidence language proficiency permanent residence application documents list"
    ),
    "citizenship": (
        "Finnish citizenship naturalization requirements years of residence language test "
        "conditions income integration declaration dual citizenship two passports "
        "documents proof language skills YKI certificate B1 B2 accepted test results "
        "continuous residence gap absence criminal record citizenship application process"
    ),
    "work": (
        "work permit requirements employer employee salary income requirement TTOL "
        "employed person collective agreement minimum wage specialist permit "
        "job loss employer bankruptcy grace period find new job work permit "
        "freelance side work permit tied employer field of employment "
        "extend residence permit renewal work permit employed worker permanent contract "
        "workplace change temporary layoff renovation employment interrupted extend permit "
        "fringe benefits salary assessment maximum 50 percent company car accommodation "
        "overtime supplements excluded assessed salary evening night work supplement "
        "salary fringe benefit taxable value calculation work permit salary assessment"
    ),
    "travel": (
        "travel abroad while residence permit application pending Finland "
        "travel permission letter Migri pending application travel abroad EU countries "
        "can I travel while waiting for permit decision Finland visa pending travel "
        "travel document while application under process Finland leave country re-entry "
        "permission to travel Migri letter pending application visit another country"
    ),
    "family": (
        "family reunification requirements sponsor income financial resources documents "
        "spouse child parent residence permit Finland family member permit "
        "income requirement family reunification sponsor financial sufficiency"
    ),
    "eu_citizen": (
        "EU citizen permanent right of residence D permit five years registration "
        "right of residence family member EU free movement spouse EU citizen "
        "residence card family member EU citizen mandatory declaratory "
        "non-EU spouse EU citizen Finland residence rights"
    ),
    "benefits": (
        "Kela benefits eligibility residence permit B permit A permit permanent "
        "social assistance housing allowance unemployment entitlement Finland "
        "child benefit perhe-etuudet entrepreneur income irregular Kela assessment "
        "basic unemployment allowance social assistance eligibility permit type"
    ),
    "tax": (
        "Finland income tax rate work permit progressive tax vero.fi tax card registration "
        "tax number foreign employee Finland tax at source arrangement flat rate "
        "progressive tax brackets income levels Finland foreign specialist tax"
    ),
    "registration": (
        "DVV Digital Population Data Services Agency municipality registration home municipality "
        "Finnish population register residence permit holder registration Finland "
        "register address Finland new resident steps first arrival registration process"
    ),
    "appeals": (
        "appeal Migri decision negative decision administrative court hallinto-oikeus "
        "objection deadline appeal process refused application steps timeline"
    ),
    "processing": (
        "application processing time Finland Migri residence permit how long wait "
        "processing time work permit family permit student permit days weeks months "
        "fast track processing priority processing status check Migri application status "
        "how long does it take permit application decision waiting period"
    ),
    "overstay": (
        "permit expired overstay Finland grace period consequences expired residence permit "
        "leaving Finland voluntarily deportation removal illegal stay fine criminal record "
        "what to do if permit expires extend before expiry apply new permit grace period "
        "expired permit reapply re-entry ban consequences overstaying Finland voluntary departure"
    ),
    "documents": (
        "passport application Finland Finnish passport requirements poliisi police "
        "identity card ID card application alien's passport refugee travel document "
        "driving licence exchange foreign driving licence Finland convert driving licence "
        "passport for Finnish citizen requirements documents police service"
    ),
    "customs": (
        "moving to Finland customs household goods import duty-free personal belongings "
        "importing vehicle car Finland customs tulli pet import Finland bringing dog cat "
        "goods private use Finland moving belongings import rules"
    ),
    "worker_rights": (
        "employment contract Finland worker rights foreign employee minimum wage "
        "working hours overtime collective agreement tyosuojelu occupational safety "
        "employer obligations foreign worker rights sent worker Finland discrimination "
        "termination notice period employee rights Finland"
    ),
}

def _detect_boost_topic(text: str) -> str:
    t = text.lower()
    # Ordered from most specific to most general to prevent misrouting
    if any(w in t for w in ["permanent residence", "perm res", "p permit", "pr permit", " pr ", "language skills requirement", "work history requirement", "prove language", "language proof", "language document"]):
        return "permanent"
    if any(w in t for w in ["citizen", "citizenship", "naturali", "dual citizen", "two passport"]):
        return "citizenship"
    if any(w in t for w in ["appeal", "refused", "negative decision", "administrative court", "hallinto"]):
        return "appeals"
    # Benefits checked before family — kela/benefits keywords win over "spouse" in same question
    if any(w in t for w in ["kela", "benefit", "social assistance", "housing allowance", "unemployment allowance", "social security", "child benefit"]):
        return "benefits"
    if any(w in t for w in ["tax", "vero", "income tax", "tax card", "tax rate", "verotus", "tax at source"]):
        return "tax"
    if any(w in t for w in ["dvv", "population register", "home municipality", "municipality register", "register address"]):
        return "registration"
    if any(w in t for w in ["travel", "go abroad", "visit abroad", "leave finland", "other country", "other countr", "eu countr", "permission letter", "travel letter", "visa in process", "application pending", "application in process", "while waiting", "while my", "can i leave", "paris", "london", "abroad"]):
        return "travel"
    if any(w in t for w in ["work permit", "ttol", "employed person", "salary requirement", "income requirement for work", "specialist permit", "specialist work", "collective agreement", "job loss", "employer bankrupt", "extend residence", "extend permit", "renew permit", "renovation", "permanent contract", "permanent work"]):
        return "work"
    if any(w in t for w in ["family reunif", "family permit", "spouse permit", "family member permit", "sponsor income", "bring parent", "parent permit"]):
        return "family"
    if any(w in t for w in ["eu citizen", "eea citizen", "d permit", "permanent right of residence", "right of residence", "residence card eu", "family member eu"]):
        return "eu_citizen"
    if any(w in t for w in ["processing time", "how long does it take", "how long will it take", "how long does the", "waiting for decision", "application status", "check my status", "status of my application", "when will i get", "how long to process"]):
        return "processing"
    if any(w in t for w in ["lost my job", "lost job", "fired", "laid off", "job loss", "employer bankrupt", "employer closed", "company closed", "terminated employment", "no longer employed"]):
        return "work"
    if any(w in t for w in ["permit expired", "expired permit", "permit has expired", "permit ran out", "overstay", "after expiry", "grace period", "permit is expiring", "permit expires soon"]):
        return "overstay"
    if any(w in t for w in ["passport", "identity card", "id card", "alien's passport", "alien passport", "travel document", "driving licence", "driving license", "driver's license", "convert licence", "foreign licence"]):
        return "documents"
    if any(w in t for w in ["customs", "tulli", "moving my belongings", "import my car", "bring my car", "bring my dog", "bring my cat", "pet import", "household goods", "moving goods"]):
        return "customs"
    if any(w in t for w in ["worker rights", "employee rights", "employment contract", "minimum wage", "working hours", "tyosuojelu", "occupational safety", "foreign employee rights", "my employer"]):
        return "worker_rights"
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
            "answer":        answer_text,
            "sources":       [],
            "category":      cat,
            "low_conf":      False,
            "standalone":    question,
            "chat_history":  updated,
            "follow_ups":    [],
            "response_type": "no_data",
        }

    # ── Pre-filter: too vague ────────────────
    if is_too_vague(question):
        return _early_return(
            "Could you give me a bit more detail? The more context you share — "
            "such as your current permit type, how long you have been in Finland, "
            "and what you are trying to do — the more accurate my answer will be."
        )

    # ── Pre-filter: off topic (first turn only) ──────────────────────────────
    # Skip entirely when the conversation is already in progress. Mid-conversation
    # questions are always immigration-contextual — blocking "how much salary do I
    # need per month?" after three turns about permits causes false rejections.
    # api/main.py has the same guard; this is a belt-and-suspenders defence.
    if not chat_history:
        off_topic, _ = check_off_topic(question)
        if off_topic:
            return _early_return(OUT_OF_SCOPE_REPLY)

    # ── Contextualize: rewrite follow-ups to standalone queries ──
    standalone = question
    recent     = chat_history[-(MAX_HISTORY_TURNS * 2):]
    lc_history = _to_lc_history(recent)

    # Always contextualise — even on first turn with no history.
    # Without history the LLM still fixes typos ("recidence"→"residence"),
    # expands abbreviations (rp/wp/ep/pr), and normalises broken English
    # before the query reaches the vectorstore. Skipping this step on first
    # turn was the primary cause of poor retrieval on mobile-typed queries.
    try:
        ctx_chain  = CONTEXTUALIZE_PROMPT | llm_fast
        standalone = ctx_chain.invoke({
            "chat_history": lc_history,   # empty list on first turn — LangChain handles it
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
    # Send the English standalone for retrieval accuracy.
    # Always include the original message so the LLM can match the response language
    # to what the user actually wrote (English stays English, Finnish stays Finnish, etc.)
    user_content = standalone
    if question.strip().lower() != standalone.strip().lower():
        user_content = (
            f"{standalone}\n\n"
            f"[Respond in the SAME language as the user's original message: \"{question}\"]"
        )
    messages.append({"role": "user", "content": user_content})

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
            "answer":        fallback_text or "An error occurred processing the response. Please try again.",
            "category":      detect_category(question),
            "cited_urls":    [],
            "follow_ups":    [],
            "response_type": "no_data",
        }
    except Exception as e:
        print(f"[DEBUG] LLM call failed: {e}")
        parsed = {
            "answer":        "Something went wrong on my end. Please try your question again.",
            "category":      "general",
            "cited_urls":    [],
            "follow_ups":    [],
            "response_type": "no_data",
        }

    # ── Parse structured output ───────────────
    answer        = parsed.get("answer",        "").strip()
    category      = parsed.get("category",      "general").strip()
    response_type = parsed.get("response_type", "full_answer").strip()
    cited_urls    = set(parsed.get("cited_urls", []))
    follow_ups    = [f.strip() for f in parsed.get("follow_ups", []) if f.strip()][:2]

    # Sanitize: if answer is still JSON-like (parse failed gracefully but returned JSON),
    # replace it with a generic error rather than exposing raw JSON in the chat.
    if answer.lstrip().startswith(("{", "[")) and len(answer) > 50:
        print(f"[DEBUG] Answer looks like raw JSON — replacing with error message")
        answer = "Something went wrong processing this response. Please try again."
        category = "general"

    # ── Filter sources to cited-only ──────────
    sources = [s for s in all_sources if s["url"] in cited_urls]
    # Fallback: if LLM cited nothing, surface the top retrieved sources
    if not sources and all_sources:
        sources = all_sources[:4]

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
        "answer":        answer,
        "sources":       sources,
        "category":      category,
        "low_conf":      low_conf,
        "standalone":    standalone,
        "chat_history":  updated_history,
        "follow_ups":    follow_ups,
        "response_type": response_type,
    }
