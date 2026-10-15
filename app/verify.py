"""Deterministic citation verification: is each cited sentence actually supported by the cited source?

Not an LLM judge. A sentence is 'supported' when most of its content words (matched by a short
stem, so Serbian inflections still hit) appear in the chunks it cites. Citations that point at a
non-existent source are reported as invalid.
"""
from __future__ import annotations

import re

from .lexical import tokenize

_CITE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_SENT = re.compile(r"(?<=[.!?…])\s+|\n+")
STEM = 5
THRESHOLD = 0.5


def _stems(text: str) -> set[str]:
    # numbers/codes count at any length ("422"); words need 4+ letters to be informative
    return {t[:STEM] for t in tokenize(text) if len(t) >= 4 or any(ch.isdigit() for ch in t)}


_ANCHOR = re.compile(r"`([^`]+)`|\b(\d[\d.,:%$-]*\d|\d)\b|\b([A-Z][A-Z0-9_]{2,})\b|\b([a-z0-9]+(?:_[a-z0-9]+)+)\b")


def _anchors(text: str) -> set[str]:
    """Language-independent evidence: numbers, ALL_CAPS codes, `code spans`, snake_case identifiers."""
    return {next(g for g in m.groups() if g).lower() for m in _ANCHOR.finditer(_CITE.sub("", text))}


def verify_answer(answer: str, sources: list[str], question: str = "") -> dict:
    """sources[i] is the text of citation [i+1].

    Words that merely restate the question are ignored: the check is about the *new* claim.
    A claim found only in a different retrieved source is 'misattributed', not unsupported.
    """
    src_stems = [_stems(s) for s in sources]
    all_stems = set().union(*src_stems) if src_stems else set()
    asked = _stems(question)
    asked_anchors = _anchors(question)
    checks, invalid = [], []
    for sent in _SENT.split(answer):
        nums = [int(n) for grp in _CITE.findall(sent) for n in re.findall(r"\d+", grp)]
        if not nums:
            continue
        valid = [n for n in nums if 1 <= n <= len(sources)]
        invalid += [n for n in nums if n not in valid]
        if not valid:
            continue
        anchors = _anchors(sent) - asked_anchors
        if anchors:  # facts like numbers/codes decide the verdict regardless of language
            cited_text = " ".join(sources[n - 1] for n in valid).lower()
            all_text = " ".join(sources).lower()
            score = sum(a in cited_text for a in anchors) / len(anchors)
            grounded = sum(a in all_text for a in anchors) / len(anchors)
            per_source = [sum(a in src.lower() for a in anchors) / len(anchors) for src in sources]
        else:
            words = _stems(_CITE.sub("", sent)) - asked
            if len(words) < 2:
                continue
            pool = set().union(*(src_stems[n - 1] for n in valid))
            score = len(words & pool) / len(words)
            grounded = len(words & all_stems) / len(words)
            per_source = [len(words & st) / len(words) for st in src_stems]
        supported = score >= THRESHOLD or grounded >= THRESHOLD
        checks.append({
            "sentence": sent.strip(),
            "cites": valid,
            "score": round(score, 2),
            "supported": supported,
            "misattributed": supported and score < THRESHOLD,
            # when the claim is true but cited to the wrong place, point at the source that has it
            "found_in": (max(range(len(per_source)), key=per_source.__getitem__) + 1) if supported and score < THRESHOLD else None,
        })
    return {
        "checks": checks,
        "invalid_citations": sorted(set(invalid)),
        "unsupported": sum(1 for c in checks if not c["supported"]),
        "checked": len(checks),
    }
