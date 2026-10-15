"""Small BM25 (Okapi) with diacritic folding, so 'šta' matches 'sta' and Latin/Cyrillic-agnostic enough for SR."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_TOKEN = re.compile(r"\w+", re.UNICODE)
_CYR = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџш", ["a", "b", "v", "g", "d", "dj", "e", "z", "z", "i", "j", "k", "l", "lj", "m", "n", "nj", "o", "p", "r", "s", "t", "c", "u", "f", "h", "c", "c", "dz", "s"]))


def tokenize(text: str) -> list[str]:
    text = "".join(_CYR.get(ch, ch) for ch in text.lower())
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).replace("đ", "dj")
    return [t for t in _TOKEN.findall(text) if len(t) > 1]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(tokenize(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(docs)) if docs else 0.0
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for tf, ln in zip(self.tf, self.len):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out
