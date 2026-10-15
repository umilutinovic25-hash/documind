from app.evaluate import run
from app.providers import EchoLLM, HashEmbedder
from app.rag import Rag
from app.stores import QdrantStore


def make(store=None):
    r = Rag(HashEmbedder(), EchoLLM(), store=store)
    r.ingest("g.pdf", ["Mačke vole mleko.", "Kubernetes orkestrira kontejnere."])
    return r


def test_qdrant_store_search_filter_delete(tmp_path):
    r = make(QdrantStore(path=str(tmp_path)))
    assert r.retrieve("kubernetes kontejnere", 1, mode="dense")[0].chunk.page == 2
    doc_id = r.documents()[0]["doc_id"]
    assert r.retrieve("mleko", 1, mode="dense", doc_ids={"nope"}) == []
    assert r.delete(doc_id) == 2 and r.documents() == []


def test_eval_metrics_and_abstention():
    golden = [
        {"question": "mleko mačke", "expected_pages": [1]},
        {"question": "kubernetes kontejnere", "expected_page": 2},
        {"question": "qwxz plmk", "answerable": False},
    ]
    rep = run(make(), golden, k=1, mode="hybrid")
    assert rep["hit_at_k"] == 1.0 and rep["mrr"] == 1.0
    assert rep["abstention_accuracy"] in (0.0, 1.0)
    assert rep["n_unanswerable"] == 1


def test_eval_detects_miss():
    rep = run(make(), [{"question": "mleko mačke", "expected_pages": [2]}], k=1)
    assert rep["hit_at_k"] == 0.0


def test_eval_expected_docs_and_verification_metrics():
    r = Rag(HashEmbedder(), EchoLLM())
    r.ingest("cats.md", ["Mačke vole mleko."])
    r.ingest("k8s.md", ["Kubernetes orkestrira kontejnere."])
    rep = run(r, [{"question": "kubernetes kontejnere", "expected_docs": ["k8s.md"]}], k=1)
    assert rep["hit_at_k"] == 1.0
    assert "unsupported_citation_rate" in rep and rep["invalid_citations"] == 0
