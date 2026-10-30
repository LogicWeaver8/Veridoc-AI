"""System, stats and index schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    llm_provider: str
    embedding_provider: str
    index_chunks: int


class StatsTotals(BaseModel):
    documents: int
    documents_completed: int
    documents_failed: int
    conversations: int
    messages: int
    chunks: int
    storage_bytes: int


class IndexSummary(BaseModel):
    chunk_count: int
    document_count: int
    backend: str
    embedding_provider: str
    embedding_model: str
    dimension: int
    updated_at: str | None = None
    needs_rebuild: bool
    size_bytes: int


class RecentDocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    created_at: datetime


class RecentConversationOut(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: datetime


class StatsOut(BaseModel):
    totals: StatsTotals
    documents_by_status: dict[str, int]
    ingestion_counts: dict[str, int]
    index: IndexSummary
    recent_documents: list[RecentDocumentOut]
    recent_conversations: list[RecentConversationOut]


class IndexStatusOut(BaseModel):
    chunk_count: int
    document_count: int
    backend: str
    embedding_provider: str
    embedding_model: str
    dimension: int
    updated_at: str | None = None
    needs_rebuild: bool
    size_bytes: int
    faiss_available: bool
    ocr_available: bool


class RebuildResponse(BaseModel):
    message: str
    chunk_count: int
    backend: str


class AppSettingsOut(BaseModel):
    app_name: str
    environment: str
    llm_provider: str
    llm_display_name: str
    llm_model: str
    llm_is_mock: bool
    llm_temperature: float
    llm_timeout_seconds: float
    ollama_base_url: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    vector_backend: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    embedding_batch_size: int
    retrieval_candidates: int
    final_evidence_chunks: int
    reranker_enabled: bool
    max_upload_mb: int
    max_batch_questions: int
    ocr_enabled: bool
    ocr_available: bool
    faiss_available: bool
