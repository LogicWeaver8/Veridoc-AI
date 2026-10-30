"""Chat request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CitationOut(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    version_id: str
    version_label: str
    page_number: int | None = None
    section: str | None = None
    excerpt: str
    relevance: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, description="Natural-language question")
    conversation_id: str | None = None
    version_ids: list[str] | None = None
    document_ids: list[str] | None = None


class AnswerOut(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    answer: str
    answer_status: str
    confidence: int
    citations: list[CitationOut] = []
    evidence: list[dict[str, Any]] = []
    requires_clarification: bool = False
    notes: list[str] = []
    provider: str
    model: str
    created_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    answer_status: str | None = None
    confidence: int | None = None
    citations: list[dict[str, Any]] = []
    message_metadata: dict[str, Any] = {}
    created_at: datetime


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ConversationOut(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []
