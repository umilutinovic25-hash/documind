from app.providers import EchoLLM, HashEmbedder
from app.rag import NO_ANSWER_TEXT, Rag
from app.stores import NumpyStore
from tests.conftest import NoLLM


def test_dedup_same_content(rag):
    again = rag.ingest("copy.txt", ["Mačke vole mleko i spavaju po ceo dan.", "Psi vole dugu šetnju."])
    assert again["duplicate"] is True
    assert len(rag.documents()) == 2


def test_same_name_new_content_replaces(rag):
    rag.ingest("a.txt", ["Potpuno novi sadržaj o ribama."])
    docs = {d["doc"]: d for d in rag.documents()}
    assert len(docs) == 2 and docs["a.txt"]["pages"] == 1


def test_delete_removes_from_retrieval(rag):
    doc_id = next(d["doc_id"] for d in rag.documents() if d["doc"] == "b.txt")
    assert rag.delete(doc_id) > 0
    assert all(h.chunk.doc != "b.txt" for h in rag.retrieve("kubernetes kontejnere", 4))


def test_doc_filter(rag):
    a = next(d["doc_id"] for d in rag.documents() if d["doc"] == "a.txt")
    assert {h.chunk.doc for h in rag.retrieve("kubernetes kontejnere mleko", 4, doc_ids={a})} == {"a.txt"}


def test_hybrid_finds_exact_code(rag):
    top = rag.retrieve("ERR-4471", 1, mode="hybrid")[0]
    assert "4471" in top.chunk.text


def test_abstains_when_nothing_relevant():
    r = Rag(HashEmbedder(), EchoLLM(), min_score=0.5)
    r.ingest("a.txt", ["Mačke vole mleko."])
    events = list(r.answer("qwxz plmk zzzz"))
    assert events[-1][1]["answered"] is False and events[-1][1]["sources"] == []
    assert events[0][1] == NO_ANSWER_TEXT


def test_model_abstention_strips_sources(rag):
    rag.llm = NoLLM()
    events = list(rag.answer("mleko mačke"))
    assert events[-1][1]["answered"] is False and events[-1][1]["sources"] == []


def test_answer_streams_with_sources_and_metrics(rag):
    events = list(rag.answer("mleko mačke"))
    done = events[-1][1]
    assert done["answered"] and done["sources"][0]["doc"] == "a.txt"
    assert {"retrieval_ms", "first_token_ms", "total_ms"} <= done["metrics"].keys()


def test_history_helps_retrieval(rag):
    hist = [{"q": "Šta radi Kubernetes?", "a": "Orkestrira kontejnere."}]
    done = list(rag.answer("a šta još?", history=hist))[-1][1]
    assert done["sources"] and done["sources"][0]["doc"] == "b.txt"


def test_persistence_roundtrip(tmp_path):
    r = Rag(HashEmbedder(), EchoLLM(), store=NumpyStore(str(tmp_path)))
    r.ingest("a.txt", ["Mačke vole mleko."])
    r2 = Rag(HashEmbedder(), EchoLLM(), store=NumpyStore(str(tmp_path)))
    assert len(r2.documents()) == 1 and r2.retrieve("mleko", 1)[0].chunk.doc == "a.txt"


def test_table_is_kept_intact_and_carries_heading():
    from app.chunking import chunk_document

    md = "# Projekat\n\n## Rezultati\n\n| # | Model | Ukupno |\n|---|---|---|\n| 1 | gemma3 | 79.5 |\n| 2 | mistral | 71.5 |\n\nNeki tekst posle tabele."
    chunks = chunk_document(md)
    table = next(c for h, c in chunks if "79.5" in c)
    assert "mistral" in table and "|---|" in table
    assert next(h for h, c in chunks if "79.5" in c) == "Rezultati"


def test_headings_inside_code_blocks_are_not_headings():
    from app.chunking import chunk_document

    md = "## Setup\n\n```bash\n# komentar a ne naslov\nnpm i\n```\n"
    assert {h for h, _ in chunk_document(md)} == {"Setup"}


def test_chunk_context_header_includes_doc_and_section():
    from app.stores import Chunk

    c = Chunk("id", "serbian-llm-bench.md", 1, "tekst", "Rezultati")
    assert "serbian llm bench" in c.indexed() and "Rezultati" in c.indexed()
    assert "serbian" not in c.lexical().lower()


def test_lexical_channel_cannot_override_strong_dense_signal(rag):
    rag.bm25_weight = 0.3
    assert rag.retrieve("šta radi kubernetes", 1, mode="hybrid")[0].chunk.doc == "b.txt"
