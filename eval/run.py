"""
Golden-set evaluation.

    python -m eval.run                      # run every case
    python -m eval.run --index NAME         # against a specific Pinecone index
    python -m eval.run --case job-loss      # one case, printed in full

Two layers of checking, split by what each is actually good at.

  Mechanical  — deterministic assertions: expected phrases, expected category and
                source authority, banned phrasing, and every figure in the answer
                verified against the retrieved text by string matching.

  Judged      — a model scores the qualitative dimensions only: completeness,
                usefulness and format. It does NOT grade factual grounding.

That split is deliberate and was learned the hard way. Asked to verify figures
against a dozen long passages, the judge repeatedly reported correctly-sourced
numbers as invented — it skims instead of searching. Numeric grounding is the
one thing here that must not produce false readings, so it is string matching.

Ungrounded figures are the failure that matters. An invented income threshold or
appeal deadline is worse than no answer, because someone will act on it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Answers come back in whatever language the user wrote in, and Windows consoles
# still default to cp1252. Without this, printing a Finnish answer crashes the run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Numeric grounding uses the same code the answer pipeline guards itself with,
# so the test and production can never disagree about what counts as grounded.
# Bound in main(), NOT imported here: importing anything from `rag` executes the
# package __init__, which reads PINECONE_INDEX_NAME at import time. Doing that
# before main() applies --index silently evaluates the wrong corpus.
ungrounded_figures = None
is_finnish = None

CASES = Path(__file__).resolve().parent / "cases.json"

# Phrases the answer must never contain. Each one is a defect seen in a real
# screenshot from a previous version.
BANNED = [
    (r"\[source\]",                          "unfilled [source] placeholder"),
    (r"\byou should\b",                      "advice framing ('you should')"),
    (r"\bit is advisable\b",                 "advice framing ('it is advisable')"),
    (r"\bI recommend\b",                     "advice framing ('I recommend')"),
    (r"\bwe recommend\b",                    "advice framing ('we recommend')"),
    (r"\bnext steps\b",                      "banned 'next steps' section"),
    (r"\byour action items\b",               "banned action-items section"),
    (r"^\s*#{1,6}\s",                        "markdown heading (format rule)"),
    (r"```",                                 "code block (format rule)"),
    (r"\bchunk(s)?\b",                       "leaked internal vocabulary ('chunk')"),
    (r"\bcontext block\b",                   "leaked internal vocabulary"),
    (r"\bresponse_type\b|\banswer_quality\b", "leaked schema field name"),
]

DEFLECTION = re.compile(
    r"don't have enough (official )?information|do not have enough (official )?information",
    re.IGNORECASE,
)

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-5.4-mini")

JUDGE_SYSTEM = """\
You are grading an answer from a Finnish immigration assistant that must answer only from \
the official source extracts it was given.

Every numeric figure in the answer has ALREADY been verified against the extracts \
automatically. Do not re-check numbers, dates or thresholds, and never report a figure as \
unsupported — that check is not yours to make here, and you will get it wrong.

Score these three dimensions 1-5:

complete — Does it answer everything the user asked? 5 = every part addressed, including \
each half of a two-part question. 3 = the main question answered, a secondary one ignored. \
1 = evasive, or deflects when the extracts clearly contain the answer. Saying "the sources \
do not give this figure, check kela.fi" is complete, not incomplete.

useful — Would this actually help the person who asked? 5 = direct and specific, and where \
they described their situation, applies the rules to it rather than restating them \
generically. 3 = correct but generic. 1 = vague, padded, or evasive.

format — 5 = opens with the direct answer in a sentence or two, uses a list only for three \
or more items, bolds the values that matter, no headings, no advice framing ("you should", \
"I recommend"), no summary or next-steps section, under about 250 words. Deduct for each \
violation.

Under `unsupported_claims`, quote any NON-numeric assertion — a rule, a condition, a \
process step, a named organisation — that you cannot find in the extracts. Leave it empty \
if there are none."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "complete":           {"type": "integer", "minimum": 1, "maximum": 5},
        "useful":             {"type": "integer", "minimum": 1, "maximum": 5},
        "format":             {"type": "integer", "minimum": 1, "maximum": 5},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "comment":            {"type": "string"},
    },
    "required": ["complete", "useful", "format", "unsupported_claims", "comment"],
    "additionalProperties": False,
}


def mechanical_checks(case: dict, result: dict, passages) -> list[str]:
    """Deterministic assertions. Returns a list of failure descriptions."""
    failures = []
    answer = result["answer"]
    low    = answer.lower()

    for pattern, description in BANNED:
        if re.search(pattern, answer, re.IGNORECASE | re.MULTILINE):
            failures.append(f"banned: {description}")

    for phrase in case.get("must_include", []):
        if phrase.lower() not in low:
            failures.append(f"missing expected phrase: {phrase!r}")

    # A list means several labels are genuinely defensible — "can I work while
    # studying" is both study and work. Asserting one exact value there tests the
    # labeller's coin-flip rather than the answer.
    if expected := case.get("expect_category"):
        allowed = [expected] if isinstance(expected, str) else expected
        if result["category"] not in allowed:
            failures.append(
                f"category was {result['category']!r}, expected one of {allowed}"
            )

    if expected_domains := case.get("expect_domains"):
        cited = {s["domain"].lower() for s in result["sources"]}
        for domain in expected_domains:
            if domain.lower() not in cited:
                failures.append(f"no source cited from {domain} (cited: {sorted(cited) or 'none'})")

    if case.get("forbid_deflection") and DEFLECTION.search(answer):
        failures.append("deflected on a question the corpus should cover")

    if case.get("expect_out_of_scope") and result["quality"] != "not_in_sources":
        if "immigration" not in low:
            failures.append("did not decline a genuinely out-of-scope question")

    # The most important check here: an invented threshold or deadline is the
    # failure most likely to cause real harm, because someone will act on it.
    for figure in ungrounded_figures(answer, passages):
        failures.append(f"figure not in any retrieved source: {figure}")

    # The site invites questions in any language, so answering a Finnish question
    # in English is a user-facing failure, not a cosmetic one. It went unnoticed
    # because this case declared expect_language and nothing checked it.
    if case.get("expect_language") == "Finnish" and not is_finnish(answer):
        failures.append("expected a Finnish answer, got another language")

    if case.get("expect_brief") and len(answer.split()) > 60:
        failures.append(f"expected a brief reply, got {len(answer.split())} words")

    return failures


def judge(client, case: dict, result: dict, passages) -> dict:
    sources = "\n\n".join(
        # Whole passages, not excerpts. Truncating here makes the grader report
        # claims as unsupported when the support was just past the cut.
        f"[source {i}] {p.url}\n{p.text}" for i, p in enumerate(passages, 1)
    )
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content":
                f"QUESTION\n{case['question']}\n\n"
                f"ANSWER\n{result['answer']}\n\n"
                f"SOURCE EXTRACTS\n{sources}"},
        ],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "grade", "schema": JUDGE_SCHEMA, "strict": True}},
    )
    return json.loads(response.choices[0].message.content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", help="Pinecone index to evaluate against")
    parser.add_argument("--case", help="run only cases whose id contains this string")
    parser.add_argument("--no-judge", action="store_true", help="mechanical checks only")
    parser.add_argument("--out", help="write full results to this JSON file")
    args = parser.parse_args()

    if args.index:
        os.environ["PINECONE_INDEX_NAME"] = args.index

    from openai import OpenAI

    global ungrounded_figures, is_finnish
    from pipeline.process import is_finnish   # same heuristic the corpus filter uses
    from rag import config
    from rag.answer import ask
    from rag.grounding import ungrounded_figures

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if args.case in c["id"]]
    if not cases:
        raise SystemExit("no cases matched")

    print(f"index: {config.PINECONE_INDEX}   model: {config.ANSWER_MODEL}   cases: {len(cases)}\n")

    records, failed_cases = [], []
    totals = {"complete": 0, "useful": 0, "format": 0}
    judged = 0

    for case in cases:
        started = time.monotonic()
        result  = ask(case["question"], case.get("history", []))

        # Exactly the passages the answer was generated from — re-retrieving here
        # would grade against different text than the model actually saw.
        passages = result["passages"]

        failures = mechanical_checks(case, result, passages)
        grade = None
        if not args.no_judge:
            grade = judge(client, case, result, passages)
            for key in totals:
                totals[key] += grade[key]
            judged += 1

        status = "PASS" if not failures else "FAIL"
        if failures:
            failed_cases.append(case["id"])

        scores = (
            f"c{grade['complete']} u{grade['useful']} f{grade['format']}" if grade else "--"
        )
        print(f"{status}  {case['id']:<34} {scores}  {time.monotonic() - started:4.1f}s")
        for failure in failures:
            print(f"        - {failure}")
        if grade and grade["unsupported_claims"]:
            for claim in grade["unsupported_claims"]:
                print(f"        - unsupported: {claim[:150]}")

        records.append({
            "id": case["id"],
            "question": case["question"],
            "answer": result["answer"],
            "category": result["category"],
            "quality": result["quality"],
            "sources": [s["url"] for s in result["sources"]],
            "failures": failures,
            "grade": grade,
        })

    print("\n" + "-" * 62)
    print(f"passed {len(cases) - len(failed_cases)} / {len(cases)}")
    if judged:
        for key in ("complete", "useful", "format"):
            print(f"  mean {key:<9} {totals[key] / judged:.2f} / 5")
    if failed_cases:
        print(f"  failing: {', '.join(failed_cases)}")

    if args.out:
        Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"  full results → {args.out}")

    sys.exit(1 if failed_cases else 0)


if __name__ == "__main__":
    main()
