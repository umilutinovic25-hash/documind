"""promptfoo provider: runs one question through the real Rag pipeline over eval/corpus + fixtures.

Output is the final `done` payload as JSON plus the streamed answer text, so assertions can check
abstention, citations and verification without parsing SSE. The index is cached on disk and
ingest dedups by content hash, so only the first call pays for embedding.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from app.evaluate import _load_corpus  # noqa: E402
from app.extract import extract_pages  # noqa: E402
from app.providers import make_providers  # noqa: E402
from app.rag import Rag  # noqa: E402
from app.stores import NumpyStore  # noqa: E402

_rag: Rag | None = None


def _get_rag() -> Rag:
    global _rag
    if _rag is None:
        emb, llm = make_providers()
        _rag = Rag(emb, llm, store=NumpyStore(os.path.join(HERE, ".cache")))
        for folder in (os.path.join(ROOT, "eval", "corpus"), os.path.join(HERE, "fixtures")):
            for name, data in _load_corpus(folder):
                pages, _ = extract_pages(name, data)
                _rag.ingest(name, pages)
    return _rag


def call_api(prompt: str, options: dict, context: dict) -> dict:
    cfg = options.get("config", {})
    vars_ = context.get("vars", {})
    tokens, done = [], {}
    for kind, payload in _get_rag().answer(prompt, cfg.get("k", 4), vars_.get("history") or [], cfg.get("mode", "hybrid")):
        if kind == "token":
            tokens.append(payload)
        elif kind == "done":
            done = payload
    done["answer"] = "".join(tokens)
    done["source_docs"] = sorted({s["doc"] for s in done.get("sources", [])})
    for s in done.get("sources", []):
        s.pop("text", None)  # keep the eval report small
    return {"output": json.dumps(done, ensure_ascii=False)}
