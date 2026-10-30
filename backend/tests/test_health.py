"""Health, stats, settings and error-shape tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "VeriDox AI"
    assert body["llm_provider"] == "mock"
    assert body["embedding_provider"] == "hashing-dev"


def test_unknown_route_returns_structured_error(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert isinstance(error["message"], str)


def test_stats_endpoint_on_empty_workspace(client: TestClient) -> None:
    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["documents"] == 0
    assert body["totals"]["chunks"] == 0
    assert body["ingestion_counts"] == {
        "processed": 0,
        "processing": 0,
        "pending": 0,
        "failed": 0,
    }
    assert body["index"]["chunk_count"] == 0
    assert body["index"]["backend"] in {"faiss", "numpy"}


def test_settings_endpoint_never_exposes_secrets(client: TestClient) -> None:
    response = client.get("/api/system/settings")
    assert response.status_code == 200
    text = response.text.lower()
    assert "api_key" not in text
    assert "secret" not in text
    body = response.json()
    assert body["llm_provider"] == "mock"
    assert body["llm_is_mock"] is True
    assert body["embedding_dimension"] == 384
