"""Chat, citation, follow-up and abstention tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.sample_docs import LEAVE_DOC, TRAVEL_DOC


def _upload(client: TestClient, filename: str, text: str):
    response = client.post(
        "/api/documents/upload",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_grounded_answer_includes_deterministic_citations(client: TestClient) -> None:
    _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC)

    response = client.post(
        "/api/chat/ask",
        json={"question": "How many annual leave days do employees receive?"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["answer_status"] == "answered"
    assert body["confidence"] > 0
    assert "18" in body["answer"]
    assert body["provider"] == "mock"
    assert body["conversation_id"]
    assert body["citations"], "answered responses must include citations"

    citation = body["citations"][0]
    assert citation["document_name"] == "Leave_Policy_2026.txt"
    assert citation["version_label"] == "2026"
    assert citation["page_number"] == 1
    assert citation["section"] == "ANNUAL LEAVE"
    assert "18 days" in citation["excerpt"]
    assert citation["document_id"]

    assert body["evidence"]
    assert body["notes"]


def test_citation_comes_from_the_relevant_document(client: TestClient) -> None:
    _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC)
    _upload(client, "Travel_Policy_2026.txt", TRAVEL_DOC)

    body = client.post(
        "/api/chat/ask",
        json={"question": "What is the meal allowance for domestic travel?"},
    ).json()

    assert body["answer_status"] == "answered"
    assert "75" in body["answer"]
    names = {citation["document_name"] for citation in body["citations"]}
    assert names == {"Travel_Policy_2026.txt"}


def test_follow_up_question_uses_conversation_context(client: TestClient) -> None:
    _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC)

    first = client.post(
        "/api/chat/ask", json={"question": "How many annual leave days do employees receive?"}
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/api/chat/ask",
        json={"question": "What about sick leave?", "conversation_id": conversation_id},
    ).json()

    assert second["conversation_id"] == conversation_id
    assert second["answer_status"] == "answered"
    assert "12" in second["answer"]
    assert second["citations"]

    conversation = client.get(f"/api/chat/conversations/{conversation_id}").json()
    assert conversation["message_count"] == 4
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert conversation["messages"][2]["content"] == "What about sick leave?"
    assert conversation["messages"][3]["citations"]


def test_missing_evidence_returns_not_covered(client: TestClient) -> None:
    _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC)

    body = client.post(
        "/api/chat/ask",
        json={"question": "Does the company provide a sponsored gym membership?"},
    ).json()

    assert body["answer_status"] == "not_covered"
    assert body["confidence"] == 0
    assert body["citations"] == []
    assert "could not find" in body["answer"].lower()


def test_partial_coverage_is_reported(client: TestClient) -> None:
    _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC)

    body = client.post(
        "/api/chat/ask",
        json={
            "question": (
                "What is the annual leave entitlement and does the company provide "
                "a gym membership benefit?"
            )
        },
    ).json()

    assert body["answer_status"] == "partially_answered"
    assert 0 < body["confidence"] <= 72
    assert body["citations"]


def test_ask_without_documents_abstains(client: TestClient) -> None:
    body = client.post(
        "/api/chat/ask", json={"question": "What is the annual leave policy?"}
    ).json()

    assert body["answer_status"] == "not_covered"
    assert body["conversation_id"]
    assert body["citations"] == []
    assert "no processed document versions" in body["answer"].lower()


def test_empty_question_is_rejected(client: TestClient) -> None:
    response = client.post("/api/chat/ask", json={"question": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_ask_for_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/chat/ask",
        json={
            "question": "What is the leave policy?",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404


def test_conversation_crud(client: TestClient) -> None:
    created = client.post("/api/chat/conversations", json={"title": "Policy questions"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert created.json()["message_count"] == 0

    listed = client.get("/api/chat/conversations")
    assert listed.status_code == 200
    assert any(item["id"] == conversation_id for item in listed.json())

    detail = client.get(f"/api/chat/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []

    deleted = client.delete(f"/api/chat/conversations/{conversation_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/chat/conversations/{conversation_id}").status_code == 404


def test_conversation_history_survives_new_client_session(client: TestClient) -> None:
    _upload(client, "Leave_Policy_2026.txt", LEAVE_DOC)
    conversation_id = client.post(
        "/api/chat/ask", json={"question": "How many annual leave days do employees receive?"}
    ).json()["conversation_id"]

    conversations = client.get("/api/chat/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["message_count"] == 2
