import pytest

from app.providers import EchoLLM, HashEmbedder
from app.rag import Rag


class NoLLM:
    def stream(self, prompt):
        yield "NEMA_ODGOVORA"


@pytest.fixture
def rag():
    r = Rag(HashEmbedder(), EchoLLM())
    r.ingest("a.txt", ["Mačke vole mleko i spavaju po ceo dan.", "Psi vole dugu šetnju."])
    r.ingest("b.txt", ["Kubernetes orkestrira kontejnere u klasteru.", "Šifra greške ERR-4471 znači istek tokena."])
    return r
