# MigriGuide — Data Pipeline (Stage 1)

Unofficial AI-powered immigration assistant for Finland.  
This repo covers **data collection → chunking → vector database** only.  
RAG pipeline, backend, and frontend are separate stages.

---

## Project structure

```
migri-assistant/
├── scraper/
│   └── scrape.py          ← Stage 1: web scraping + PDF extraction
├── processor/
│   └── process.py         ← Stage 2: cleaning, chunking, auto-tagging
├── vectordb/
│   ├── build_db.py        ← Stage 3: embed chunks → ChromaDB
│   └── test_query.py      ← Stage 3: retrieval smoke test
├── data/
│   ├── raw/
│   │   ├── pdfs/          ← drop your PDF files here before running Stage 1
│   │   ├── migri_pages.json
│   │   └── pdf_content.json
│   ├── cleaned/
│   │   └── all_chunks.json
│   └── chroma_db/         ← persisted ChromaDB
├── .env                   ← add your OPENAI_API_KEY here
└── requirements.txt
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env` and fill in your key:

```
OPENAI_API_KEY=sk-...
```

---

## Running the pipeline

Run each stage independently **in order**:

### Stage 1 — Scrape

```bash
python scraper/scrape.py
```

Outputs:
- `data/raw/migri_pages.json` — 26 scraped web pages
- `data/raw/pdf_content.json` — text from any PDFs in `data/raw/pdfs/`

> Place any Migri PDF guides inside `data/raw/pdfs/` before running.

---

### Stage 2 — Process & Chunk

```bash
python processor/process.py
```

Outputs:
- `data/cleaned/all_chunks.json` — all chunks with metadata

Chunk config: `chunk_size=700`, `chunk_overlap=100`, `min_tokens=80`.

Auto-tagged `permit_category` values:
`work | study | family | asylum | permanent | citizenship | eu_citizen | processing | general`

---

### Stage 3 — Build vector database

```bash
python vectordb/build_db.py
```

Embeds every chunk using `text-embedding-3-small` and persists to ChromaDB.  
Prints total vector count when done.

---

### Stage 3 — Test retrieval

```bash
python vectordb/test_query.py
```

Runs a hardcoded test query against the existing ChromaDB and prints the top 5 results.  
**Does not rebuild the database.**

---

## Data sources

| Source | Type |
|--------|------|
| migri.fi/en/* | Official Finnish Immigration Service |
| infofinland.fi/en/* | Government integration info portal |
| data/raw/pdfs/*.pdf | Any PDFs you add manually |

---

## Notes

- 1-second delay between scrape requests (polite crawling)
- Non-200 responses are logged and skipped gracefully
- Chunks under ~80 tokens (nav remnants) are filtered out
- The `processing-times` page gets an extra `scraped_date` metadata field
