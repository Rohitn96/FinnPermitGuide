"""
Stage 2 — turn raw pages into embeddable chunks.

Reads data/raw/pages.json + data/raw/pdfs.json, writes data/chunks.json.

    python -m pipeline.process
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).resolve().parent.parent
RAW_DIR    = BASE_DIR / "data" / "raw"
PAGES_IN   = RAW_DIR / "pages.json"
PDFS_IN    = RAW_DIR / "pdfs.json"
CHUNKS_OUT = BASE_DIR / "data" / "chunks.json"

CHUNK_SIZE        = 1200   # wide enough to hold a full requirement paragraph
CHUNK_OVERLAP     = 200
PDF_CHUNK_SIZE    = 1500   # legal text: multi-condition rules run long
PDF_CHUNK_OVERLAP = 300
MIN_CHARS         = 320    # below this it is nav debris, not content

SCRAPED_DATE = date.today().isoformat()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)
pdf_splitter = RecursiveCharacterTextSplitter(
    chunk_size=PDF_CHUNK_SIZE,
    chunk_overlap=PDF_CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# ── Which authority does a URL belong to ──────────────────────────────────────
# Drives the "According to Migri / Kela / Vero..." attribution in answers and
# the source badges in the UI, so the label is user-visible.
AUTHORITIES = [
    ("migri.fi",           "migri",        "Finnish Immigration Service (Migri)"),
    ("infofinland.fi",     "infofinland",  "InfoFinland"),
    ("kela.fi",            "kela",         "Kela"),
    ("dvv.fi",             "dvv",          "Digital and Population Data Services Agency (DVV)"),
    ("vero.fi",            "vero",         "Finnish Tax Administration (Vero)"),
    ("poliisi.fi",         "poliisi",      "Finnish Police"),
    ("traficom.fi",        "traficom",     "Finnish Transport and Communications Agency (Traficom)"),
    ("tulli.fi",           "tulli",        "Finnish Customs (Tulli)"),
    ("tyosuojelu.fi",      "tyosuojelu",   "Occupational Safety and Health Administration"),
    ("tyomarkkinatori.fi", "tyomarkkinatori", "Job Market Finland"),
    ("te-palvelut.fi",     "te_services",  "TE Services"),
    ("suomi.fi",           "suomi",        "Suomi.fi"),
    ("enterfinland.fi",    "enterfinland", "Enter Finland"),
    ("ihhelsinki.fi",      "ihh",          "International House Helsinki"),
]


def authority(url: str) -> tuple[str, str]:
    """Return (short tag, human-readable authority name) for a source URL."""
    netloc = urlparse(url).netloc.lower()
    for match, tag, name in AUTHORITIES:
        if match in netloc:
            return tag, name
    return "other", "Official Finnish source"


# ── Topic tagging ─────────────────────────────────────────────────────────────
# First match wins, so specific topics come before general ones. This is corpus
# metadata for diagnostics and filtering — the answer's own category is chosen
# by the model at answer time, not from here.
TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("citizenship",   ("citizenship", "naturalis", "naturaliz", "finnish citizen")),
    ("permanent",     ("permanent residence", "permanent-residence", "long-term resident",
                       "period-of-residence", "language-skills-requirement",
                       "work-history-requirement")),
    ("family",        ("family", "spouse", "cohabiting", "reunification", "child-in-finland",
                       "dna-analysis")),
    ("study",         ("student", "studies", "studying", "researcher", "graduation",
                       "university", "scholarship")),
    ("work",          ("work", "employed", "employer", "specialist", "blue-card", "entrepreneur",
                       "seasonal", "internship", "au-pair", "income-requirement", "salary",
                       "job", "fast-track")),
    ("asylum",        ("asylum", "refugee", "temporary protection", "international protection",
                       "reception")),
    ("eu_citizen",    ("eu-citizen", "eu citizen", "eea", "nordic citizen", "right-of-residence",
                       "freedom of movement")),
    ("benefits",      ("kela", "benefit", "allowance", "social assistance", "pension",
                       "unemployment", "sickness")),
    ("tax",           ("vero.fi", "tax", "verokortti", "tax card")),
    ("registration",  ("dvv.fi", "municipality of residence", "personal identity code",
                       "population register", "registering-your-address")),
    ("documents",     ("passport", "identity card", "id-card", "travel document",
                       "driving licence", "driving license", "traficom.fi",
                       "driving-licens", "vehicle registration")),
    ("customs",       ("tulli.fi", "customs", "removal goods", "importing", "pets")),
    ("worker_rights", ("tyosuojelu", "employment contract", "working hours", "termination",
                       "occupational", "collective agreement")),
    ("appeals",       ("appeal", "administrative court", "negative decision", "rectification")),
    ("processing",    ("processing time", "processing fee", "application status", "decision")),
]


def topic_of(url: str, text: str) -> str:
    haystack = f"{url} {text[:400]}".lower()
    for name, keywords in TOPICS:
        if any(kw in haystack for kw in keywords):
            return name
    return "general"


# ── Cleaning ──────────────────────────────────────────────────────────────────

BOILERPLATE = re.compile(
    r"^(skip to (main )?content|cookie settings?|accept all cookies|"
    r"share on (facebook|twitter|linkedin)|print this page|back to top|"
    r"was this page helpful\??|give feedback|last updated)\b",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    """Drop boilerplate lines and normalise spacing."""
    kept = [
        line for line in (l.strip() for l in text.splitlines())
        if line and not BOILERPLATE.match(line)
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


# Function words that are common in Finnish and effectively absent from English.
# Deliberately excludes "on", "ja" and "tai", which collide with English words
# or appear inside them.
FINNISH_MARKERS = frozenset("""
    että ovat voit voitte sinun sinulle hänen heidän myös mutta kuin sekä
    jos kun jotka jonka tämän tämä näiden niiden kanssa ilman jälkeen ennen
    mukaan täytyy pitää oleskelulupa oleskeluluvan hakemus hakemuksen
    hakea saada olla ovatko viranomainen kansalainen työntekijä
""".split())

MIN_FINNISH_RATIO = 0.03   # 3% of words being Finnish function words is decisive


def is_finnish(text: str) -> bool:
    """True when a page is Finnish despite living under an English URL path.

    Several of these sites publish Finnish-language news under /en/ paths, so
    the crawler's language prefix does not catch them. Left in, they consume
    retrieval slots and occasionally surface as Finnish text inside an English
    answer's sources.
    """
    words = re.findall(r"[a-zäöå]+", text.lower())
    if len(words) < 40:
        return False
    hits = sum(1 for w in words if w in FINNISH_MARKERS)
    return hits / len(words) >= MIN_FINNISH_RATIO


def build_chunks(
    *, text: str, url: str, title: str, source_type: str, split
) -> list[dict]:
    """Split one document and attach retrieval metadata to every chunk.

    The page title is prepended to the embedded text. A chunk taken from the
    middle of a page otherwise carries no signal about what page it came from —
    "you must have lived in Finland for four years" is indistinguishable between
    the permanent-residence and the citizenship page once it is detached from
    its heading, and that ambiguity is what produces confidently wrong answers.
    """
    content = clean(text)
    if not content:
        return []
    if is_finnish(content):
        log.info("  skipped (Finnish-language page) %s", url[-70:])
        return []

    tag, name = authority(url)
    chunks = []

    for idx, piece in enumerate(split.split_text(content)):
        if len(piece) < MIN_CHARS:
            continue
        chunks.append({
            "text": f"{title}\n\n{piece}" if title else piece,
            "metadata": {
                "source":       url,
                "title":        title,
                "type":         source_type,
                "domain":       tag,
                "authority":    name,
                "topic":        topic_of(url, piece),
                "chunk_id":     idx,
                "scraped_date": SCRAPED_DATE,
            },
        })
    return chunks


def load(path: Path) -> list[dict]:
    if not path.exists():
        log.warning("%s not found — skipping", path)
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    log.info("=== Stage 2: process ===")

    chunks: list[dict] = []

    for page in load(PAGES_IN):
        chunks.extend(build_chunks(
            text=page.get("content", ""),
            url=page.get("url", ""),
            title=page.get("title", ""),
            source_type="webpage",
            split=splitter,
        ))

    for doc in load(PDFS_IN):
        name = doc.get("source", "unknown.pdf")
        chunks.extend(build_chunks(
            text=doc.get("content", ""),
            url=name,
            title=name,
            source_type="pdf",
            split=pdf_splitter,
        ))

    # Identical text across pages is shared boilerplate that survived cleaning.
    # Keeping copies wastes retrieval slots on the same sentence many times over.
    seen, unique = set(), []
    for chunk in chunks:
        key = chunk["text"][:200]
        if key not in seen:
            seen.add(key)
            unique.append(chunk)
    duplicates = len(chunks) - len(unique)

    CHUNKS_OUT.write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("=== Stage 2 complete ===")
    log.info("chunks: %d (dropped %d duplicates) → %s", len(unique), duplicates, CHUNKS_OUT)

    for label, counter in (
        ("by authority", Counter(c["metadata"]["domain"] for c in unique)),
        ("by topic",     Counter(c["metadata"]["topic"]  for c in unique)),
    ):
        log.info("%s:", label)
        for key, n in counter.most_common():
            log.info("  %-20s %5d", key, n)


if __name__ == "__main__":
    main()
