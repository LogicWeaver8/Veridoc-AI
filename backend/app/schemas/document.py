"""Document and version response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    version_label: str
    version_number: int
    effective_from: date
    effective_to: date | None = None
    status: str
    page_count: int
    chunk_count: int
    size_bytes: int
    file_hash: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    size_bytes: int
    file_hash: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    version_count: int
    page_count: int
    chunk_count: int
    active_version: VersionOut | None = None
    versions: list[VersionOut] = []
    warnings: list[str] = []


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class DuplicateUploadOut(BaseModel):
    filename: str
    existing_document_id: str | None = None
    message: str


class UploadErrorOut(BaseModel):
    filename: str
    message: str


class MultiUploadOut(BaseModel):
    uploaded: list[DocumentOut]
    duplicates: list[DuplicateUploadOut]
    errors: list[UploadErrorOut]
