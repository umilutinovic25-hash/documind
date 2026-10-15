from app.providers import EchoLLM, HashEmbedder
from app.rag import Rag
from app.rerank import LLMReranker
from app.verify import verify_answer


def test_supported_sentence_passes():
    src = ["Profil stila se čuva lokalno na računaru korisnika i može ponovo da se koristi."]
    v = verify_answer("Profil stila se čuva lokalno na računaru [1].", src)
    assert v["checked"] == 1 and v["unsupported"] == 0


def test_unsupported_sentence_is_flagged():
    src = ["Profil stila se čuva lokalno na računaru korisnika."]
    v = verify_answer("Cena pretplate iznosi petnaest evra mesečno za svaki nalog [1].", src)
    assert v["unsupported"] == 1


def test_invalid_citation_reported():
    v = verify_answer("Nešto o profilu stila i čuvanju podataka [7].", ["profil stila čuvanje podataka"])
    assert v["invalid_citations"] == [7]


def test_inflection_matches_via_stem():
    v = verify_answer("Titlovi se generišu iz transkripta [1].", ["Titlove generiše iz transkripta sistem."])
    assert v["unsupported"] == 0


class OrderLLM:
    def __init__(self, reply):
        self.reply = reply

    def stream(self, prompt):
        yield self.reply


def test_reranker_applies_order_and_appends_missing():
    assert LLMReranker(OrderLLM("[2, 0]")).order("q", ["a", "b", "c"]) == [2, 0, 1]


def test_reranker_falls_back_on_garbage():
    assert LLMReranker(OrderLLM("ne znam")).order("q", ["a", "b", "c"]) == [0, 1, 2]


def test_rerank_mode_reorders_hits():
    r = Rag(HashEmbedder(), EchoLLM(), reranker=LLMReranker(OrderLLM("[1,0]")))
    r.ingest("a.txt", ["Mačke vole mleko.", "Mačke vole mleko i ribu."])
    plain = r.retrieve("mačke mleko", 2, mode="hybrid")
    reranked = r.retrieve("mačke mleko", 2, mode="hybrid+rerank")
    assert [h.chunk.text for h in reranked] == [plain[1].chunk.text, plain[0].chunk.text]


def test_done_event_contains_verification(rag):
    done = list(rag.answer("mleko mačke"))[-1][1]
    assert done["verification"] is not None and "checks" in done["verification"]


def test_review_grid_shape(rag):
    out = rag.review(["mleko mačke", "kubernetes kontejnere"])
    assert len(out["rows"]) == 2 and all(len(r["cells"]) == 2 for r in out["rows"])
    a = next(r for r in out["rows"] if r["doc"] == "a.txt")
    assert a["cells"][0]["answered"] is True


def test_grouped_citations_are_parsed():
    v = verify_answer("Profil stila se čuva lokalno na računaru [1, 2].", ["profil stila čuva lokalno računaru", "nešto drugo"])
    assert v["checked"] == 1 and v["invalid_citations"] == []
    v2 = verify_answer("Profil stila se čuva lokalno na računaru [1, 5].", ["profil stila čuva lokalno računaru"])
    assert v2["invalid_citations"] == [5]


def test_question_restating_words_do_not_cause_false_alarm():
    src = ["Provider mock je podrazumevani kad nema ključa."]
    v = verify_answer("BrandPilot koristi mock provider kada nema API ključa [1].", src, question="Koji provajder BrandPilot koristi kada nema API ključa?")
    assert v["unsupported"] == 0


def test_misattributed_claim_is_supported_but_marked():
    srcs = ["Profil stila se čuva lokalno na računaru.", "Titlovi se generišu iz transkripta."]
    v = verify_answer("Profil stila se čuva lokalno na računaru [2].", srcs)
    c = v["checks"][0]
    assert c["supported"] and c["misattributed"] and c["found_in"] == 1


def test_numbers_count_as_evidence():
    v = verify_answer("Vraća kod 422 kada status nije COMPLETED [1].", ["422 unless COMPLETED; 409 if already invoiced"])
    assert v["unsupported"] == 0
