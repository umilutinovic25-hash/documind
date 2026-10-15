"""Eval harness: retrieval quality, abstention and citation checks over a golden set.

    python -m app.evaluate eval/golden_multi.json eval/corpus --compare --min-hit 0.8

`corpus` is a file or a directory of .pdf/.txt/.md. Golden case fields:
  question
  expected_docs   list of document names, any match is a hit   (multi-document corpora)
  expected_pages  list of pages (combined with expected_docs if both are given)
  answerable      default true; false = must abstain
  expected_keywords  all must appear in the answer
Exits non-zero when hit@k of the gated mode is below --min-hit, so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys

from .rag import Rag


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def _is_hit(case: dict, chunk) -> bool:
    ev = case.get("expected_evidence")
    if ev:  # chunk-level: the retrieved chunk must actually contain the fact
        return any(_norm(e) in _norm(chunk.text) for e in ev)
    docs = case.get("expected_docs")
    pages = case.get("expected_pages") or ([case["expected_page"]] if "expected_page" in case else None)
    if docs and chunk.doc not in docs:
        return False
    if pages and chunk.page not in pages:
        return False
    return bool(docs or pages)


def score_case(rag: Rag, case: dict, k: int, mode: str, retrieval_only: bool = False) -> dict:
    answerable = case.get("answerable", True)
    hits = rag.retrieve(case["question"], k, mode)
    rank = next((i + 1 for i, h in enumerate(hits) if _is_hit(case, h.chunk)), None)
    if retrieval_only:
        base = {"question": case["question"], "answerable": answerable, "total_ms": 0.0, "answer": ""}
        if not answerable:
            return base | {"abstained": None}
        return base | {"hit": rank is not None, "reciprocal_rank": 1 / rank if rank else 0.0,
                       "answered": True, "cited": True, "keywords_ok": True,
                       "unsupported": 0, "checked": 0, "invalid_citations": 0}

    text, done = [], {}
    for kind, payload in rag.answer(case["question"], k, mode=mode):
        if kind == "token":
            text.append(payload)
        else:
            done = payload
    text = "".join(text)
    row = {"question": case["question"], "answerable": answerable, "total_ms": done["metrics"]["total_ms"], "answer": text}
    if answerable:
        ver = done.get("verification") or {"checked": 0, "unsupported": 0, "invalid_citations": []}
        kws = case.get("expected_keywords", [])
        row |= {
            "hit": rank is not None,
            "reciprocal_rank": 1 / rank if rank else 0.0,
            "answered": done["answered"],
            "cited": done["answered"] and bool(re.search(r"\[\d+(?:\s*[,;]\s*\d+)*\]", text)),
            "keywords_ok": all(w.lower() in text.lower() for w in kws),
            "unsupported": ver["unsupported"],
            "checked": ver["checked"],
            "invalid_citations": len(ver["invalid_citations"]),
        }
    else:
        row |= {"abstained": not done["answered"]}
    return row


def run(rag: Rag, golden: list[dict], k: int = 4, mode: str = "hybrid", retrieval_only: bool = False) -> dict:
    rows = [score_case(rag, c, k, mode, retrieval_only) for c in golden]
    pos = [r for r in rows if r["answerable"]]
    neg = [r for r in rows if not r["answerable"]]
    checked = sum(r["checked"] for r in pos)
    return {
        "mode": mode,
        "k": k,
        "n_answerable": len(pos),
        "n_unanswerable": len(neg),
        "hit_at_k": sum(r["hit"] for r in pos) / len(pos) if pos else 0.0,
        "mrr": statistics.mean(r["reciprocal_rank"] for r in pos) if pos else 0.0,
        "answered_rate": sum(r["answered"] for r in pos) / len(pos) if pos else 0.0,
        "citation_rate": sum(r["cited"] for r in pos) / len(pos) if pos else 0.0,
        "keyword_accuracy": sum(r["keywords_ok"] for r in pos) / len(pos) if pos else 0.0,
        "unsupported_citation_rate": (sum(r["unsupported"] for r in pos) / checked) if checked else 0.0,
        "invalid_citations": sum(r["invalid_citations"] for r in pos),
        "abstention_accuracy": (sum(bool(r["abstained"]) for r in neg) / len(neg)) if neg and neg[0]["abstained"] is not None else None,
        "p50_ms": statistics.median(r["total_ms"] for r in rows),
        "cases": rows,
    }


def _summary(rep: dict) -> dict:
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rep.items() if k != "cases"}


def _load_corpus(path: str) -> list[tuple[str, bytes]]:
    if os.path.isdir(path):
        names = sorted(f for f in os.listdir(path) if f.lower().endswith((".pdf", ".txt", ".md")))
        return [(n, open(os.path.join(path, n), "rb").read()) for n in names]
    return [(os.path.basename(path), open(path, "rb").read())]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("golden")
    ap.add_argument("corpus", help="file or directory")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "dense", "bm25", "hybrid+rerank"])
    ap.add_argument("--compare", action="store_true", help="run dense, bm25, hybrid and hybrid+rerank")
    ap.add_argument("--retrieval-only", action="store_true", help="skip generation: fast, deterministic retrieval metrics")
    ap.add_argument("--min-hit", type=float, default=0.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    from .extract import extract_pages
    from .providers import make_providers
    from .rerank import LLMReranker

    emb, llm = make_providers()
    rag = Rag(emb, llm, reranker=LLMReranker(llm))
    for name, data in _load_corpus(a.corpus):
        pages, _ = extract_pages(name, data)
        rag.ingest(name, pages)
    golden = json.load(open(a.golden))

    modes = ["dense", "bm25", "hybrid", "hybrid+rerank"] if a.compare else [a.mode]
    reports = {m: run(rag, golden, a.k, m, a.retrieval_only) for m in modes}
    if a.out:
        json.dump(reports, open(a.out, "w"), ensure_ascii=False, indent=2)
    print(json.dumps({m: _summary(r) for m, r in reports.items()}, ensure_ascii=False, indent=2))
    gate = reports.get("hybrid") or reports[a.mode]
    return 0 if gate["hit_at_k"] >= a.min_hit else 1


if __name__ == "__main__":
    sys.exit(main())
