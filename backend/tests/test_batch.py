"""CSV batch processing tests."""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from tests.sample_docs import LEAVE_DOC


def _create_document(client: TestClient) -> None:
    response = client.post(
        "/api/documents/upload",
        files={"file": ("Leave_Policy_2026.txt", LEAVE_DOC.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201


def _upload_csv(client: TestClient, filename: str, content: bytes):
    return client.post(
        "/api/batch/upload",
        files={"file": (filename, content, "text/csv")},
    )


def test_batch_job_processes_questions_and_downloads_results(client: TestClient) -> None:
    _create_document(client)
    csv_content = (
        "question\n"
        "How many annual leave days do employees receive?\n"
        "Does the company provide a sponsored gym membership?\n"
    ).encode("utf-8")

    response = _upload_csv(client, "questions.csv", csv_content)
    assert response.status_code == 201
    job = response.json()
    assert job["total_questions"] == 2

    status = client.get(f"/api/batch/{job['id']}/status").json()
    assert status["status"] == "completed"
    assert status["processed_questions"] == 2
    assert status["progress_percent"] == 100
    assert status["result_available"] is True

    download = client.get(f"/api/batch/{job['id']}/download")
    assert download.status_code == 200
    assert "text/csv" in download.headers["content-type"]

    rows = list(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))
    assert len(rows) == 2
    assert list(rows[0].keys()) == [
        "question",
        "answer",
        "status",
        "source_document",
        "document_version",
        "page_number",
        "section",
    ]
    assert rows[0]["status"] == "answered"
    assert rows[0]["source_document"] == "Leave_Policy_2026.txt"
    assert rows[0]["page_number"] == "1"
    assert "18" in rows[0]["answer"]
    assert rows[1]["status"] == "not_covered"


def test_batch_jobs_are_listed(client: TestClient) -> None:
    _create_document(client)
    _upload_csv(client, "questions.csv", b"question\nHow many annual leave days?\n")

    jobs = client.get("/api/batch/jobs").json()
    assert jobs["total"] >= 1
    assert jobs["items"][0]["filename"] == "questions.csv"


def test_csv_without_question_column_is_rejected(client: TestClient) -> None:
    response = _upload_csv(client, "bad.csv", b"prompt\nWhat is the leave policy?\n")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "batch_job_error"


def test_csv_with_too_many_questions_is_rejected(client_factory) -> None:
    client = client_factory(max_batch_questions=2)
    _create_document(client)
    content = b"question\nOne?\nTwo?\nThree?\n"
    response = _upload_csv(client, "many.csv", content)
    assert response.status_code == 400
    assert "limit" in response.json()["error"]["message"].lower()


def test_empty_csv_is_rejected(client: TestClient) -> None:
    response = _upload_csv(client, "empty.csv", b"question\n")
    assert response.status_code == 400


def test_non_csv_batch_upload_is_rejected(client: TestClient) -> None:
    response = _upload_csv(client, "questions.txt", b"question\nWhat is the leave policy?\n")
    assert response.status_code == 422
