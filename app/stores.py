"""Vector stores behind one small interface: NumpyStore (default, on disk) and QdrantStore (local or server)."""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np


@dataclass
class Chunk:
    doc_id: str
    doc: str
    page: int
    text: str
    heading: str = ""

    def lexical(self) -> str:
        """BM25 text: section heading + chunk. The document title is deliberately left out; when a
        question names the project it would otherwise match every chunk of that document equally."""
        return f"{self.heading}\n{self.text}" if self.heading else self.text

    def indexed(self) -> str:
        """What gets embedded / BM25-indexed: the chunk plus its document and section as context."""
        title = os.path.splitext(self.doc)[0].replace("-", " ").replace("_", " ")
        return f"{title}{' > ' + self.heading if self.heading else ''}\n{self.text}"


def _norm(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


class Store(Protocol):
    def add(self, chunks: list[Chunk], vecs: np.ndarray) -> None: ...
    def remove_doc(self, doc_id: str) -> int: ...
    def dense_search(self, qvec: np.ndarray, k: int, doc_ids: set[str] | None) -> list[tuple[Chunk, float]]: ...
    def all_chunks(self) -> list[Chunk]: ...


class NumpyStore:
    def __init__(self, path: str | None = None):
        self.path, self.lock = path, threading.RLock()
        self.chunks: list[Chunk] = []
        self.vecs: np.ndarray | None = None
        if path:
            self._load()

    def add(self, chunks, vecs):
        with self.lock:
            vecs = _norm(np.asarray(vecs, dtype=np.float32))
            self.chunks += chunks
            self.vecs = vecs if self.vecs is None else np.vstack([self.vecs, vecs])
            self._save()

    def remove_doc(self, doc_id):
        with self.lock:
            keep = [i for i, c in enumerate(self.chunks) if c.doc_id != doc_id]
            removed = len(self.chunks) - len(keep)
            if removed:
                self.chunks = [self.chunks[i] for i in keep]
                self.vecs = self.vecs[keep] if keep else None
                self._save()
            return removed

    def dense_search(self, qvec, k, doc_ids):
        with self.lock:
            if self.vecs is None:
                return []
            scores = self.vecs @ _norm(np.asarray(qvec, dtype=np.float32))
            order = np.argsort(-scores)
            out = []
            for i in order:
                if doc_ids is None or self.chunks[i].doc_id in doc_ids:
                    out.append((self.chunks[i], float(scores[i])))
                if len(out) == k:
                    break
            return out

    def all_chunks(self):
        with self.lock:
            return list(self.chunks)

    def _save(self):
        if not self.path:
            return
        os.makedirs(self.path, exist_ok=True)
        np.save(os.path.join(self.path, "vecs.npy"), self.vecs if self.vecs is not None else np.zeros((0, 1), dtype=np.float32))
        with open(os.path.join(self.path, "chunks.json"), "w") as f:
            json.dump([asdict(c) for c in self.chunks], f, ensure_ascii=False)

    def _load(self):
        vp, cp = os.path.join(self.path, "vecs.npy"), os.path.join(self.path, "chunks.json")
        if os.path.exists(vp) and os.path.exists(cp):
            self.chunks = [Chunk(**c) for c in json.load(open(cp))]
            self.vecs = np.load(vp) if self.chunks else None


class QdrantStore:
    """Qdrant via embedded local mode (path) or a server (url). Cosine distance."""

    def __init__(self, path: str | None = None, url: str | None = None, collection: str = "documind"):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=url) if url else QdrantClient(path=path or ":memory:")
        self.collection, self.lock = collection, threading.RLock()

    def _ensure(self, dim: int):
        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    def add(self, chunks, vecs):
        from qdrant_client.models import PointStruct

        with self.lock:
            vecs = np.asarray(vecs, dtype=np.float32)
            self._ensure(vecs.shape[1])
            self.client.upsert(
                self.collection,
                [PointStruct(id=str(uuid.uuid4()), vector=v.tolist(), payload=asdict(c)) for c, v in zip(chunks, vecs)],
            )

    def remove_doc(self, doc_id):
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        with self.lock:
            if not self.client.collection_exists(self.collection):
                return 0
            f = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
            n = self.client.count(self.collection, count_filter=f, exact=True).count
            if n:
                self.client.delete(self.collection, points_selector=FilterSelector(filter=f))
            return n

    def dense_search(self, qvec, k, doc_ids):
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        with self.lock:
            if not self.client.collection_exists(self.collection):
                return []
            f = Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=list(doc_ids)))]) if doc_ids else None
            res = self.client.query_points(self.collection, query=np.asarray(qvec, dtype=np.float32).tolist(), limit=k, query_filter=f, with_payload=True)
            return [(Chunk(**p.payload), float(p.score)) for p in res.points]

    def all_chunks(self):
        with self.lock:
            if not self.client.collection_exists(self.collection):
                return []
            out, offset = [], None
            while True:
                pts, offset = self.client.scroll(self.collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
                out += [Chunk(**p.payload) for p in pts]
                if offset is None:
                    return out
