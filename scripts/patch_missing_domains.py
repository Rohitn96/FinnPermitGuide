"""
FinnPermit Guide — Targeted domain patch
Scrapes tulli.fi, tyosuojelu.fi, and poliisi.fi (all had 0 or very few pages
in the main rebuild due to URL restructuring) and upserts into Pinecone.

Does NOT delete any existing vectors — safe to run after a full rebuild.

Run: .venv\Scripts\python.exe scripts/patch_missing_domains.py
Expected runtime: ~5-10 minutes
"""

import logging
import os
import re
import time
from collections import deque
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SCRAPED_DATE = date.today().isoformat()
TIMEOUT = 25
REQUEST_DELAY = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FinnPermitGuide-Bot/2.0; "
        "educational/non-commercial; +https://finnpermit.com)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

NOISE_TAGS = [
    "nav", "footer", "header", "script", "style", "noscript",
    "aside", "form", "button", "iframe", "svg", "figure",
]

GLOBAL_SKIP = [
    "#", "mailto:", "tel:", "javascript:", "data:",
    ".pdf", ".doc", ".docx", ".xls", ".zip",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".xml",
    "/logout", "/login", "/register", "/admin", "/404", "/403",
    "?print=", "?format=pdf", "?download=", "?share=",
    "/feed/", "/rss/", "/atom/",
]

# Verified working URLs (checked 2026-05-22)
PATCH_DOMAINS = {
    "tulli.fi": {
        "lang_prefix": "/en/",
        "max_pages": 40,
        "skip": ["/fi/", "/sv/"],
        "domain_tag": "tulli",
        "permit_category": "customs",
        "id_prefix": "tulli_patch",
        "seeds": [
            "https://tulli.fi/en/individuals/moving",
            "https://tulli.fi/en/individuals/moving/to-finland",
            "https://tulli.fi/en/individuals/moving/how-to-declare-removal-goods",
            "https://tulli.fi/en/individuals/moving/goods-imported-by-a-student-arriving-in-finland",
            "https://tulli.fi/en/restrictions/pets",
            "https://tulli.fi/en/restrictions/pets/moving",
            "https://tulli.fi/en/restrictions/pets/travelling",
            "https://tulli.fi/en/restrictions/cars/moving",
            "https://tulli.fi/en/individuals/going-to-order-goods-from-abroad",
        ],
    },
    "tyosuojelu.fi": {
        "lang_prefix": "/en/",
        "max_pages": 50,
        "skip": ["/fi/", "/sv/"],
        "domain_tag": "tyosuojelu",
        "permit_category": "worker_rights",
        "id_prefix": "tyosuojelu_patch",
        "seeds": [
            "https://www.tyosuojelu.fi/en/employment-relationship",
            "https://www.tyosuojelu.fi/en/employment-relationship/working-hours",
            "https://www.tyosuojelu.fi/en/employment-relationship/employment-contract",
            "https://www.tyosuojelu.fi/en/employment-relationship/pay",
            "https://www.tyosuojelu.fi/en/employment-relationship/termination",
            "https://www.tyosuojelu.fi/en/working-conditions",
            "https://www.tyosuojelu.fi/en/occupational-health",
        ],
    },
    "poliisi.fi": {
        "lang_prefix": "/en/",
        "max_pages": 50,
        "skip": ["/fi/", "/sv/", "/ru/", "/ar/", "/so/"],
        "domain_tag": "poliisi",
        "permit_category": "documents",
        "id_prefix": "poliisi_patch",
        "seeds": [
            "https://poliisi.fi/en/passports-identity-cards-and-permits",
            "https://poliisi.fi/en/passport",
            "https://poliisi.fi/en/identity-card",
            "https://poliisi.fi/en/how-to-apply-for-an-identity-card",
            "https://poliisi.fi/en/using-your-passport",
        ],
    },
}

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def convert_tables_to_text(soup: BeautifulSoup) -> None:
    for table in soup.find_all("table"):
        rows = []
        header_written = False
        for tr in table.find_all("tr"):
            ths = tr.find_all("th")
            tds = tr.find_all("td")
            cells = ths if ths else tds
            if not cells:
                continue
            cell_texts = [
                " ".join(c.get_text(separator=" ", strip=True).split()) or "–"
                for c in cells
            ]
            if all(t in ("–", "", "-") for t in cell_texts):
                continue
            rows.append(" | ".join(cell_texts))
            if ths and not header_written:
                rows.append("-" * min(60, sum(len(t) + 3 for t in cell_texts)))
                header_written = True
        if rows:
            tag = soup.new_tag("p")
            tag.string = "\n".join(rows)
            table.replace_with(tag)
        else:
            table.decompose()


def clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def is_crawlable(url: str, domain_key: str, config: dict) -> bool:
    url_lower = url.lower()
    netloc = urlparse(url).netloc.lower()

    if domain_key not in netloc:
        return False

    for skip in GLOBAL_SKIP:
        if skip in url_lower:
            return False

    for skip in config.get("skip", []):
        if skip in url_lower:
            return False

    path = urlparse(url).path
    lang_prefix = config.get("lang_prefix")
    if lang_prefix and not path.startswith(lang_prefix):
        return False

    if len(path.rstrip("/")) < 3:
        return False

    return True


def fetch_page(url: str) -> tuple[dict | None, BeautifulSoup | None]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Request failed — %s | %s", url, exc)
        return None, None

    if resp.status_code == 429:
        log.warning("Rate limited (429) — %s — pausing 10s", url)
        time.sleep(10)
        return None, None

    if resp.status_code != 200:
        log.warning("HTTP %d — skipping %s", resp.status_code, url)
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")
    convert_tables_to_text(soup)

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
    raw_text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    content = clean_text(raw_text)

    if not content or len(content) < 120:
        log.warning("No content — skipping %s", url)
        return None, None

    log.info("  ✓  %-70s  (%d chars)", url[-70:], len(content))
    return {"url": url, "title": title, "content": content}, soup


def crawl_domain(domain_key: str, config: dict) -> list[dict]:
    seeds = config["seeds"]
    max_pages = config["max_pages"]

    visited: set[str] = set()
    queue: deque = deque()
    pages: list[dict] = []

    for seed in seeds:
        url = seed.rstrip("/")
        if is_crawlable(url, domain_key, config) and url not in visited:
            visited.add(url)
            queue.append(url)

    log.info("── %s — %d seeds queued, max %d pages", domain_key, len(queue), max_pages)

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        page, soup = fetch_page(url)

        if page:
            pages.append(page)

        if soup:
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href:
                    continue
                full_url = urljoin(url, href).split("#")[0].rstrip("/")
                if (
                    full_url not in visited
                    and is_crawlable(full_url, domain_key, config)
                    and len(pages) + len(queue) < max_pages
                ):
                    visited.add(full_url)
                    queue.append(full_url)

        time.sleep(REQUEST_DELAY)

    log.info("  %s: scraped %d pages", domain_key, len(pages))
    return pages


def pages_to_chunks(pages: list[dict], config: dict) -> list[dict]:
    chunks = []
    domain_tag = config["domain_tag"]
    permit_category = config["permit_category"]

    for page in pages:
        raw_chunks = splitter.split_text(page["content"])
        for idx, chunk_text in enumerate(raw_chunks):
            if len(chunk_text) // 4 < 80:
                continue
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    "source": page["url"],
                    "title": page["title"],
                    "type": "webpage",
                    "domain": domain_tag,
                    "chunk_id": idx,
                    "permit_category": permit_category,
                    "scraped_date": SCRAPED_DATE,
                },
            })

    return chunks


def main() -> None:
    log.info("=" * 60)
    log.info("FinnPermit Guide — Missing Domain Patch")
    log.info("Domains: tulli.fi, tyosuojelu.fi, poliisi.fi")
    log.info("=" * 60)

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "migri-guide"))

    stats = index.describe_index_stats()
    log.info("Current Pinecone vector count: %d", stats.total_vector_count)

    total_upserted = 0

    for domain_key, config in PATCH_DOMAINS.items():
        pages = crawl_domain(domain_key, config)
        if not pages:
            log.warning("No pages scraped for %s — skipping", domain_key)
            continue

        chunks = pages_to_chunks(pages, config)
        log.info("  Produced %d chunks from %d pages", len(chunks), len(pages))

        id_prefix = config["id_prefix"]
        vectors = []
        for i, chunk in enumerate(chunks):
            vec_id = f"{id_prefix}_{i}"
            embedding = embeddings.embed_query(chunk["text"])
            vectors.append({
                "id": vec_id,
                "values": embedding,
                "metadata": {"text": chunk["text"], **chunk["metadata"]},
            })
            if (i + 1) % 10 == 0 or (i + 1) == len(chunks):
                log.info("  Embedded %d/%d chunks for %s", i + 1, len(chunks), domain_key)

        for i in range(0, len(vectors), 100):
            index.upsert(vectors=vectors[i:i + 100])

        log.info("  Upserted %d vectors for %s", len(vectors), domain_key)
        total_upserted += len(vectors)

    stats = index.describe_index_stats()
    log.info("=" * 60)
    log.info("Patch complete")
    log.info("Vectors upserted this run : %d", total_upserted)
    log.info("Total vectors in index    : %d", stats.total_vector_count)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
