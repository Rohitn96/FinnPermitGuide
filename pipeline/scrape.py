"""
Stage 1 — collect pages from official Finnish government sources.

Writes data/raw/pages.json and data/raw/pdfs.json.

Each domain is crawled by its own thread, so the 1.5s politeness delay is paid
per domain rather than globally. One request per domain at a time is the part
that matters for being a good citizen; running fourteen domains concurrently
cuts a 35-minute crawl to under 10.

    python -m pipeline.scrape
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

from pipeline.sources import DOMAINS, GLOBAL_SKIP, SEEDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).resolve().parent.parent
RAW_DIR   = BASE_DIR / "data" / "raw"
PDF_DIR   = RAW_DIR / "pdfs"
PAGES_OUT = RAW_DIR / "pages.json"
PDF_OUT   = RAW_DIR / "pdfs.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 1.5   # seconds between requests to the SAME domain
TIMEOUT       = 25

# Floor for socket operations that requests' timeout= does not cover. Note this
# does NOT bound DNS: socket.getaddrinfo() is a blocking C call that ignores
# Python socket timeouts, so a hung resolver can still stall a fetch.
socket.setdefaulttimeout(TIMEOUT + 5)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FinnPermitGuide-Bot/3.0; "
        "educational/non-commercial; +https://finnpermit.com)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

NOISE_TAGS = [
    "nav", "footer", "header", "script", "style", "noscript",
    "aside", "form", "button", "iframe", "svg", "figure",
    "breadcrumb", "cookie-consent", "cookie-bar",
]


# ── URL filtering ─────────────────────────────────────────────────────────────

def domain_of(url: str) -> str | None:
    """Return the DOMAINS key this URL belongs to, or None if it is off-catalogue."""
    netloc = urlparse(url).netloc.lower()
    for key in DOMAINS:            # dict order puts subdomains before parents
        if key in netloc:
            return key
    return None


def is_crawlable(url: str) -> bool:
    low = url.lower()
    if any(skip in low for skip in GLOBAL_SKIP):
        return False

    key = domain_of(url)
    if not key:
        return False
    config = DOMAINS[key]

    if any(skip in low for skip in config["skip"]):
        return False

    prefix = config["lang_prefix"]
    path   = urlparse(url).path
    if prefix and not path.startswith(prefix):
        return False

    return len(path.rstrip("/")) >= 3   # reject bare domain roots


# ── HTML → text ───────────────────────────────────────────────────────────────

def tables_to_text(soup: BeautifulSoup) -> None:
    """Rewrite <table> as pipe-delimited text, in place.

    Income thresholds, fee schedules and requirement matrices live in tables.
    Plain get_text() runs the cells together into an unreadable stream and the
    numbers lose their row and column, so the answer layer cannot use them.
    """
    for table in soup.find_all("table"):
        rows, header_done = [], False
        for tr in table.find_all("tr"):
            ths, tds = tr.find_all("th"), tr.find_all("td")
            cells = ths or tds
            if not cells:
                continue
            texts = [
                " ".join(c.get_text(separator=" ", strip=True).split()) or "–"
                for c in cells
            ]
            if all(t in ("–", "", "-") for t in texts):
                continue
            rows.append(" | ".join(texts))
            if ths and not header_done:
                rows.append("-" * min(60, sum(len(t) + 3 for t in texts)))
                header_done = True

        if rows:
            tag = soup.new_tag("p")
            tag.string = "\n".join(rows)
            table.replace_with(tag)
        else:
            table.decompose()


def clean_text(text: str) -> str:
    """Collapse runaway whitespace while keeping paragraph breaks."""
    # Government CMSs emit non-breaking and zero-width spaces liberally. Left
    # in, they survive through chunking and turn up as mojibake in answers.
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    out, prev_blank = [], False
    for line in (l.rstrip() for l in text.splitlines()):
        if line:
            out.append(line)
            prev_blank = False
        elif not prev_blank:
            out.append("")
            prev_blank = True
    return "\n".join(out).strip()


def extract(html: str, url: str) -> tuple[str, str, BeautifulSoup | None]:
    """Return (title, content, soup). Content is '' when the page is unusable."""
    soup = BeautifulSoup(html, "html.parser")

    tables_to_text(soup)           # before noise removal, which eats structure
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.find(class_="main-content")
        or soup.find("body")
    )
    content = clean_text((main or soup).get_text(separator="\n"))

    if len(content) < 120:
        return "", "", None
    return title, content, soup


def fetch(url: str) -> tuple[dict | None, BeautifulSoup | None]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("request failed  %s | %s", url, exc)
        return None, None

    if resp.status_code == 429:
        log.warning("rate limited (429) %s — backing off 10s", url)
        time.sleep(10)
        return None, None
    if resp.status_code != 200:
        log.warning("HTTP %d  %s", resp.status_code, url)
        return None, None

    title, content, soup = extract(resp.text, url)
    if not content:
        log.warning("no content extracted  %s", url)
        return None, None

    log.info("ok  %-72s (%d chars)", url[-72:], len(content))
    return {"url": url, "title": title, "content": content}, soup


def sublinks(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Crawlable same-domain links found on a page."""
    base_key = domain_of(base_url)
    if not base_key:
        return []

    found = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        full = urljoin(base_url, href).split("#")[0].rstrip("/")
        if full and domain_of(full) == base_key and is_crawlable(full):
            found.add(full)
    return sorted(found)


# ── Crawl ─────────────────────────────────────────────────────────────────────

def crawl_domain(key: str, seeds: list[str]) -> list[dict]:
    """BFS one domain to its page cap. Seeds are visited before discovered links."""
    cap     = DOMAINS[key]["max_pages"]
    queue   = deque(seeds)
    visited = set(seeds)
    pages: list[dict] = []
    attempted = 0

    while queue and len(pages) < cap:
        url = queue.popleft()
        attempted += 1

        page, soup = fetch(url)
        if page:
            pages.append(page)
            if soup and len(pages) + len(queue) < cap:
                for link in sublinks(soup, url):
                    if link not in visited:
                        visited.add(link)
                        queue.append(link)

        time.sleep(REQUEST_DELAY)

    # A domain that fetches pages but yields nothing usable is almost always
    # client-side rendered. That failure is silent otherwise — it just shows up
    # months later as a topic the assistant cannot answer.
    if attempted and not pages:
        log.error("ZERO YIELD  %s — fetched %d pages, extracted none. "
                  "Likely JavaScript-rendered; see EXCLUDED in pipeline/sources.py",
                  key, attempted)

    log.info("done  %-28s %d pages (cap %d, queue left %d)",
             key, len(pages), cap, len(queue))
    return pages


def crawl_all(only: list[str] | None = None) -> list[dict]:
    by_domain: dict[str, list[str]] = {}
    for raw in SEEDS:
        url = raw.rstrip("/")
        if not is_crawlable(url):
            log.warning("seed rejected by filters: %s", url)
            continue
        by_domain.setdefault(domain_of(url), []).append(url)

    if only:
        by_domain = {k: v for k, v in by_domain.items() if any(o in k for o in only)}
        if not by_domain:
            raise SystemExit(f"no configured domain matches {only}")

    log.info("crawling %d domains from %d seeds",
             len(by_domain), sum(len(v) for v in by_domain.values()))

    with ThreadPoolExecutor(max_workers=len(by_domain)) as pool:
        results = pool.map(lambda kv: crawl_domain(*kv), by_domain.items())
        pages = [page for domain_pages in results for page in domain_pages]

    log.info("── crawl summary ──")
    counts: dict[str, int] = {}
    for p in pages:
        counts[domain_of(p["url"]) or "?"] = counts.get(domain_of(p["url"]) or "?", 0) + 1
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        cap  = DOMAINS.get(key, {}).get("max_pages", 0)
        note = "  ← AT CAP, corpus is being truncated" if n >= cap else ""
        log.info("  %-28s %4d / %d%s", key, n, cap, note)
    log.info("  total pages: %d", len(pages))
    return pages


# ── PDFs ──────────────────────────────────────────────────────────────────────

def extract_pdfs() -> list[dict]:
    """Extract text from any PDFs dropped into data/raw/pdfs/."""
    files = sorted(PDF_DIR.glob("*.pdf"))
    if not files:
        log.info("no PDFs in %s", PDF_DIR)
        return []

    docs = []
    for path in files:
        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            log.warning("cannot open %s — %s", path.name, exc)
            continue

        text = clean_text("\n".join(doc.load_page(i).get_text("text") for i in range(len(doc))))
        doc.close()

        if text:
            log.info("ok  PDF %-60s (%d chars)", path.name, len(text))
            docs.append({"source": path.name, "content": text})
        else:
            log.warning("no text in %s", path.name)
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect pages from official sources.")
    parser.add_argument(
        "--only", nargs="+", metavar="DOMAIN",
        help="crawl just these domains and merge them into the existing "
             "data/raw/pages.json, instead of recrawling everything. Adding one "
             "source should not cost a full crawl of all the others.",
    )
    args = parser.parse_args()

    log.info("=== Stage 1: collect ===")
    start = time.time()

    pages = crawl_all(args.only)

    if args.only and PAGES_OUT.exists():
        existing = json.loads(PAGES_OUT.read_text(encoding="utf-8"))
        refreshed = {domain_of(p["url"]) for p in pages}
        # Drop the old copies of the domains just recrawled, keep everything else.
        kept = [p for p in existing if domain_of(p["url"]) not in refreshed]
        log.info("merging: %d new pages, %d kept from previous crawl", len(pages), len(kept))
        pages = kept + pages

    PAGES_OUT.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("pages → %s (%d)", PAGES_OUT, len(pages))

    if args.only and PDF_OUT.exists():
        log.info("pdfs unchanged (--only run)")
    else:
        pdfs = extract_pdfs()
        PDF_OUT.write_text(json.dumps(pdfs, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("pdfs  → %s (%d)", PDF_OUT, len(pdfs))

    log.info("=== Stage 1 complete in %.1f min ===", (time.time() - start) / 60)


if __name__ == "__main__":
    main()
