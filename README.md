# FinnPermit Guide

An AI assistant that answers questions about immigrating to Finland — residence
permits, citizenship, Kela benefits, DVV registration, tax, documents, customs
and workers' rights.

Every answer is generated from text retrieved out of a knowledge base built by
crawling official Finnish government sites. The model is instructed never to use
its own knowledge of Finnish immigration law, and the UI only ever shows source
links that were actually retrieved. Answers say when the sources do not cover
something rather than guessing.

Live at **[finnpermit.com](https://finnpermit.com)**. Not affiliated with Migri
or any Finnish authority.

## How it works

```
                   ┌─────────────────────────────────────────┐
  A question  ───► │ 1. rewrite    make it standalone,        │
                   │               English, typo-free         │
                   │ 2. retrieve   40 candidates from         │
                   │               Pinecone by embedding      │
                   │ 3. rerank     cross-encoder keeps the 12 │
                   │               that actually answer it    │
                   │ 4. answer     grounded strictly in those │
                   └─────────────────────────────────────────┘
                                     │
                                     ▼
                        answer · sources · follow-ups
```

Two model calls per question. Retrieving wide and reranking is what makes
answers specific: embedding similarity alone surfaces a dozen near-identical
overview pages and buries the one paragraph containing the actual threshold.

## Layout

| Path | What it is |
|---|---|
| `rag/` | Answering. `retrieval.py` searches and reranks, `prompts.py` holds the system prompt and response schema, `answer.py` runs the pipeline, `config.py` has every tunable. |
| `api/` | FastAPI service — `/ask`, `/feedback`, `/` health. Rate limiting, edge authentication, structured event logging. |
| `pipeline/` | Knowledge-base build. `sources.py` is the source catalogue, then `scrape.py` → `process.py` → `index.py`, orchestrated by `run.py`. |
| `eval/` | Golden-set harness. `cases.json` is the test set, `run.py` scores answers mechanically and with a model judge. |
| `frontend/` | Next.js chat UI, deployed on Cloudflare Pages. |

## Running locally

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements-pipeline.txt

cp .env.example .env        # then fill in the keys
uvicorn api.main:app --reload
```

`.env` needs:

```
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=migri-guide-YYYYMMDD
ALLOW_UNAUTHENTICATED=true      # local only — see "Edge authentication"
```

Frontend:

```bash
cd frontend
npm install
npm run dev          # expects the API on http://localhost:8000
```

## Rebuilding the knowledge base

```bash
python -m pipeline.run
```

Crawls every source in `pipeline/sources.py`, chunks the text, embeds it, and
writes it to a **new** index named `migri-guide-YYYYMMDD`. Production keeps
serving the old index until you switch over, so a bad rebuild is never a live
outage and rollback is just pointing the name back.

Roughly 15 minutes and about $0.20 in embedding cost. Individual stages:

```bash
python -m pipeline.scrape                    # → data/raw/pages.json
python -m pipeline.process                   # → data/chunks.json
python -m pipeline.index --into some-index   # → Pinecone
```

Watch the crawl summary for domains marked `AT CAP` — that means the page limit,
not the site, decided what got collected, and rebuilds will silently swap pages
in and out. Raise the cap in `sources.py`. A `ZERO YIELD` line means a site
started rendering client-side and a static crawler can no longer read it.

## Evaluating

```bash
python -m eval.run                            # every case, against the live index
python -m eval.run --index migri-guide-20260908
python -m eval.run --case salary              # one case
```

Each case gets deterministic checks (expected facts, expected category and
source authority, banned phrasing, and euro figures that must appear verbatim in
a retrieved source) plus a model judge scoring grounding, completeness,
usefulness and format.

**Grounding is the score that matters.** An invented income threshold is worse
than no answer, because someone will act on it. Never ship a corpus or prompt
change that lowers the grounding mean.

## Deploying

### Backend — Google Cloud Run

```bash
gcloud run deploy migriguide-api \
  --source . --region europe-north1 --allow-unauthenticated
```

To put a new corpus live:

```bash
printf 'migri-guide-20260908' | \
  gcloud secrets versions add pinecone-index --data-file=-
gcloud run services update migriguide-api --region europe-north1
```

Rolling back is the same command with the previous index name.

### Frontend — Cloudflare Pages

Pushing to `master` triggers a build. Environment variables live in the Pages
dashboard under Settings → Environment variables:

| Variable | Purpose |
|---|---|
| `BACKEND_URL` | Cloud Run service URL |
| `EDGE_SHARED_SECRET` | Must match the backend's — see below |

### Edge authentication

The Cloud Run URL is publicly reachable, so anything at the CDN can be bypassed
by calling it directly. `EDGE_SHARED_SECRET` is a shared value that the site's
edge route sends as `X-Edge-Auth` and the backend checks; without it, per-IP
rate limits mean nothing and anyone can bill questions to the OpenAI account.

**Order matters when rotating it.** Set it on Cloudflare Pages and redeploy the
frontend *first*, then set it on Cloud Run. The reverse order 401s every live
user until the frontend catches up.

The backend fails closed: with neither `EDGE_SHARED_SECRET` nor
`ALLOW_UNAUTHENTICATED=true`, every `/ask` returns 401. A forgotten variable
should be a visible outage rather than a silently open endpoint.

## Analytics

Measured server-side, with no third-party script in the visitor's browser. The
API writes one JSON line per event to stdout; Cloud Run forwards stdout to Cloud
Logging, where these are queryable and chartable.

This replaced an arrangement that recorded nothing at all: the frontend had no
analytics beacon, and the backend wrote its logs to a file on the container's
ephemeral disk, which is discarded on every deploy.

Useful queries:

```
jsonPayload.event="ask"                          -- every question answered
jsonPayload.event="ask" jsonPayload.quality="not_in_sources"   -- coverage gaps
jsonPayload.event="feedback" jsonPayload.vote="down"           -- bad answers
jsonPayload.event="rate_limited"                 -- someone hitting limits
```

`quality="not_in_sources"` is the one to watch: each occurrence is a real
question the knowledge base could not answer, and the fastest guide to what
belongs in `pipeline/sources.py`.

To chart these, build a log-based metric in Cloud Logging on
`jsonPayload.event="ask"`, grouped by `jsonPayload.category`.

If you later want pageview and visitor counts as well, Cloudflare Web Analytics
needs its beacon added explicitly to `frontend/src/app/layout.tsx` — Cloudflare
only auto-injects it for statically proxied sites, and this app's HTML is
rendered by a Worker.

## Tuning

Everything adjustable is in `rag/config.py` and overridable by environment
variable, so the deployed service can be retuned without a rebuild.

| Setting | Default | Effect |
|---|---|---|
| `ANSWER_MODEL` | `gpt-5.4-mini` | Answer quality against cost |
| `CANDIDATES` | 40 | Pulled from Pinecone before reranking |
| `CONTEXT_CHUNKS` | 12 | Passages the model sees |
| `MIN_RELEVANCE` | 0.15 | Below this, the answer is flagged low-confidence |
| `HISTORY_TURNS` | 6 | Conversation turns replayed |

Change one thing, run `python -m eval.run`, compare the means. The prompt in
`rag/prompts.py` is the highest-leverage thing in the repo and the easiest to
make worse — an earlier version had grown to 21 numbered rules that contradicted
each other and hardcoded permit rules the corpus did not support.
