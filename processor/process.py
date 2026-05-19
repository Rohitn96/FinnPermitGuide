"""
MigriGuide - Stage 2: Processing & Chunking
Loads raw scraped data, cleans it, chunks it, auto-tags permit categories,
and saves structured chunks to data/cleaned/all_chunks.json.

permit_category values:
  work | study | family | asylum | permanent | citizenship |
  eu_citizen | processing | benefits | tax | registration |
  employment_services | housing | health | general
"""

import json
import re
import logging
from datetime import date
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
RAW_DIR     = BASE_DIR / "data" / "raw"
CLEANED_DIR = BASE_DIR / "data" / "cleaned"
PAGES_IN    = RAW_DIR / "migri_pages.json"
PDF_IN      = RAW_DIR / "pdf_content.json"
CHUNKS_OUT  = CLEANED_DIR / "all_chunks.json"

CLEANED_DIR.mkdir(parents=True, exist_ok=True)

# ── Chunking config ────────────────────────────────────────────────────────────
# Larger chunks capture full requirement paragraphs without splitting on clause boundaries.
# PDFs (legal text) get extra width so multi-condition requirements stay in one chunk.
CHUNK_SIZE     = 1200   # web pages — up from 700
CHUNK_OVERLAP  = 200    # up from 100
PDF_CHUNK_SIZE    = 1500
PDF_CHUNK_OVERLAP = 300
MIN_TOKENS     = 80   # chunks below this are discarded (nav remnants etc.)

# ── Permit / topic category rules ─────────────────────────────────────────────
# Evaluated in order — first match wins. Keep more specific rules above general.
# Matching runs on: source URL + first 400 chars of chunk text, lowercased.
CATEGORY_RULES: list[tuple[str, list[str]]] = [

    # Immigration permit types — most specific, highest priority
    ("work", [
        "work", "employee", "specialist", "fast-track", "fast track",
        "blue-card", "blue card", "entrepreneur", "startup", "start-up",
        "employer", "job", "employment permit", "work permit",
        "coming-to-finland-for-work", "seasonal work", "self-employed",
        "au pair", "residence-permit-for-an-employee",
    ]),
    ("study", [
        "study", "student", "student permit", "university", "school",
        "researcher", "research permit", "scholarship", "coming-to-finland-to-study",
        "higher education", "vocational", "exchange student",
    ]),
    ("family", [
        "family", "spouse", "child", "parent", "relative",
        "family-member", "family member", "reunification",
        "moving-to-finland-to-be-with", "family-member-of-a-finnish",
        "family-member-of-a-foreign", "family-member-of-an-eu",
        "cohabiting partner", "dependent",
    ]),
    ("asylum", [
        "asylum", "refugee", "protection", "temporary-protection",
        "temporary protection", "humanitarian", "asylum-interview",
        "asylum-decision", "reception service", "asylum seeker",
        "international protection", "stateless",
    ]),
    ("permanent", [
        "permanent", "permanent residence", "permanent-residence-permit",
        "extended-permit", "extended permit", "long-term resident",
        "long term resident", "p-permit", "p permit",
    ]),
    ("citizenship", [
        "citizenship", "naturalisation", "naturalization",
        "applying-for-citizenship", "citizenship-requirements",
        "language requirement for citizenship", "dual citizenship",
        "finnish citizen", "declaration of citizenship",
    ]),
    ("eu_citizen", [
        "eu-citizen", "eu citizen", "registration-of-right",
        "right-of-residence", "eea", "eu national",
        "permanent-right-of-residence", "freedom of movement",
        "union citizen", "nordic citizen",
    ]),

    # Administrative / process topics
    ("processing", [
        "processing-time", "processing time", "processing-fee",
        "processing fee", "fee", "cost", "price list",
        "how long does it take", "application fee",
    ]),
    ("appeals", [
        "appeal", "appealing", "appeal a decision", "administrative court",
        "complaint", "rectification", "reconsideration",
        "withdrawal of residence", "post-decision",
    ]),
    ("application_process", [
        "how to apply", "apply online", "enterfinland",
        "enter finland", "application form", "book an appointment",
        "biometric", "fingerprint", "documents you need",
        "checklist", "checking your case", "application status",
    ]),

    # Life in Finland topics (Kela, DVV, Vero, TE)
    ("benefits", [
        "kela", "benefit", "social security", "allowance", "pension",
        "unemployment benefit", "housing benefit", "basic social assistance",
        "health insurance benefit", "maternity", "parental benefit",
        "child benefit", "entitled to kela",
    ]),
    ("tax", [
        "vero", "tax", "taxation", "tax card", "income tax",
        "tax number", "arriving in finland tax", "tax registration",
        "tax administration", "finnish tax",
    ]),
    ("registration", [
        "dvv", "population register", "home municipality",
        "personal identity code", "hetu", "register personal data",
        "registration of foreign", "municipality of residence",
        "maistraatti", "digital and population",
    ]),
    ("employment_services", [
        "te-palvelut", "te services", "te office", "employment office",
        "job seeker", "integration training", "integration services",
        "employment agency", "public employment", "unemployment register",
        "tyomarkkinatori",
    ]),
    ("documents", [
        "passport", "identity card", "alien's passport", "alien-s-passport",
        "refugee travel document", "travel document", "driving licence",
        "foreign driving", "driving-licence", "poliisi",
    ]),
    ("customs", [
        "tulli", "customs", "moving-to-finland", "import", "vehicle import",
        "pet import", "household goods", "duty-free", "goods for private use",
    ]),
    ("worker_rights", [
        "tyosuojelu", "work-relationship", "foreign-employee", "sent-worker",
        "employment contract", "minimum wage", "working hours", "worker protection",
        "occupational safety", "working conditions",
    ]),
    ("housing", [
        "housing", "apartment", "rent", "rental", "lease",
        "find housing", "housing market", "municipality housing",
        "student housing", "hoas", "deposit",
    ]),
    ("health", [
        "health", "healthcare", "health centre", "doctor", "hospital",
        "health services", "terveyskeskus", "occupational health",
        "private health", "health insurance card", "european health",
    ]),

    # Catch-all — must be last
    ("general", []),
]


def classify_permit(source: str, content: str) -> str:
    """Return the best-fit category for a chunk."""
    haystack = (source + " " + content[:400]).lower()
    for category, keywords in CATEGORY_RULES:
        if not keywords:      # catch-all
            return category
        if any(kw in haystack for kw in keywords):
            return category
    return "general"


# ── Text cleaning ──────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Strip excessive whitespace and blank lines."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def token_estimate(text: str) -> int:
    """Rough token estimate: characters / 4."""
    return len(text) // 4


# ── Source domain helper ───────────────────────────────────────────────────────

def get_domain_tag(source: str) -> str:
    """Return a short tag identifying which authority the source comes from."""
    source = source.lower()
    if "migri.fi" in source:
        return "migri"
    if "enterfinland" in source:
        return "enterfinland"
    if "infofinland" in source:
        return "infofinland"
    if "kela.fi" in source:
        return "kela"
    if "dvv.fi" in source:
        return "dvv"
    if "vero.fi" in source:
        return "vero"
    if "te-palvelut" in source or "te-services" in source or "tyomarkkinatori" in source:
        return "te_services"
    if "workinfinland.eu" in source:
        return "workinfinland"
    if "ihhelsinki" in source:
        return "ihh"
    if "suomi.fi" in source:
        return "suomi"
    if "poliisi.fi" in source:
        return "poliisi"
    if "tulli.fi" in source:
        return "tulli"
    if "tyosuojelu.fi" in source:
        return "tyosuojelu"
    return "pdf" if source.endswith(".pdf") else "other"


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_pages() -> list[dict]:
    if not PAGES_IN.exists():
        log.warning("migri_pages.json not found — run scrape.py first")
        return []
    with open(PAGES_IN, encoding="utf-8") as f:
        pages = json.load(f)
    log.info("Loaded %d web pages", len(pages))
    return pages


def load_pdfs() -> list[dict]:
    if not PDF_IN.exists():
        log.info("pdf_content.json not found — no PDFs to process")
        return []
    with open(PDF_IN, encoding="utf-8") as f:
        pdfs = json.load(f)
    log.info("Loaded %d PDF documents", len(pdfs))
    return pdfs


# ── Processing ─────────────────────────────────────────────────────────────────

PROCESSING_TIMES_URL = "https://migri.fi/en/processing-times"
SCRAPED_DATE         = date.today().isoformat()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)

pdf_splitter = RecursiveCharacterTextSplitter(
    chunk_size=PDF_CHUNK_SIZE,
    chunk_overlap=PDF_CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def process_page(page: dict) -> list[dict]:
    """Split a web page into chunks with full metadata."""
    url     = page.get("url", "")
    title   = page.get("title", "")
    content = clean_text(page.get("content", ""))

    if not content:
        return []

    raw_chunks = splitter.split_text(content)
    chunks = []

    for idx, chunk_text in enumerate(raw_chunks):
        if token_estimate(chunk_text) < MIN_TOKENS:
            log.debug("Dropping short chunk (idx %d) from %s", idx, url)
            continue

        meta = {
            "source":          url,
            "title":           title,
            "type":            "webpage",
            "domain":          get_domain_tag(url),
            "chunk_id":        idx,
            "permit_category": classify_permit(url, chunk_text),
        }

        if PROCESSING_TIMES_URL in url:
            meta["scraped_date"] = SCRAPED_DATE

        chunks.append({"text": chunk_text, "metadata": meta})

    return chunks


def process_pdf(doc: dict) -> list[dict]:
    """Split a PDF document into chunks with full metadata."""
    source  = doc.get("source", "unknown.pdf")
    content = clean_text(doc.get("content", ""))

    if not content:
        return []

    raw_chunks = pdf_splitter.split_text(content)
    chunks = []

    for idx, chunk_text in enumerate(raw_chunks):
        if token_estimate(chunk_text) < MIN_TOKENS:
            log.debug("Dropping short chunk (idx %d) from %s", idx, source)
            continue

        meta = {
            "source":          source,
            "title":           source,
            "type":            "pdf",
            "domain":          "pdf",
            "chunk_id":        idx,
            "permit_category": classify_permit(source, chunk_text),
        }
        chunks.append({"text": chunk_text, "metadata": meta})

    return chunks


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=== MigriGuide Stage 2: Processing & Chunking ===")

    pages = load_pages()
    pdfs  = load_pdfs()

    all_chunks: list[dict] = []

    for page in pages:
        page_chunks = process_page(page)
        all_chunks.extend(page_chunks)
        category = page_chunks[0]["metadata"]["permit_category"] if page_chunks else "—"
        domain   = page_chunks[0]["metadata"]["domain"] if page_chunks else "—"
        log.info(
            "  [%-14s] %-60s → %d chunks",
            domain, page.get("url", "?")[-60:], len(page_chunks),
        )

    for doc in pdfs:
        pdf_chunks = process_pdf(doc)
        all_chunks.extend(pdf_chunks)
        log.info("  [pdf          ] %-60s → %d chunks", doc.get("source", "?"), len(pdf_chunks))

    with open(CHUNKS_OUT, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    # ── Summary ────────────────────────────────────────────────────────────────
    category_counts: dict[str, int] = {}
    domain_counts:   dict[str, int] = {}
    for c in all_chunks:
        cat = c["metadata"]["permit_category"]
        dom = c["metadata"]["domain"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        domain_counts[dom]   = domain_counts.get(dom, 0) + 1

    log.info("=== Stage 2 complete ===")
    log.info("Total chunks : %d  →  %s", len(all_chunks), CHUNKS_OUT)
    log.info("")
    log.info("By permit category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d", cat, count)
    log.info("")
    log.info("By source domain:")
    for dom, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d", dom, count)


if __name__ == "__main__":
    main()
