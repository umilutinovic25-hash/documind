import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMIND_DATA", str(tmp_path))
    monkeypatch.setenv("DOCUMIND_MAX_MB", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import app.main as main

    main = importlib.reload(main)

    from app.providers import EchoLLM, HashEmbedder
    from app.rag import Rag
    from app.stores import NumpyStore

    main.rag = Rag(HashEmbedder(), EchoLLM(), store=NumpyStore(str(tmp_path)))
    return TestClient(main.app), main


def up(c, name, text):
    return c.post("/documents", files={"file": (name, text.encode(), "text/plain")})


def test_upload_dedup_list_delete(client):
    c, _ = client
    r = up(c, "a.txt", "Mačke vole mleko.")
    assert r.status_code == 200 and r.json()["duplicate"] is False
    assert up(c, "copy.txt", "Mačke vole mleko.").json()["duplicate"] is True
    docs = c.get("/documents").json()
    assert len(docs) == 1
    assert c.delete(f"/documents/{docs[0]['doc_id']}").status_code == 200
    assert c.delete(f"/documents/{docs[0]['doc_id']}").status_code == 404


def test_rejects_bad_type_and_oversize(client):
    c, _ = client
    assert up(c, "x.exe", "x").status_code == 415
    assert c.post("/documents", files={"file": ("big.txt", b"a" * (1024 * 1024 + 10))}).status_code == 413


def test_empty_file_is_422(client):
    c, _ = client
    assert up(c, "empty.txt", "   ").status_code == 422


def test_api_prefix_serves_same_routes(client):
    c, _ = client
    assert c.get("/api/health").status_code == 200 and c.get("/health").status_code == 200


def test_query_streams_events(client):
    c, _ = client
    up(c, "a.txt", "Mačke vole mleko i spavaju.")
    r = c.post("/query", json={"question": "mleko mačke"})
    assert r.status_code == 200
    assert "event: token" in r.text and "event: done" in r.text


def test_query_validation(client):
    c, _ = client
    assert c.post("/query", json={"question": ""}).status_code == 422
    assert c.post("/query", json={"question": "x", "mode": "nope"}).status_code == 422


def test_api_key_enforced(client, monkeypatch):
    c, main = client
    monkeypatch.setattr(main, "API_KEY", "s3cret")
    assert c.get("/documents").status_code == 401
    assert c.get("/documents", headers={"X-API-Key": "s3cret"}).status_code == 200
