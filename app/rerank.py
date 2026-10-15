"""Optional listwise LLM reranker. One extra non-streaming call; falls back to the input order on any parse problem."""
from __future__ import annotations

import json
import re

from .providers import LLM


class LLMReranker:
    def __init__(self, llm: LLM, snippet_chars: int = 350):
        self.llm, self.snippet = llm, snippet_chars

    def order(self, question: str, passages: list[str]) -> list[int]:
        if len(passages) < 2:
            return list(range(len(passages)))
        listing = "\n".join(f"{i}: {p[: self.snippet]!r}" for i, p in enumerate(passages))
        prompt = (
            "Poređaj odlomke od najrelevantnijeg do najmanje relevantnog za pitanje. "
            "Odgovori SAMO JSON listom brojeva, npr. [2,0,1].\n\n"
            f"PITANJE: {question}\n\nODLOMCI:\n{listing}\n\nJSON:"
        )
        raw = "".join(self.llm.stream(prompt))
        m = re.search(r"\[[\d,\s]*\]", raw)
        try:
            ids = [i for i in json.loads(m.group(0)) if isinstance(i, int) and 0 <= i < len(passages)] if m else []
        except ValueError:
            ids = []
        seen: list[int] = []
        for i in ids:
            if i not in seen:
                seen.append(i)
        return seen + [i for i in range(len(passages)) if i not in seen]
