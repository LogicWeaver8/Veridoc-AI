"""Index administration, persistence and rebuild tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.sample_docs import LEAVE_DOC


def _upload(client: TestClient) -> dict:
    response = client.post(
        "/api/documents/upload",
        files={"file": ("Leave_Policy_2026.txt", LEAVE_DOC.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_index_status_and_rebuild(client: TestClient) -> None:
    _upload(client)

    status = client.get("/api/index/status").json()
    assert status["chunk_count"] > 0
    assert status["document_count"] == 1
    assert status["needs_rebuild"] is False
    assert status["backend"] in {"faiss", "numpy"}
    assert status["dimension"] == 384

    rebuild = client.post("/api/index/rebuild")
    assert rebuild.status_code == 200
    body = rebuild.json()
    assert body["chunk_count"] == status["chunk_count"]

    after = client.get("/api/index/status").json()
    assert after["chunk_count"] == status["chunk_count"]
    assert after["needs_rebuild"] is False


def test_index_persists_across_restart(settings_factory) -> None:
    settings = settings_factory("persist")
    app = create_app(settings)
    with TestClient(app) as client:
        uploaded = _upload(client)
        chunk_count = client.get("/api/index/status").json()["chunk_count"]
        assert chunk_count > 0

    restarted_app = create_app(settings_factory("persist"))
    with TestClient(restarted_app) as client:
        status = client.get("/api/index/status").json()
        assert status["chunk_count"] == chunk_count
        assert status["needs_rebuild"] is False
        assert client.get(f"/api/documents/{uploaded['id']}").status_code == 200

        answer = client.post(
            "/api/chat/ask", json={"question": "How many annual leave days do employees receive?"}
        ).json()
        assert answer["answer_status"] == "answered"
        assert "18" in answer["answer"]


def test_embedding_change_requires_and_survives_rebuild(settings_factory) -> None:
    app = create_app(settings_factory("dimension", embedding_dim=384))
    with TestClient(app) as client:
        _upload(client)

    app = create_app(settings_factory("dimension", embedding_dim=128))
    with TestClient(app) as client:
        status = client.get("/api/index/status").json()
        assert status["needs_rebuild"] is True
        assert status["chunk_count"] == 0
        assert status["dimension"] == 128

        rebuild = client.post("/api/index/rebuild")
        assert rebuild.status_code == 200
        assert rebuild.json()["chunk_count"] > 0

        status = client.get("/api/index/status").json()
        assert status["needs_rebuild"] is False
        assert status["chunk_count"] > 0

        answer = client.post(
            "/api/chat/ask", json={"question": "How many annual leave days do employees receive?"}
        ).json()
        assert answer["answer_status"] == "answered"
        assert "18" in answer["answer"]


def test_delete_removes_chunks_and_conversations_remain(client: TestClient) -> None:
    uploaded = _upload(client)
    client.post("/api/chat/ask", json={"question": "How many annual leave days?"})

    assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 204
    assert client.get("/api/index/status").json()["chunk_count"] == 0

    # Conversations are independent of documents.
    assert client.get("/api/chat/conversations").json()

    after = client.post("/api/chat/ask", json={"question": "How many annual leave days?"}).json()
    assert after["answer_status"] == "not_covered"
