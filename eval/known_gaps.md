# Known coverage gaps

Things the corpus is missing for reasons already diagnosed. Recorded so they are not
rediscovered from scratch. None of these are fixed; each entry says what it would take.

---

## 1. workinfinland.eu returns a JS-rendered shell — zero usable content

**Status:** open. Seeded, crawled, yields nothing.

`workinfinland.eu` has 8 seed URLs in `SEED_URLS` and a `DOMAIN_CONFIGS` entry with
`max_pages: 50`. The 2026-08-27 crawl fetched 9 of its pages successfully — HTTP 200, no
errors — but every single one returned **exactly 279 characters**:

```
17:20:05  workinfinland.eu/en/living-in-finland/banking    (279 chars)
17:20:53  workinfinland.eu/en/living-in-finland/housing    (279 chars)
17:21:30  workinfinland.eu/en/living-in-finland/taxation   (279 chars)
```

Identical length across unrelated pages means the HTML is an app shell and the content is
rendered client-side. Every chunk falls under `MIN_TOKENS = 80` and is dropped, so the
domain appears in neither `all_chunks.json` nor `all_chunks_v2.json`.

**Same failure mode as the original tulli.fi / tyosuojelu.fi zero-yield**, which was worked
around by `scripts/patch_missing_domains.py` rather than diagnosed. Those two now work
(405 and 394 chunks in v2), so whatever broke them was transient or path-specific — but
workinfinland.eu is structurally different: a static fetcher cannot read it at all.

**What it would take:** a headless browser (Playwright) for this domain only, or dropping
the domain from `SEED_URLS` and accepting the gap. It is the official Talent Boost portal,
so the content is genuinely relevant to work-permit questions.

**How to detect this class of failure early:** flag any domain where fetched pages cluster
at an identical small character count. A per-domain "fetched N pages, produced 0 chunks"
warning at the end of a crawl would have surfaced tulli/tyosuojelu months earlier.

---

## 2. Dead migri.fi URLs behind golden-set failures

**Status:** open. Flagged 2026-08-27, not investigated.

These seeds returned HTTP 404 in the 2026-08-27 crawl:

| URL | Why it matters |
|---|---|
| `migri.fi/en/dual-citizenship` | Cited in `source_testing_screenshots.md` §1.3-Q4, one of four false out-of-scope failures. The page that would ground a correct answer is gone. |
| `migri.fi/en/citizenship-by-declaration` | Citizenship path content |
| `migri.fi/en/losing-finnish-citizenship` | Citizenship loss rules |
| `migri.fi/en/identity-investigation` | Identity establishment |
| `migri.fi/en/reception-centers` | Reception system |
| `migri.fi/en/granted` | Post-decision |
| `migri.fi/en/residence-permit-card-on-the-basis-of-temporary-protection` | Superseded by `/residence-permit-card-for-temporary-protection`, which does resolve |

This is a **content gap, not a scraper bug** — the URLs 404 at origin. Migri may have moved
the content rather than removed it; `migri.fi/en/citizenship-declaration` (no "by-") does
resolve and was fetched, so at least one is a rename.

**What it would take:** check each 404 against the live site, map renames into `SEED_URLS`,
and note any genuinely retired content so the eval does not expect answers the corpus cannot
support.

---

## 3. tyomarkkinatori.fi serves Finnish-language news under /en/

**Status:** open. Causes real coverage loss.

`tyomarkkinatori.fi/en/news/*` publishes Finnish-language articles under an `/en/` path, so
the `lang_prefix: "/en/"` filter passes them. Sublink discovery keeps finding them, and
because the domain is **cap-bound at 40 pages**, this Finnish news crowds out the English
guidance pages that are actually useful.

Measured between v1 and v2 for the `te_services` domain tag (201 → 154 chunks):

- **lost**, substantive English guidance: `services-to-support-job-seeking` (34 chunks),
  `tips-for-finding-a-job` (15), `the-rights-and-responsibilities-of-unemployed-job-seekers`
  (6), `registration-as-a-job-seeker` (3), `information-and-guidance-about-unemployment-security` (2)
- **gained**: 13 of 15 new URLs are `/en/news/` with Finnish slugs — `aktivointipalveluissa-olevien-maara-kasvussa`,
  `tyoton-voi-tehda-vapaaehtois-ja-talkootyota`, `korkeakoulujen-syksyn-yhteishaku-alkaa-31-elokuuta`, etc.

Registering as a jobseeker is a precondition for Kela unemployment benefits, so this is
load-bearing content for benefits questions.

**What it would take:** add `"/news/"` to `tyomarkkinatori.fi`'s skip list, or detect
Finnish-language content post-fetch (stopword ratio) and drop it before chunking.

---

## 4. Cap-bound domains churn their page composition between runs

**Status:** by design, but the consequence is worth knowing.

migri, dvv and te_services all hit their `max_pages` caps in both the v1 and v2 crawls —
URL counts are near-identical (migri 249 vs 249, dvv 58 vs 58, te_services 38 vs 40). The cap
is the binding constraint, so *which* pages land in the corpus is decided by BFS discovery
order, which varies run to run.

This means a rebuild does not produce a superset of the previous corpus. It produces a
different sample of the same budget. Between v1 and v2, migri swapped out 20 URLs / 129
chunks and swapped in 20 URLs / 100 chunks with no scraper change involved.

**Consequence:** never assume a rebuild preserves a page that was present before. If a
specific page matters (e.g. one an eval case depends on), it needs to be pinned in
`SEED_URLS` and the cap raised, or discovery needs to be ordered by relevance rather than
BFS.
