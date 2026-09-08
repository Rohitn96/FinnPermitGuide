# Known coverage gaps

Things the knowledge base does not cover, and why. Recorded so they are not
rediagnosed from scratch every few months. Each entry says what closing it would
take.

Last reviewed: 2026-09-08.

---

## Open

### 1. workinfinland.eu cannot be crawled

The official Talent Boost portal renders entirely client-side. Every page
returns an identical ~279-character HTML shell, so a static fetcher extracts
nothing — it was seeded and crawled for months while contributing zero chunks.

It is now listed in `EXCLUDED` in `pipeline/sources.py` rather than silently
failing. Closing this needs a headless browser for that one domain.

The crawler now logs `ZERO YIELD` for any domain that fetches pages but extracts
none, so this class of failure surfaces during the crawl instead of months later
as a topic the assistant cannot answer.

### 2. Some domains are still cap-bound

When a domain hits its `max_pages` limit, the page limit — not the site — decides
what ends up in the corpus, and discovery order varies between runs. A rebuild
then produces a *different sample*, not a superset.

As of the 2026-09-08 crawl the following finished at their cap with pages still
queued: `dvv.fi` (100, 108 queued), `tyosuojelu.fi` (110, 270 queued),
`tulli.fi` (70, 15 queued), `vero.fi` (120, 11 queued).

The queued remainder on tyosuojelu and dvv is mostly deep procedural material of
low relevance to immigration questions, so this is a deliberate budget rather
than a defect. Raise the cap in `sources.py` if evals start failing on those
topics. Anything an eval case depends on should be pinned in `SEEDS` rather than
left to discovery.

### 3. Two-part questions spanning two authorities cite only one

**Status:** open, measured, intermittent.

When a question has halves belonging to different agencies — "what Kela benefits
can I claim on an entrepreneur permit, and can my spouse apply for social
assistance?" or "how do I extend my permit, and how do I get a tax card?" — the
rewritten query is dominated by one half's vocabulary. The reranker then fills
most slots from that authority, and the answer draws its facts from one site
while merely *pointing* at the other.

The answers are not wrong: they answer both halves and route the reader to the
right authority. They just cite one source set, so `expect_domains` in
`eval/cases.json` fails on `mixed-permit-and-tax` and
`entrepreneur-irregular-income-kela` on maybe half of runs.

Partly mitigated by `MAX_PER_SOURCE` in `rag/config.py`, which stopped a single
long page taking 7 of 12 context slots and was why Kela passages previously
never made it in at all. The remainder is a ranking problem, not a coverage one:
the right passages are in the candidate pool and rank just below the cut.

**What it would take:** retrieve separately per sub-question and merge, which is
what the old `_multi_query_retrieve` did. That was removed because it was
entangled with a 15-topic keyword table that misrouted more often than it
helped. A clean version — split only when the question genuinely has multiple
parts, one extra retrieval, no keyword table — would close this. Weigh it
against the extra latency and the second decomposition call.

**Do not** fix this by relaxing the eval assertion. Citing the authority you
took a fact from is the property that makes the answers auditable.

### 4. Some Finnish questions are still answered in English

**Status:** open, much improved, not closed.

The site invites questions in any language, and until 2026-09-08 Finnish
questions were answered in English every time. Three things were wrong: the
answering model was never told which language to use, the instruction it did
have was awkwardly worded, and `eval/cases.json` declared `expect_language`
while `eval/run.py` never checked it — so the failure was invisible.

Now `rewrite()` returns the detected language alongside the query, and
`_generate()` puts an explicit directive at the very top of the system prompt.
Placement turned out to matter more than wording: the identical instruction
appended after the source passages was ignored, because by then the model had
read a screen of English. Arabic obeyed from either position. Finnish only
obeys from the top.

Measured after the fix: 3 of 4 sample Finnish questions answer in Finnish,
against 0 of 4 before. The holdout is the processing-times question, which
retrieves heavily numeric English content — `finnish-language-question` in the
golden set uses exactly that question and still fails, deliberately, so the
limitation stays visible rather than being quietly dropped.

**What it would take:** likely a separate translation pass over the finished
answer when the target language is not English, rather than asking one call to
retrieve, reason and translate at once. Costs a third model call on non-English
questions only.

### 5. te-palvelut.fi has been decommissioned

`toimistot.te-palvelut.fi` no longer resolves in DNS, and `te-palvelut.fi`
serves a single page with no navigable links. Finland's employment services
moved to `tyomarkkinatori.fi` (Job Market Finland), which is crawled and
contributes the jobseeker-registration content that Kela unemployment answers
depend on.

Both te-palvelut entries were removed from `sources.py`. Nothing is lost, but
if a jobseeker topic goes missing, that migration is the place to look.

---

## Closed

### migri.fi dead seed URLs — fixed 2026-09-08

`/dual-citizenship`, `/citizenship-by-declaration`, `/losing-finnish-citizenship`,
`/identity-investigation`, `/reception-centers` and `/granted` all return 404 at
origin. Migri reorganised its citizenship section; `/citizenship-application` and
`/finnish-citizenship` carry that content now and are seeded in their place.

The `dual-citizenship` case in `eval/cases.json` guards this — it was one of the
false out-of-scope failures in the original manual QA pass.

### tyomarkkinatori.fi Finnish news crowding out English guidance — fixed

`/en/news/` and `/en/careerstories/` publish Finnish-language articles under an
English path, so the `lang_prefix` filter passed them. Under a page cap they
displaced the English jobseeker guidance entirely. Both are now in the domain's
skip list.

### Off-topic authority content — fixed 2026-09-08

The police and customs sites cover far more than immigration. Crawls were
pulling in gambling licences, firearms permits and commercial import procedure,
which then competed for retrieval slots. `poliisi.fi` now skips licensing paths
and `tulli.fi` skips `/businesses/`.

### Hardcoded permit rules in the prompt — fixed 2026-09-08

The previous system prompt asserted "a TTOL employer-tied work permit gives 3
months to find a new employer; a continuous A permit gives 6 months" as a rule
the model had to state. The corpus does not support it — Migri's actual rule
turns on how long the permit has been held. The model was reciting the prompt
over the sources.

Removing it is why the `job-loss-grace-period` eval case checks that the number
comes from a retrieved source rather than asserting a specific figure.
