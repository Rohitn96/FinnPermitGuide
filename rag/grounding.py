"""
Verifying that the figures in an answer came from the sources.

A wrong euro threshold or appeal deadline is the most damaging thing this system
can produce: it is specific, it sounds authoritative, and someone will act on it.
The prompt forbids inventing figures, and the model usually complies — but
"usually" is not good enough for a number someone plans their residence around,
so every answer is checked mechanically before it is returned.

Deliberately string matching rather than a model check. Asked to verify figures
against a dozen long passages, a model skims and reports correctly-sourced
numbers as invented. This has to be exact, and exactness is what code is for.

Shared by rag/answer.py (the production guard) and eval/run.py (the test
assertion) so the two can never disagree about what counts as grounded.
"""

from __future__ import annotations

import re

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}

# Durations must match value AND unit together: "6 months" is wrong when the
# source says 3, even though both documents contain the word "months".
DURATION = re.compile(r"\b(\d+)\s*(day|week|month|year)s?\b", re.IGNORECASE)

# Money appears in both orders — "EUR 1 600", "€1600", "1,600 euros" — so it
# needs its own pattern. Matching only "value then unit" silently misses
# "EUR 2,500", precisely the figure most dangerous to invent.
MONEY = re.compile(
    r"(?:€|\beur\b)\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(?:€|\beuros?\b)",
    re.IGNORECASE,
)

CEFR = re.compile(r"\b([ABC][12])\b")


def normalise(text: str) -> str:
    """Fold the surface forms that sources and answers disagree about.

    "two months" versus "2 months", "1 600" versus "1,600" — comparing raw
    strings turns those differences into false hallucination reports.
    """
    text = text.replace("\xa0", " ").lower()
    for word, digit in NUMBER_WORDS.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    text = re.sub(r"(?<=\d)[\s,](?=\d{3}\b)", "", text)   # 1 600 / 1,600 -> 1600
    return re.sub(r"(?<=\d)[.,]00\b", "", text)           # 1600.00 -> 1600


def ungrounded_figures(answer: str, passages, asked: str = "") -> list[str]:
    """Figures stated in the answer that appear in none of the passages.

    `passages` is any iterable of objects with a `.text` attribute. `asked` is
    the user's own message, whose figures also count as grounded: when someone
    says "I have been in Finland 3 years" and the answer reflects that back, the
    3 came from them, not from an invented source. Without this the check fires
    on exactly the personalised answers it should be encouraging.
    """
    corpus = normalise(" ".join(p.text for p in passages) + " " + asked)
    text   = normalise(answer)

    missing = []

    # Requiring the whole surrounding phrase would be too strict: sources write
    # "a period of 4 years" where an answer writes "4 years of residence".
    for value, unit in DURATION.findall(text):
        if not re.search(rf"\b{value}\s*{unit}", corpus):
            missing.append(f"{value} {unit}s")

    # For money, check the amount alone — a specific euro figure occurring
    # anywhere in the retrieved text is almost certainly the same figure, and
    # the two sides place the currency marker differently.
    for before, after in MONEY.findall(text):
        amount = before or after
        if not re.search(rf"\b{re.escape(amount)}\b", corpus):
            missing.append(f"EUR {amount}")

    for level in set(CEFR.findall(answer)):
        if level.lower() not in corpus:
            missing.append(f"language level {level}")

    return sorted(set(missing))
