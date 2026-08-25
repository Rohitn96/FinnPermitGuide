# Golden-set source material: `Testing/*.png`

Transcribed from the 15 manual-test screenshots recovered from git
(`git show HEAD:Testing/<file>.png`, verified byte-identical to their git objects).
These are the only surviving record of the manual QA passes — the live query logs in
`logs/*.jsonl` were written to Cloud Run's ephemeral filesystem and did not survive.

**Purpose.** Raw input for the step-4 golden-set eval harness. Each turn gives the user
question, the key factual assertions the system made, the facts a correct answer must
contain, and any rule violation visible in the screenshot. The defect taxonomy at the end
aggregates recurring failure modes.

**Provenance.** These screenshots predate the MMR fix (commit 83d503f), so every answer was
produced by a system retrieving at most 4 topic-boost chunks — and zero chunks for questions
with no `TOPIC_BOOST` entry. Treat the recorded answers as a *baseline to beat*, never as
expected output.

**Transcription confidence.** High for 1.1–1.9 and 2.2–2.5. Lower for 2.1, captured at a much
smaller render scale; figures from it are marked low-confidence.

**Rule references** point at the numbered rules in `SYSTEM_PROMPT` in `rag/chain.py`.

---

## 1.1 — Aalto master's graduate, continuous A permit, PR eligibility

Persona: arrived 2020 on a student permit, master's at Aalto 2022, job-search permit,
continuous A permit since early 2023, full-time employment, ~4.5 years in Finland.

### 1.1-Q1 [Permanent Residence] (1 source)
**Q:** What are my options for permanent residence and am I close to qualifying?
**Asserted:** Qualifies if (1) at least 4 years in Finland on a continuous A permit,
(2) sufficient financial resources, (3) language skills requirement at "developing level A2",
where a master's completed in Finland is relevant; mentions the YKI test or 15 credits of
Finnish/Swedish study.
**Expected facts:** 4 years continuous residence; A2 language level; financial resources.

### 1.1-Q2 [Study] (2 sources)
**Q:** I passed YKI at B1 but my master's was taught in English. Does that satisfy the
language condition, or does the master's path need a higher level?
**Asserted:** The requirement for that path is A2; B1 is higher than A2, so it is met.
**Expected facts:** A2 required; B1 satisfies it.
**Note:** Correct CEFR ordering — keep as a positive regression case.

### 1.1-Q3 [General] (2 sources)
**Q:** What documents will I need to gather and submit for the PR application?
**Asserted:** Deflection phrase ("I don't have enough official information...").
**DEFECT:** Deflected with 2 sources attached. Rule 2 states document questions are always in
scope and must be answered from whatever chunks exist.

### 1.1-Q4 [General] (2 sources)
**Q:** My A permit expires in 8 months. Renew first, or apply for PR directly?
**Asserted:** Must still meet continuous-permit requirements when applying; "it is advisable
to renew your A permit before applying".
**DEFECT:** "it is advisable to" — Rule 13 forbids advice framing.

---

## 1.2 — Startup entrepreneur, irregular income, Kela benefits, family

Persona: 2 years in Finland on a startup entrepreneur permit, uneven business income, spouse
on a family reunification permit, 3-year-old child born in Finland.

### 1.2-Q1 [Benefits] (3 sources)
**Q:** (top of capture cut) Kela entitlements on a low, irregular entrepreneur income.
**Asserted:** May be eligible for general housing allowance if income is low enough; may be
entitled to child benefit; may apply for income support if income does not cover expenses.
Irregular income is assessed case by case.
**DEFECT:** Closes with "verify at migri.fi" for a wholly Kela question. Rule 10 routes
benefits to kela.fi.

### 1.2-Q2 [Family] (2 sources)
**Q:** Can my spouse apply for basic unemployment allowance or social assistance
independently, or does my business income count against their application?
**Asserted:** The spouse may apply independently, but household income is considered. Income
is not sufficient if based on social assistance, labour market subsidy, basic unemployment
allowance or general social security benefit.
**DEFECT:** Attributed to Migri and routed to migri.fi; this is Kela's rule.

### 1.2-Q3 [Family] (2 sources)
**Q:** Is child benefit automatic for our 3-year-old, and does permit type affect it?
**Asserted:** Not automatic — it must be applied for. Permit type (startup entrepreneur /
family reunification) should not affect eligibility.
**Expected facts:** Child benefit requires an application; residence in Finland is the test.

### 1.2-Q4 [Family] (2 sources)
**Q:** If my startup permit is not renewed, what happens to my spouse's permit and my child's
status?
**Asserted:** A family member's permit is typically tied to the primary holder's status; the
spouse may need to apply on independent grounds; a child born in Finland generally has the
right to reside, depending on the parents' permits.

---

## 1.3 — Citizenship with a 5-month absence, criminal record, dual citizenship

Persona: in Finland since 2017, 5-month absence in 2021 during which the permit expired,
continuous A permit since returning, full-time work, YKI B1 in 2023, ~8 years total.

### 1.3-Q1 [Citizenship] (1 source)
**Q:** Am I eligible for citizenship, and does the 5-month gap break continuous residence?
**Asserted:** Absence should not exceed 6 months during the required period, so a 5-month gap
does not break continuity. Lists: over 5 years of residence, a continuous permit, YKI B1.
**Expected facts:** 5-year residence requirement; B1 language; absence threshold.
**Watch:** the "6 months" figure must appear verbatim in a chunk — flag if it does not.

### 1.3-Q2 [General] (2 sources)
**Q:** If the gap does break continuity, when does the clock reset and how many years do I
need from that point?
**Asserted:** Deflection phrase.
**DEFECT:** Deflected with 2 sources attached.

### 1.3-Q3 [Citizenship] (2 sources)
**Q:** Does a 2019 minor traffic offence with a fine and no imprisonment affect my
citizenship application?
**Asserted:** A criminal record can affect the application; imprisonment matters most; a minor
fine is generally considered less serious.

### 1.3-Q4 [out_of_scope] (0 sources)
**Q:** Can I hold dual citizenship if I naturalise as Finnish?
**Asserted:** "This is outside MigriGuide's scope."
**DEFECT — SEVERE:** Rule 9 lists dual citizenship and the right to hold two passports as
ALWAYS in scope. False out-of-scope rejection.

---

## 1.4.1 / 1.4.2 — Specialist permit, EUR 6,200/month, arrival logistics and tax

Persona: senior software engineer arriving from India on a specialist work permit,
EUR 6,200/month, never lived in Finland before.

### 1.4-Q1 [Registration] (2 sources)
**Q:** Walk me through everything in the first 30 days — permit registration, tax, DVV,
social security — in order.
**Asserted:** Seven steps: (1) register the residence permit at police/Migri within 30 days;
(2) register the address with DVV within a week of moving in; (3) apply for a tax card from
Vero; (4) register with Kela with proof of employment; (5) open a Finnish bank account;
(6) familiarise yourself with local services; (7) consider Finnish language courses.
**Expected facts:** DVV address registration; Vero tax card; Kela registration.
**DEFECT — HIGH VALUE:** Steps 5–7 are exactly the padding Rule 17 names verbatim ("open a
Finnish bank account", "consider language learning"). Ideal regression case.

### 1.4-Q2 [Work] (2 sources)
**Q:** What tax rate on EUR 6,200/month — a flat rate for foreign specialists, or progressive?
**Asserted:** Staying over 6 months means taxable in Finland; "no flat rate specifically
mentioned"; progressive tax applies.
**DEFECT:** "According to Migri" for a tax fact, routed to migri.fi. Rule 10 routes tax to
vero.fi. Also check against the key-employee flat-rate regime for foreign specialists.

### 1.4-Q3 [Work] (2 sources)
**Q:** What is a "tax at source" arrangement and is it better than progressive tax at my
salary level?
**Asserted:** Withholding at a fixed rate, typically for short stays or non-residents; which
is better depends on income and circumstances; "it is advisable to consult the Finnish Tax
Administration or verify at migri.fi".
**DEFECT:** Advice framing (Rule 13) plus tax routed to migri.fi (Rule 10).

### 1.4-Q4 [Work] (2 sources)
**Q:** When does Kela coverage start — is there a waiting period before public healthcare?
**Asserted:** Registering residence may confer entitlement; emergency and essential care are
available immediately; full benefits typically after one year of residence.
**Watch:** the "one year" figure needs verbatim chunk support.

---

## 1.5 — Non-EU spouse of an EU citizen

Persona: Moroccan, married to a French citizen employed in Helsinki for 2 years, arrived 4
months ago, no permit or residence card applied for.

### 1.5-Q1 [Registration] (1 source)
**Q:** What is my current legal status, and am I living here legally with no document?
**Asserted:** As the spouse of an EU citizen there is a right to reside, but status is
"uncertain" without a document; should apply for a residence card.

### 1.5-Q2 [Family] (2 sources)
**Q:** Is the residence card mandatory or just declaratory? What if I get a police check?
**Asserted:** "It is mandatory to apply for this residence card to formalise your legal
status."
**DEFECT:** Advice framing (Rule 13). Also verify the mandatory-vs-declaratory claim — under
EU free movement law the card is generally declaratory of a right that already exists.
Potential factual error; high-value eval case.

### 1.5-Q3 [Family] (2 sources)
**Q:** If my husband returns to France before I reach 5 years, does my residence right
disappear?
**Asserted:** The derived right is linked to the EU citizen's residence and may cease if he
leaves; an independent basis should be obtained.

### 1.5-Q4 [Family] (2 sources)
**Q:** If I switch to a continuous permit in my own right based on employment, does time
already spent as an EU family member count toward the 4-year PR requirement?
**Asserted:** Yes — time already spent counts, the clock does not restart, provided other
requirements are met.
**Expected facts:** 4-year PR requirement; continuity across a change of basis.

---

## 1.6 — Mixed off-topic message (single turn)

**Q:** "I'm german, planning to visit finland in december, my girlfriend lives there, will i
require a visa? what will the weather be like this year? what should i bring along?"
**Asserted:** "This is outside MigriGuide's scope."
**DEFECT — SEVERE:** Rule 8 requires answering the immigration part (a German citizen needs no
visa — EU free movement) and appending one sentence declining the weather and packing parts.
The whole message was rejected instead.

---

## 1.7 — Wrong salary assumption, freelance rights, pet import, employer bankruptcy

Persona: Filipino UX designer, job offer at EUR 2,800/month, believes the minimum is
EUR 2,000/month.

### 1.7-Q1 [Work] (2 sources)
**Q:** Confirm I meet the income requirement (I read the minimum is EUR 2,000/month) — and
which Helsinki neighbourhoods are best for young professionals?
**Asserted:** "You qualify under the income requirement"; salary must meet the collective
agreement minimum; "since your salary exceeds the minimum requirement, you meet this
condition". Declines the neighbourhood question.
**DEFECT — HIGH VALUE:** Rule 4 requires explicitly correcting the user's EUR 2,000 figure,
which does not appear in official sources. Instead the answer implicitly confirmed it, then
asserted the threshold was met without quoting any verbatim figure (Rule 5).

### 1.7-Q2 [Work] (2 sources)
**Q:** Can I freelance for clients outside Finland, and what is a "collective agreement"?
**Asserted:** A permit for an employed person is "granted for the field of employment to which
your job belongs", therefore "your work permit ties you exclusively to the employer".
A collective agreement sets sector minimum pay and conditions.
**DEFECT:** Internally contradictory — a field-restricted permit is not an employer-exclusive
one. Verify which is correct for TTOL permits.

### 1.7-Q3 [Work] (2 sources)
**Q:** Pet import rules for my dog, and what happens to my permit if my employer goes bankrupt
6 months after I arrive?
**Asserted:** Deflection for pet import, routed to migri.fi. For job loss: "you typically have
a limited time to find a new job"; "the specific duration is not detailed in the provided
chunks".
**DEFECT — HIGH VALUE:** Rule 15 requires stating the grace period explicitly and precisely
(3 months on an employer-tied TTOL permit, 6 months on a continuous A permit). Also pet import
belongs to tulli.fi, not migri.fi (Rule 10).

---

## 1.8 — Nurse, A1 exemption claim, refused application, PR to citizenship

Persona: 3 years 8 months in Finland on a continuous A permit, nurse at a public hospital, no
language test taken, told by a colleague that healthcare workers need only A1.

### 1.8-Q1 [Permanent Residence] (2 sources)
**Q:** Is A1 enough because healthcare workers get an exemption, and can I apply for PR now or
must I wait until 4 years?
**Asserted:** Does not yet qualify — at least 4 years on a continuous A permit is required.
The chunks mention no healthcare-worker exemption for A1. For an application after
8 January 2026 the language requirement depends on the application path; the work-history path
would need B1 with at least 6 years of residence.
**Expected facts:** 4-year minimum; no A1 healthcare exemption; path-dependent language level.
**Note:** Correctly rejects the user's false premise — positive Rule 4 regression case.

### 1.8-Q2 [out_of_scope] (0 sources)
**Q:** Migri refused my application over a passport photo that was accepted before. Did they
err, should I sue? And separately, what is the process and deadline for appealing a refused PR
application?
**Asserted:** "This is outside MigriGuide's scope."
**DEFECT — SEVERE:** Rule 9 lists appeals against Migri decisions as always in scope. The
appeal process and deadline should have been answered, with only the "should I sue" part
declined per Rule 8.

### 1.8-Q3 [Citizenship] (2 sources)
**Q:** After PR, can I apply for citizenship immediately? And does a salary increase to
EUR 4,200 affect an ongoing PR application?
**Asserted:** Citizenship generally requires 5 years total, counting A-permit and PR time, so
there is a separate wait. Income does not apply when applying on years of residence; it would
matter on an income basis "for example, if you needed to show that your annual income is more
than EUR 40,000".
**Watch:** the EUR 40,000 figure needs verbatim chunk support — otherwise a Rule 5 violation.

---

## 1.9 — Brazilian spouse of a Finnish citizen, degree recognition, sponsoring a parent

Persona: Brazilian, married to a Finnish citizen, currently in Finland on a tourist entry
expiring in 3 weeks, qualified dentist with 8 years of experience.

### 1.9-Q1 [out_of_scope] (0 sources)
**Q:** My husband says that because he is Finnish I automatically get EU free movement rights
like a French or German spouse. Is he right? What permit do I need, and can I apply from
inside Finland before my tourist entry expires?
**Asserted:** "This is outside MigriGuide's scope."
**DEFECT — SEVERE:** Rule 9 lists "spouse or family member of a Finnish citizen applying for a
permit" as always in scope. Also a missed Rule 4 correction: a Finnish citizen residing in
Finland does not trigger EU free movement rules for family members; national law applies.

### 1.9-Q2 [Registration] (2 sources)
**Q:** Will my Brazilian dental degree be recognised automatically or must I go through
Valvira? And what Kela benefits am I entitled to as the spouse of a Finnish citizen?
**Asserted:** Not automatic — recognition must go through Valvira, the National Supervisory
Authority for Welfare and Health. Kela entitlement may depend on employment status; routed to
kela.fi.
**Note:** Correct source routing here — positive Rule 10 regression case.

### 1.9-Q3 [Family] (2 sources)
**Q:** Can I sponsor my 68-year-old mother with no income, what income must I show, and does
her Type 2 diabetes affect a family reunification application?
**Asserted:** A long-term permit for a parent as a family member is possible subject to the
income requirement; income cannot be based on social assistance, labour market subsidy, basic
unemployment allowance or general social security benefit. A health condition does not
directly affect the application.
**Expected facts:** Income requirement applies; excluded income types; health not a bar.

---

## 2.1 — Nigerian PhD, job-search permit, PR (low-confidence transcription)

Persona: arrived 2019 on a student permit for a PhD at University of Helsinki, thesis March
2025, job-search permit to September 2025, postdoc offer at EUR 3,400/month, 6 years total by
August.

### 2.1-Q1 [Permanent Residence] (2 sources)
**Q:** Can I apply for PR directly from a job-search permit, or must I switch to a work permit
and wait more years? Also, best area to live near campus?
**Asserted:** Can apply directly, having 6 years of residence, a postdoc position, and meeting
the work-history requirement; must meet at least B1 Finnish or Swedish.
**DEFECT:** The off-topic housing question was silently dropped rather than declined in one
sentence (Rule 8).

### 2.1-Q2 [Work] (2 sources)
**Q:** Is there an "academic fast track" needing only 2 years instead of 4? And do my student
permit years count?
**Asserted:** "The information from your friend does not appear in the official sources."
At least 4 years on a continuous permit is required; "your years on a student permit do not
count towards this requirement".
**DEFECT — HIGH VALUE:** Rule 20 states that ALL A-permit types count toward the 4-year total,
explicitly including student permits. Direct contradiction between prompt rule and answer;
resolve which is correct against the corpus.
**DEFECT:** Answer ends "verify at [source]" — a literal unfilled placeholder.

### 2.1-Q3 [Citizenship] (2 sources)
**Q:** Does a 2-week trip to Stockholm to renew my passport break continuous residence, and
can I re-enter on a job-search permit?
**Asserted:** A 2-week trip does not break continuity provided you return; re-entry rights
should be verified since the permit is not a Schengen visa.
**DEFECT:** Literal "[source]" placeholder. Category mislabelled Citizenship for a travel/PR
question (should be permanent per the Rule 21 edge cases).

### 2.1-Q4 [General] (2 sources)
**Q:** Can my unmarried partner of 3 years come on a cohabitation basis, what must we prove,
and does Finland recognise same-sex partnerships for immigration?
**Asserted:** A permit based on cohabitation is possible; evidence such as a shared lease or
joint bank account, photos and communication records, other documentation of a long-term
relationship. Finland recognises same-sex relationships for immigration on the same terms.
**DEFECT:** Literal "[source]" placeholder. Omits the two-year cohabitation requirement —
verify against the corpus.

---

## 2.2 — Ukrainian temporary protection to work permit, family, travel

Persona: holds a temporary/humanitarian permit, has worked unofficially, employer willing to
formalise, prospective salary EUR 2,200/month, 72-year-old mother in Russia.

### 2.2-Q1 [Work] (1 source)
**Q:** (top cut) Will my unofficial work history cause problems in switching to a work permit?
**Asserted:** May qualify; can apply from within Finland on a valid permit; unofficial work
history may complicate the application; disclose everything; employer must supply documents.

### 2.2-Q2 [Temporary Protection] (3 sources)
**Q:** What is the difference between temporary protection status and the humanitarian
protection permit I hold, and do they carry different rights?
**Asserted:** "Note: official sources differ on this point — check migri.fi for the current
rule."
**DEFECT — HIGH VALUE:** Rule 14 restricts the contradiction response to two chunks that
contradict each other on the same specific fact, and explicitly says NOT to use it when
sources describe different but related programmes — which is exactly this case. The answer
should have explained the distinction.

### 2.2-Q3 [Work] (3 sources)
**Q:** Can I sponsor my mother, is EUR 2,200/month enough, what documents does the work permit
need, and what must my employer do?
**Asserted:** Sponsorship possible with a valid permit and sufficient income; the specific
threshold must be verified. Lists passport, job offer or employment contract, proof of
qualifications and experience. Employer submits a job offer and may need to show labour-law
compliance.
**DEFECT:** Ends with "Your next steps could be: 1. ... 2. ..." — Rule 17 explicitly bans a
next-steps section. Also a literal "[source]" placeholder.

### 2.2-Q4 [Permanent Residence] (sources not visible)
**Q:** With permanent residence, can I travel to Russia to visit my mother, and how many days
a year may I spend outside Finland?
**Asserted:** Should not be outside the EU for more than 12 consecutive months or the permit
may be lost.
**DEFECT:** "Your next steps could be" again, plus a "[source]" placeholder.
**Watch:** the 12-month figure needs verbatim chunk support.

---

## 2.3 — Indian remote worker, overstay, tax residency, salary threshold

Persona: Indian national working remotely for a UK company paid in GBP, physically in Finland
7 months, Schengen tourist visa expired 4 months ago, believes remote work exempts him.

### 2.3-Q1 [Overstay] (2 sources)
**Q:** I work for a British company and get paid in the UK, so I don't need a Finnish work
permit and I'm not a Finnish tax resident — correct? My friend says the 90/180 rule doesn't
apply to remote workers. Also recommend co-working spaces in Helsinki.
**Asserted:** Needs a residence permit to stay longer; should register with Vero and get a tax
card as tax residency may apply; consider consulting Migri about legalising the stay.
**DEFECT — HIGH VALUE:** Rule 4 requires explicitly correcting both false premises (the remote
work exemption and the 90/180 claim). Neither was corrected. Overstay consequences were not
addressed, and the co-working question was not declined per Rule 8.

### 2.3-Q2 [Tax] (4 sources)
**Q:** What are my options now — can I leave voluntarily and re-enter with the right permit,
would the overstay affect future applications, and what tax would I owe on GBP 4,000/month?
**Asserted:** Voluntary departure is possible; the overstay may affect future applications;
"it is advisable to consult the Finnish Immigration Service"; the tax amount depends on
deductions and the progressive rate, "not detailed in the provided chunks".
**DEFECT:** Advice framing (Rule 13) and a "[source]" placeholder.

### 2.3-Q3 [Work] (3 sources)
**Q:** If my UK company opens a Finnish subsidiary and hires me, what permit and what is the
exact minimum salary for an IT role? I want the number, not "it depends".
**Asserted:** A residence permit for an employed person (TTOL); "the minimum salary
requirement for a residence permit for an employed person is EUR 1,500 per month", with a
link to migri.fi/en/residence-permit-for-an-employed-person.
**DEFECT — CRITICAL EVAL CASE:** A specific EUR threshold stated as fact. Rule 5 forbids this
unless the figure appears verbatim in a retrieved chunk. This is the single most important
hallucination check for the golden set.

### 2.3-Q4 [Work] (2 sources)
**Q:** Once legal with a work permit, how long until PR, and does time spent here illegally
count?
**Asserted:** 4 years on a continuous A permit; illegal time does not count; the clock starts
from the date the proper permit is received.
**Expected facts:** 4-year requirement; unlawful residence excluded.

---

## 2.4 — Australian with a Finnish grandmother, citizenship by declaration

Persona: Australian, 37, grandmother was a Finnish citizen who lost it on naturalising in
Australia, master's from an Australian university, no Finnish, Vietnamese wife and a
5-year-old daughter born in Australia.

### 2.4-Q1 [Citizenship] (1 source)
**Q:** (top cut) Do I qualify for citizenship by declaration through my grandmother?
**Asserted:** "You may qualify for Finnish citizenship by declaration", then lists declaration
categories that all turn on a Finnish **parent**, not a grandparent.
**DEFECT:** The stated criteria do not support the conclusion for a grandchild. Verify whether
descent by declaration extends beyond one generation; likely a false positive.

### 2.4-Q2 [Study] (3 sources)
**Q:** If declaration doesn't apply, what is the realistic timeline and full requirements to
naturalise, including language?
**Asserted:** 5 years on a continuous A permit; satisfactory Finnish or Swedish at B1;
"Integration Requirement: You must have a valid reason for wanting to become a citizen";
timeline at least 5 years.
**DEFECT:** Markdown bold (`**Residence Requirement**`) in the answer body — Rule 11 forbids
all markdown. Category mislabelled Study for a citizenship question. The "valid reason for
wanting to become a citizen" requirement appears fabricated — verify.

### 2.4-Q3 [Citizenship] (3 sources)
**Q:** Would naturalising cost me my Australian citizenship, what does Finnish law say about
two passports, and could I then work anywhere in the EU?
**Asserted:** Finland accepts multiple citizenship, so Australian citizenship is not
automatically lost; Finnish citizenship confers the right to live and work across the EU.
**Expected facts:** Finland permits dual citizenship; EU free movement follows citizenship.

### 2.4-Q4 [Permanent Residence] (sources not visible)
**Q:** What status would my Vietnamese wife get, and does my daughter get Finnish citizenship
automatically through me?
**Asserted:** The wife may apply on family ties subject to requirements possibly including
financial resources and language; the daughter may be eligible for citizenship by declaration.
**DEFECT:** Markdown bold again (Rule 11).

---

## 2.5 — Startup entrepreneur, Kela rejection and appeal, business failure, marriage

Persona: 3 years on a startup entrepreneur permit, ~EUR 900/month income, general housing
allowance rejected by Kela, business failing, marrying a Finnish woman next month.

### 2.5-Q1 [Benefits] (2 sources)
**Q:** Am I actually entitled to housing allowance, what is the income threshold, and which
Finnish law is Kela basing the rejection on so I can challenge it?
**Asserted:** Permit type can affect Kela benefits; "the income threshold ... is not specified
in the chunks provided"; the governing laws are not in the chunks either.
**DEFECT:** Literal "[source]" placeholder instead of routing to kela.fi (Rule 10).

### 2.5-Q2 [Benefits] (3 sources)
**Q:** The rejection letter is dated 3 weeks ago with a 30-day appeal deadline and I only just
received it. Do I still have time, and how does the appeal work?
**Asserted:** 30 days from the date of the letter, so roughly 1 week remains; follow the
instructions in the letter; include personal details, the decision appealed and supporting
documents; appeals generally go to Kela.
**Note:** The date arithmetic is correct — positive regression case for Rule 5 calculations.

### 2.5-Q3 [Benefits] (3 sources)
**Q:** If I close the company and become unemployed, what can I claim immediately and what has
a waiting period? What happens to my entrepreneur permit?
**Asserted:** Basic unemployment allowance typically requires unemployment fund membership and
contributions; waiting periods vary; the entrepreneur permit ceases to be valid without an
active business; "typically, you would have a grace period of 3 months to apply for a new
permit".
**Watch:** the 3-month grace period needs verbatim chunk support (Rule 15 names 3 months for
TTOL and 6 for a continuous A permit — confirm which applies to a startup permit).

### 2.5-Q4 [Family] (4 sources)
**Q:** After marrying a Finnish citizen can I switch to family ties, what income must she show,
can we apply from inside Finland, and should I close the company first?
**Asserted:** Can switch after marriage; "your Finnish spouse must meet the income
requirement", threshold not detailed; can apply from inside Finland; "it is generally
advisable to close your company before you apply".
**DEFECT:** Advice framing (Rule 13) and a "[source]" placeholder.
**DEFECT — HIGH VALUE:** The spouse of a Finnish citizen is generally exempt from the income
requirement. Asserting the requirement applies is a likely factual error with direct
consequences for the user.

---

# Defect taxonomy

Aggregated across the 15 screenshots (~50 turns). Ordered by eval priority.

| # | Failure mode | Rule | Occurrences |
|---|---|---|---|
| 1 | Unverified EUR / duration figures stated as fact | 5 | EUR 1,500 (2.3-Q3), EUR 40,000 (1.8-Q3), 3-month grace (2.5-Q3), 12-month EU absence (2.2-Q4), 6-month absence (1.3-Q1), 1-year Kela wait (1.4-Q4) |
| 2 | Literal `[source]` placeholder leaked into answer text | 18 | 2.1 ×3, 2.2 ×2, 2.3 ×2, 2.5 ×4 |
| 3 | False out-of-scope on an explicitly in-scope topic | 9 | dual citizenship (1.3-Q4), appeals (1.8-Q2), spouse of a Finn (1.9-Q1), EU visitor visa (1.6) |
| 4 | Advice framing — "it is advisable", "your next steps" | 13, 17 | 1.1-Q4, 1.4-Q3, 1.5-Q2, 2.2-Q3, 2.2-Q4, 2.3-Q2, 2.5-Q4 |
| 5 | Failure to correct a false user premise | 4 | EUR 2,000 minimum (1.7-Q1), remote-work exemption and 90/180 (2.3-Q1) |
| 6 | Wrong official source routing | 10 | Kela to migri.fi (1.2-Q1, 1.2-Q2), tax to migri.fi (1.4-Q2, 1.4-Q3), pet import to migri.fi (1.7-Q3), Kela with no route (2.5-Q1) |
| 7 | Grace period not stated when job loss raised | 15 | 1.7-Q3 |
| 8 | Padding — bank accounts, language courses, next steps | 17 | 1.4-Q1 |
| 9 | Contradiction response misapplied to related programmes | 14 | 2.2-Q2 |
| 10 | Deflection despite retrieved sources | 2 | 1.1-Q3, 1.3-Q2 |
| 11 | Markdown formatting in answer body | 11 | 2.4-Q2, 2.4-Q4 |
| 12 | Category mislabelled | 21 | travel to citizenship (2.1-Q3), citizenship to study (2.4-Q2), Kela to family (1.2-Q2) |
| 13 | Internally contradictory claim | 1 | field-restricted vs employer-exclusive permit (1.7-Q2) |
| 14 | Likely factual errors needing corpus adjudication | — | student years counting toward PR (2.1-Q2 vs Rule 20), residence card mandatory vs declaratory (1.5-Q2), income requirement for a Finnish citizen's spouse (2.5-Q4), citizenship by declaration via grandparent (2.4-Q1) |

## Positive regression cases

Behaviours to preserve; these were correct.

- 1.1-Q2 — CEFR ordering: B1 satisfies an A2 requirement.
- 1.8-Q1 — Correctly rejected the false "A1 exemption for healthcare workers" premise.
- 1.9-Q2 — Correct routing of a Kela question to kela.fi, and correct Valvira answer.
- 2.5-Q2 — Correct date arithmetic on a 30-day appeal deadline.
- 2.1-Q2 — Correctly flagged that a friend's claim does not appear in official sources.
