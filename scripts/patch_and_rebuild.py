"""
MigriGuide — Patch & Rebuild Script
====================================
Run this when you need to:
  (a) add newly identified pages to the knowledge base, OR
  (b) re-process everything with updated chunk settings

What it does, in order:
  1. Fetches ONLY the new URLs not already in migri_pages.json
  2. Appends them to data/raw/migri_pages.json
  3. Re-processes ALL pages + PDFs with improved chunk settings
     (1200 chars / 200 overlap for web, 1500 / 300 for PDFs)
  4. Wipes and rebuilds data/chroma_db/ from scratch

Usage:
    cd migri-assistant
    .venv\\Scripts\\python.exe scripts/patch_and_rebuild.py

Cost estimate: ~$0.03 USD (embedding ~2000-2500 chunks at text-embedding-3-small)
"""

import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Bootstrap ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
PAGES_JSON  = BASE_DIR / "data" / "raw" / "migri_pages.json"
PDF_JSON    = BASE_DIR / "data" / "raw" / "pdf_content.json"
CHUNKS_JSON = BASE_DIR / "data" / "cleaned" / "all_chunks.json"
CHROMA_DIR  = str(BASE_DIR / "data" / "chroma_db")

# ── Chunk settings (improved from original 700/100) ───────────────────────────
WEB_CHUNK_SIZE    = 1200   # captures full requirement paragraphs
WEB_CHUNK_OVERLAP = 200
PDF_CHUNK_SIZE    = 1500   # legal text needs wider context
PDF_CHUNK_OVERLAP = 300
MIN_TOKENS        = 80     # rough: chars / 4

# ── HTTP config ────────────────────────────────────────────────────────────────
REQUEST_DELAY = 1.2   # seconds between requests
TIMEOUT       = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MigriGuide-Bot/1.0; "
        "educational/non-commercial; +https://github.com/Rohitn96/migri-guide)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

NOISE_TAGS = [
    "nav", "footer", "header", "script", "style", "noscript",
    "aside", "form", "button", "iframe", "svg", "figure",
    "cookie-consent", "breadcrumb",
]

# ── NEW URLs to add ────────────────────────────────────────────────────────────
# Only pages NOT in the original scrape.  All verified/attempted against live site.
NEW_URLS = [

    # ── Migri: PR integration requirement sub-pages (linked from PR main page) ─
    # These are the critical missing pages with A2, years, work history thresholds
    "https://migri.fi/en/language-skills-requirement",
    "https://migri.fi/en/period-of-residence-requirement",
    "https://migri.fi/en/work-history-requirement",

    # ── Migri: Citizenship requirement pages ───────────────────────────────────
    "https://migri.fi/en/requirements-for-citizenship",
    "https://migri.fi/en/citizenship-declaration",
    "https://migri.fi/en/dual-citizenship",

    # ── Migri: Work permit income (the page all FAQs reference but was never scraped)
    "https://migri.fi/en/income-requirement-for-persons-who-apply-for-a-residence-permit-on-the-basis-of-work",

    # ── Migri: Permit type overview pages ─────────────────────────────────────
    "https://migri.fi/en/types-of-residence-permits",
    "https://migri.fi/en/continuous-permit",
    "https://migri.fi/en/temporary-permit",
    "https://migri.fi/en/d-permit",

    # ── Migri: Processing fees (actual euro amounts) ───────────────────────────
    "https://migri.fi/en/processing-fees",

    # ── Migri: Right to work (crucial — many users ask what work rights their permit gives)
    "https://migri.fi/en/right-to-work",
    "https://migri.fi/en/applying-for-a-new-permit",

    # ── Kela: Specific benefit detail pages (missing from original scrape) ─────
    "https://www.kela.fi/general-housing-allowance",
    "https://www.kela.fi/child-benefit",
    "https://www.kela.fi/parental-benefit",
    "https://www.kela.fi/national-pension",
    "https://www.kela.fi/sickness-allowance",
    "https://www.kela.fi/when-you-move-to-finland",
    "https://www.kela.fi/jobseekers-allowance",

    # ── InfoFinland: Integration and employment pages ──────────────────────────
    "https://infofinland.fi/en/settling-in-finland/integration",
    "https://infofinland.fi/en/work-and-enterprise/looking-for-work",
    "https://infofinland.fi/en/work-and-enterprise/starting-a-business",
    "https://infofinland.fi/en/settling-in-finland/finland-information",
    "https://infofinland.fi/en/health/using-health-services",

    # ── DVV: Personal identity code (the all-important Finnish hetu) ───────────
    "https://dvv.fi/en/personal-identity-code",
    "https://dvv.fi/en/notifications",

    # ── Vero: Additional tax guidance ─────────────────────────────────────────
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/income-taxes-in-finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/moving-to-finland/",

    # ── WorkInFinland.eu: Official government portal for specialists ───────────
    "https://www.workinfinland.eu/en/coming-to-finland/",
    "https://www.workinfinland.eu/en/coming-to-finland/residence-permit/",
    "https://www.workinfinland.eu/en/coming-to-finland/after-arrival/",
    "https://www.workinfinland.eu/en/living-in-finland/",
    "https://www.workinfinland.eu/en/living-in-finland/social-security-and-healthcare/",
    "https://www.workinfinland.eu/en/living-in-finland/taxation/",

    # ── International House Helsinki (retry — failed in original scrape) ────────
    "https://ihhelsinki.fi/services/",
    "https://ihhelsinki.fi/services/residence-permits/",
    "https://ihhelsinki.fi/services/social-security-benefits/",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned, prev_blank = [], False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    return "\n".join(cleaned).strip()


def extract_page(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Request failed — %s | %s", url, exc)
        return None
    if resp.status_code != 200:
        log.warning("HTTP %d — skipping %s", resp.status_code, url)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.find("body")
    )
    raw_text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    content = clean_text(raw_text)

    if not content or len(content) < 100:
        log.warning("Too little content from %s — skipping", url)
        return None

    log.info("  scraped  %s  (%d chars)", url[-70:], len(content))
    return {"url": url, "title": title, "content": content}


def get_domain_tag(source: str) -> str:
    s = source.lower()
    if "migri.fi" in s:        return "migri"
    if "infofinland.fi" in s:  return "infofinland"
    if "enterfinland" in s:    return "enterfinland"
    if "kela.fi" in s:         return "kela"
    if "dvv.fi" in s:          return "dvv"
    if "vero.fi" in s:         return "vero"
    if "te-palvelut" in s:     return "te_services"
    if "workinfinland.eu" in s: return "workinfinland"
    if "ihhelsinki" in s:      return "ihh"
    if "suomi.fi" in s:        return "suomi"
    return "pdf" if s.endswith(".pdf") else "other"


CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("work", [
        "work", "employee", "specialist", "fast-track", "fast track",
        "blue-card", "blue card", "entrepreneur", "startup", "start-up",
        "employer", "job", "employment permit", "work permit",
        "coming-to-finland-for-work", "seasonal work", "self-employed",
        "au pair", "income-requirement-for-persons-who-apply-for-a-residence-permit-on-the-basis-of-work",
    ]),
    ("study", [
        "study", "student", "student permit", "university", "school",
        "researcher", "research permit", "scholarship",
        "higher education", "vocational", "exchange student",
    ]),
    ("family", [
        "family", "spouse", "child", "parent", "relative",
        "family-member", "family member", "reunification",
        "moving-to-finland-to-be-with", "cohabiting partner", "dependent",
    ]),
    ("asylum", [
        "asylum", "refugee", "protection", "temporary-protection",
        "temporary protection", "humanitarian", "asylum seeker",
        "international protection", "stateless",
    ]),
    ("permanent", [
        "permanent", "permanent residence", "permanent-residence-permit",
        "long-term resident", "p-permit", "p permit",
        "language-skills-requirement", "period-of-residence-requirement",
        "work-history-requirement", "integration requirement",
    ]),
    ("citizenship", [
        "citizenship", "naturalisation", "naturalization",
        "requirements-for-citizenship", "citizenship-requirements",
        "language requirement for citizenship", "dual citizenship",
        "finnish citizen", "declaration of citizenship", "citizenship-declaration",
    ]),
    ("eu_citizen", [
        "eu-citizen", "eu citizen", "registration-of-right",
        "right-of-residence", "eea", "eu national",
        "permanent-right-of-residence", "freedom of movement",
        "union citizen", "nordic citizen", "d-permit",
    ]),
    ("processing", [
        "processing-time", "processing time", "processing-fee", "processing fees",
        "fee", "cost", "price list", "how long does it take", "application fee",
    ]),
    ("appeals", [
        "appeal", "appealing", "appeal a decision", "administrative court",
        "complaint", "rectification", "reconsideration",
    ]),
    ("benefits", [
        "kela", "benefit", "social security", "allowance", "pension",
        "unemployment benefit", "housing benefit", "basic social assistance",
        "health insurance benefit", "maternity", "parental benefit",
        "child benefit", "entitled to kela", "sickness allowance",
        "general housing allowance", "national pension",
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
        "digital and population",
    ]),
    ("employment_services", [
        "te-palvelut", "te services", "te office", "employment office",
        "job seeker", "integration training", "integration services",
        "employment agency", "public employment",
    ]),
    ("housing", [
        "housing", "apartment", "rent", "rental", "lease",
        "find housing", "housing market",
    ]),
    ("health", [
        "health", "healthcare", "health centre", "doctor", "hospital",
        "health services", "terveyskeskus",
    ]),
    ("general", []),
]

def classify_chunk(source: str, text: str) -> str:
    haystack = (source + " " + text[:400]).lower()
    for cat, keywords in CATEGORY_RULES:
        if not keywords:
            return cat
        if any(kw in haystack for kw in keywords):
            return cat
    return "general"


# ── Step 1: Fetch new URLs ─────────────────────────────────────────────────────

def fetch_new_pages() -> int:
    """Fetch new URLs not already in migri_pages.json. Returns count added."""
    if PAGES_JSON.exists():
        with open(PAGES_JSON, encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    already_scraped = {p["url"] for p in existing}
    to_fetch = [u for u in NEW_URLS if u not in already_scraped]

    if not to_fetch:
        log.info("All new URLs already in migri_pages.json — nothing to fetch")
        return 0

    log.info("Fetching %d new URLs ...", len(to_fetch))
    added = 0
    for i, url in enumerate(to_fetch):
        log.info("[%d/%d] %s", i + 1, len(to_fetch), url)
        page = extract_page(url)
        if page:
            existing.append(page)
            added += 1
        if i < len(to_fetch) - 1:
            time.sleep(REQUEST_DELAY)

    PAGES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(PAGES_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    log.info("Added %d new pages. Total in migri_pages.json: %d", added, len(existing))
    return added


# ── Step 2: Re-process ALL pages + PDFs with new chunk settings ────────────────

def reprocess_all() -> list[dict]:
    """Chunk everything at 1200/200 (web) and 1500/300 (PDF)."""

    web_splitter = RecursiveCharacterTextSplitter(
        chunk_size=WEB_CHUNK_SIZE,
        chunk_overlap=WEB_CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    pdf_splitter = RecursiveCharacterTextSplitter(
        chunk_size=PDF_CHUNK_SIZE,
        chunk_overlap=PDF_CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks: list[dict] = []
    today = date.today().isoformat()
    PROCESSING_TIMES_URL = "https://migri.fi/en/processing-times"

    # Web pages
    if PAGES_JSON.exists():
        with open(PAGES_JSON, encoding="utf-8") as f:
            pages = json.load(f)
        log.info("Processing %d web pages ...", len(pages))
        for page in pages:
            url     = page.get("url", "")
            title   = page.get("title", "")
            content = clean_text(page.get("content", ""))
            if not content:
                continue
            raw_chunks = web_splitter.split_text(content)
            page_chunks = []
            for idx, text in enumerate(raw_chunks):
                if len(text) // 4 < MIN_TOKENS:
                    continue
                meta = {
                    "source":          url,
                    "title":           title,
                    "type":            "webpage",
                    "domain":          get_domain_tag(url),
                    "chunk_id":        idx,
                    "permit_category": classify_chunk(url, text),
                }
                if PROCESSING_TIMES_URL in url:
                    meta["scraped_date"] = today
                page_chunks.append({"text": text, "metadata": meta})
            all_chunks.extend(page_chunks)
        log.info("  Web chunks: %d", sum(1 for c in all_chunks if c["metadata"]["type"] == "webpage"))

    # PDFs
    if PDF_JSON.exists():
        with open(PDF_JSON, encoding="utf-8") as f:
            pdfs = json.load(f)
        log.info("Processing %d PDFs ...", len(pdfs))
        pdf_count_before = len(all_chunks)
        for doc in pdfs:
            source  = doc.get("source", "unknown.pdf")
            content = clean_text(doc.get("content", ""))
            if not content:
                continue
            raw_chunks = pdf_splitter.split_text(content)
            for idx, text in enumerate(raw_chunks):
                if len(text) // 4 < MIN_TOKENS:
                    continue
                all_chunks.append({
                    "text": text,
                    "metadata": {
                        "source":          source,
                        "title":           source,
                        "type":            "pdf",
                        "domain":          "pdf",
                        "chunk_id":        idx,
                        "permit_category": classify_chunk(source, text),
                    },
                })
        log.info("  PDF chunks: %d", len(all_chunks) - pdf_count_before)

    # Save
    CHUNKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    log.info("Total chunks written: %d  ->  %s", len(all_chunks), CHUNKS_JSON)
    return all_chunks


# ── Step 3: Rebuild ChromaDB from scratch ─────────────────────────────────────

def rebuild_chromadb(all_chunks: list[dict]) -> None:
    """Wipe and rebuild the ChromaDB collection with all chunks."""
    import shutil

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not set — check .env")

    # Wipe existing collection — use subprocess on Windows to avoid file-lock errors
    chroma_path = Path(CHROMA_DIR)
    if chroma_path.exists():
        log.info("Wiping existing ChromaDB at %s ...", CHROMA_DIR)
        import sys, subprocess
        if sys.platform == "win32":
            subprocess.run(["cmd", "/c", "rd", "/s", "/q", str(chroma_path)],
                           check=False, capture_output=True)
        else:
            shutil.rmtree(chroma_path)
        if chroma_path.exists():
            log.warning("Could not fully delete %s — continuing anyway (stale files may persist)", CHROMA_DIR)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=api_key)

    docs = [
        Document(page_content=c["text"], metadata=c["metadata"])
        for c in all_chunks
    ]

    log.info("Embedding %d documents in batches of 100 ...", len(docs))
    BATCH = 100
    vectordb = None
    for start in range(0, len(docs), BATCH):
        batch = docs[start:start + BATCH]
        end   = min(start + BATCH, len(docs))
        log.info("  Batch %d-%d ...", start + 1, end)
        if vectordb is None:
            vectordb = Chroma.from_documents(
                documents=batch,
                embedding=embeddings,
                collection_name="migri_guide",
                persist_directory=CHROMA_DIR,
            )
        else:
            vectordb.add_documents(batch)

    total = vectordb._collection.count()
    log.info("ChromaDB rebuilt: %d vectors at %s", total, CHROMA_DIR)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("MigriGuide — Patch & Rebuild")
    log.info("=" * 60)

    log.info("")
    log.info("STEP 1: Fetching new URLs ...")
    added = fetch_new_pages()

    log.info("")
    log.info("STEP 2: Re-processing all content at 1200/200 (web) and 1500/300 (PDF) ...")
    all_chunks = reprocess_all()

    log.info("")
    log.info("STEP 3: Rebuilding ChromaDB ...")
    rebuild_chromadb(all_chunks)

    log.info("")
    log.info("=" * 60)
    log.info("Done. %d new pages added. Total chunks: %d.", added, len(all_chunks))
    log.info("ChromaDB rebuilt at: %s", CHROMA_DIR)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
