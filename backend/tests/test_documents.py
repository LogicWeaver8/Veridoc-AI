"""Document upload, listing, validation and deletion tests."""

from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from tests.sample_docs import LEAVE_DOC, TRAVEL_DOC


def _upload(client, filename, content, data=None):
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, content, "application/octet-stream")},
        data=data or {},
    )


def test_upload_txt_is_processed(client: TestClient) -> None:
    response = _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC.encode("utf-8"))
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "Leave_Policy_2026.txt"
    assert body["file_type"] == "txt"

    detail = client.get(f"/api/documents/{body['id']}").json()
    assert detail["status"] == "completed"
    assert detail["version_count"] == 1
    assert detail["active_version"]["chunk_count"] >= 1
    assert detail["active_version"]["page_count"] == 1


def test_upload_markdown_is_processed(client: TestClient) -> None:
    response = _upload(client, "handbook.md", TRAVEL_DOC.encode("utf-8"))
    assert response.status_code == 201
    detail = client.get(f"/api/documents/{response.json()['id']}").json()
    assert detail["file_type"] == "markdown"
    assert detail["status"] == "completed"


def test_upload_pdf_preserves_page_numbers(client: TestClient) -> None:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "TRAVEL POLICY 2026", fontsize=14)
    page.insert_text((72, 110), "The daily meal allowance is capped at $75.00 per diem.", fontsize=11)
    content = pdf.tobytes()
    pdf.close()

    response = _upload(client, "travel_policy.pdf", content)
    assert response.status_code == 201
    detail = client.get(f"/api/documents/{response.json()['id']}").json()
    assert detail["status"] == "completed"
    assert detail["active_version"]["page_count"] == 1


def test_invalid_extension_is_rejected(client: TestClient) -> None:
    response = _upload(client, "malware.exe", b"not a policy")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_empty_file_is_rejected(client: TestClient) -> None:
    response = _upload(client, "empty.txt", b"")
    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"].lower()


def test_oversized_file_is_rejected(client_factory) -> None:
    client = client_factory(max_upload_mb=1)
    response = _upload(client, "large.txt", b"a" * (1024 * 1024 + 10))
    assert response.status_code == 422
    assert "limit" in response.json()["error"]["message"].lower()


def test_duplicate_document_is_detected(client: TestClient) -> None:
    first = _upload(client, "leave.txt", LEAVE_DOC.encode("utf-8"))
    assert first.status_code == 201

    second = _upload(client, "leave_copy.txt", LEAVE_DOC.encode("utf-8"))
    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "duplicate_document"
    assert error["details"]["existing_document_id"] == first.json()["id"]


def test_multiple_upload_handles_success_and_duplicates(client: TestClient) -> None:
    files = [
        ("files", ("leave.txt", LEAVE_DOC.encode("utf-8"), "text/plain")),
        ("files", ("travel.txt", TRAVEL_DOC.encode("utf-8"), "text/plain")),
        ("files", ("leave_again.txt", LEAVE_DOC.encode("utf-8"), "text/plain")),
    ]
    response = client.post("/api/documents/upload-multiple", files=files)
    assert response.status_code == 200
    body = response.json()
    assert len(body["uploaded"]) == 2
    assert len(body["duplicates"]) == 1
    assert body["duplicates"][0]["filename"] == "leave_again.txt"
    assert body["errors"] == []


def test_list_search_and_filter(client: TestClient) -> None:
    _upload(client, "leave.txt", LEAVE_DOC.encode("utf-8"))
    _upload(client, "travel.md", TRAVEL_DOC.encode("utf-8"))

    all_docs = client.get("/api/documents").json()
    assert all_docs["total"] == 2

    searched = client.get("/api/documents", params={"search": "travel"}).json()
    assert searched["total"] == 1
    assert searched["items"][0]["filename"] == "travel.md"

    by_type = client.get("/api/documents", params={"file_type": "markdown"}).json()
    assert by_type["total"] == 1

    by_status = client.get("/api/documents", params={"status": "completed"}).json()
    assert by_status["total"] == 2


def test_delete_document_removes_index_entries(client: TestClient) -> None:
    uploaded = _upload(client, "leave.txt", LEAVE_DOC.encode("utf-8")).json()
    assert client.get("/api/index/status").json()["chunk_count"] > 0

    response = client.delete(f"/api/documents/{uploaded['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/documents/{uploaded['id']}").status_code == 404
    assert client.get("/api/index/status").json()["chunk_count"] == 0


def test_path_traversal_filename_is_sanitised(client: TestClient) -> None:
    response = _upload(client, "../../evil.txt", LEAVE_DOC.encode("utf-8"))
    assert response.status_code == 201
    assert response.json()["filename"] == "evil.txt"


def test_binary_content_disguised_as_text_is_rejected(client: TestClient) -> None:
    response = _upload(client, "fake.txt", bytes([0, 1, 2, 3, 4]) * 500)
    assert response.status_code == 422


def test_missing_document_returns_404(client: TestClient) -> None:
    response = client.get("/api/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
