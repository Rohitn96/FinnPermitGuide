"""
Targeted patch: fetch the new Migri income-requirement-for-work page,
chunk it, and upsert into Pinecone without touching any existing vectors.
"""

import os, re, json, logging
from pathlib import Path
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

URL   = "https://migri.fi/en/working-in-finland/income-requirement"
TITLE = "Income requirement for persons who apply for a residence permit on the basis of work"

# ── Fetch ──────────────────────────────────────────────────────────────────────
log.info("Fetching %s", URL)
r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
r.raise_for_status()

soup = BeautifulSoup(r.text, "html.parser")
for tag in soup(["script", "style", "nav", "footer", "header"]):
    tag.decompose()
raw_text = soup.get_text(separator="\n", strip=True)

# Clean
text = re.sub(r"\n{3,}", "\n\n", raw_text)
text = re.sub(r"[ \t]{2,}", " ", text)
text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
log.info("Extracted %d chars", len(text))

# ── Chunk ──────────────────────────────────────────────────────────────────────
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200, chunk_overlap=200,
    length_function=len, separators=["\n\n", "\n", ". ", " ", ""],
)
chunks = splitter.split_text(text)
chunks = [c for c in chunks if len(c) // 4 >= 80]   # drop tiny fragments
log.info("Produced %d chunks", len(chunks))

# ── Embed & upsert ─────────────────────────────────────────────────────────────
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)
pc    = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "migri-guide"))

vectors = []
for i, chunk in enumerate(chunks):
    vec_id = f"income_req_work_{i}"
    embedding = embeddings.embed_query(chunk)
    vectors.append({
        "id": vec_id,
        "values": embedding,
        "metadata": {
            "text":             chunk,
            "source":           URL,
            "title":            TITLE,
            "type":             "webpage",
            "domain":           "migri",
            "chunk_id":         i,
            "permit_category":  "work",
        },
    })
    log.info("  Embedded chunk %d/%d", i + 1, len(chunks))

index.upsert(vectors=vectors)
log.info("Upserted %d vectors into Pinecone", len(vectors))

# ── Verify ─────────────────────────────────────────────────────────────────────
stats = index.describe_index_stats()
log.info("Index total vectors: %d", stats.total_vector_count)
log.info("Patch complete.")
