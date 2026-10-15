import json
import os

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .extract import ExtractionError, extract_pages
from .providers import make_providers
from .rag import Rag
from .rerank import LLMReranker
from .stores import NumpyStore, QdrantStore

MAX_UPLOAD = int(os.getenv("DOCUMIND_MAX_MB", "20")) * 1024 * 1024
ALLOWED = (".pdf", ".txt", ".md")
DATA_DIR = os.getenv("DOCUMIND_DATA", "data")
API_KEY = os.getenv("DOCUMIND_API_KEY")


def make_store():
    if os.getenv("DOCUMIND_STORE", "numpy") == "qdrant":
        return QdrantStore(path=os.path.join(DATA_DIR, "qdrant"), url=os.getenv("QDRANT_URL"))
    return NumpyStore(DATA_DIR)


def auth(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Neispravan API ključ")


app = FastAPI(title="DocuMind", dependencies=[Depends(auth)])
router = APIRouter()
_emb, _llm = make_providers()
rag = Rag(_emb, _llm, store=make_store(), reranker=LLMReranker(_llm) if os.getenv("DOCUMIND_RERANK") == "1" else None)


class Turn(BaseModel):
    q: str
    a: str


class Query(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=4, ge=1, le=10)
    mode: str = Field(default="hybrid", pattern="^(hybrid|dense|bm25|hybrid\\+rerank)$")
    doc_ids: list[str] | None = None
    history: list[Turn] = []


@router.post("/documents")
async def upload(file: UploadFile):
    name = file.filename or "upload"
    if not name.lower().endswith(ALLOWED):
        raise HTTPException(415, f"Dozvoljeni formati: {', '.join(ALLOWED)}")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"Fajl je veći od {MAX_UPLOAD // 1024 // 1024} MB")
    try:
        pages, ocr_pages = extract_pages(name, data)
    except ExtractionError as e:
        raise HTTPException(422, str(e))
    return {**rag.ingest(name, pages), "ocr_pages": ocr_pages}


@router.get("/documents")
def documents():
    return rag.documents()


@router.delete("/documents/{doc_id}")
def delete(doc_id: str):
    if not rag.delete(doc_id):
        raise HTTPException(404, "Dokument ne postoji")
    return {"deleted": doc_id}


@router.post("/query")
def query(q: Query):
    history = [t.model_dump() for t in q.history]

    def sse():
        try:
            for kind, payload in rag.answer(q.question, q.k, history, q.mode, set(q.doc_ids) if q.doc_ids else None):
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
        except Exception as e:  # surface model/embedding outages to the UI instead of a dead stream
            yield f"event: error\ndata: {json.dumps(str(e))}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


class Review(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=5)
    doc_ids: list[str] | None = None


@router.post("/review")
def review(r: Review):
    """Documents x questions grid; each cell is answered from that single document."""
    return rag.review(r.questions, r.doc_ids)


@router.get("/health")
def health():
    return {"documents": len(rag.documents())}


# Same routes at / (scripts, tests) and /api (the bundled UI); then the built UI itself.
app.include_router(router)
app.include_router(router, prefix="/api")
_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
