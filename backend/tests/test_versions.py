"""Document version intelligence tests."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.document_version import DocumentVersion
from app.models.enums import VersionStatus

POLICY_2025 = """LEAVE POLICY 2025

SECTION 2: ANNUAL LEAVE

Employees receive 12 days of annual paid leave per calendar year. Leave must be approved by a manager.
"""

POLICY_2026 = """LEAVE POLICY 2026

SECTION 2: ANNUAL LEAVE

Employees receive 18 days of annual paid leave per calendar year. Leave must be approved by a manager and requested ten business days in advance.
"""


def _create_leave_versions(client: TestClient) -> str:
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("Leave_Policy.txt", POLICY_2025.encode("utf-8"), "text/plain")},
        data={"effective_from": "2025-01-01", "version_label": "2025"},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    version = client.post(
        f"/api/documents/{document_id}/versions",
        files={"file": ("Leave_Policy.txt", POLICY_2026.encode("utf-8"), "text/plain")},
        data={"effective_from": "2026-01-01", "version_label": "2026"},
    )
    assert version.status_code == 201, version.text
    body = version.json()
    assert body["version_count"] == 2
    return document_id


def test_current_version_answers_current_question(client: TestClient) -> None:
    _create_leave_versions(client)

    body = client.post(
        "/api/chat/ask", json={"question": "How many annual leave days do employees receive?"}
    ).json()

    assert body["answer_status"] == "answered"
    assert "18" in body["answer"]
    assert {citation["version_label"] for citation in body["citations"]} == {"2026"}


def test_historical_year_selects_older_version(client: TestClient) -> None:
    _create_leave_versions(client)

    body = client.post(
        "/api/chat/ask",
        json={"question": "How many annual leave days did employees receive in 2025?"},
    ).json()

    assert body["answer_status"] == "answered"
    assert "12" in body["answer"]
    assert "18" not in body["answer"]
    assert {citation["version_label"] for citation in body["citations"]} == {"2025"}


def test_missing_year_returns_not_covered(client: TestClient) -> None:
    _create_leave_versions(client)

    body = client.post(
        "/api/chat/ask",
        json={"question": "What was the annual leave policy in 2030?"},
    ).json()

    assert body["answer_status"] == "not_covered"
    assert body["requires_clarification"] is False
    assert "2030" in body["answer"] or any("2030" in note for note in body["notes"])


def test_version_statuses_are_updated(client: TestClient) -> None:
    document_id = _create_leave_versions(client)

    versions = client.get(f"/api/documents/{document_id}/versions").json()
    by_label = {version["version_label"]: version for version in versions}
    assert by_label["2025"]["status"] == "superseded"
    assert by_label["2026"]["status"] == "active"
    assert by_label["2025"]["effective_from"] == "2025-01-01"
    assert by_label["2026"]["version_number"] == 2


def test_ambiguous_versions_require_clarification(client: TestClient, app) -> None:
    document_id = _create_leave_versions(client)
    assert document_id

    with app.state.container.session_factory() as session:
        versions = session.scalars(select(DocumentVersion)).all()
        assert len(versions) == 2
        for version in versions:
            version.effective_from = date(2026, 1, 1)
            version.status = VersionStatus.ACTIVE
        session.commit()

    body = client.post(
        "/api/chat/ask", json={"question": "How many annual leave days do employees receive?"}
    ).json()

    assert body["requires_clarification"] is True
    assert body["answer_status"] == "not_covered"
    assert "please specify" in body["answer"].lower()
    assert body["citations"] == []


def test_duplicate_version_content_is_rejected(client: TestClient) -> None:
    document_id = _create_leave_versions(client)
    response = client.post(
        f"/api/documents/{document_id}/versions",
        files={"file": ("Leave_Policy.txt", POLICY_2026.encode("utf-8"), "text/plain")},
        data={"effective_from": "2027-01-01", "version_label": "2027"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_document"


def test_version_for_unknown_document_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/documents/00000000-0000-0000-0000-000000000000/versions",
        files={"file": ("Leave_Policy.txt", POLICY_2026.encode("utf-8"), "text/plain")},
        data={"effective_from": "2026-01-01", "version_label": "2026"},
    )
    assert response.status_code == 404


def test_duplicate_version_label_is_rejected(client: TestClient) -> None:
    document_id = _create_leave_versions(client)
    response = client.post(
        f"/api/documents/{document_id}/versions",
        files={"file": ("Leave_Policy.txt", POLICY_2025.encode("utf-8"), "text/plain")},
        data={"effective_from": "2024-01-01", "version_label": "2026"},
    )
    assert response.status_code == 422
