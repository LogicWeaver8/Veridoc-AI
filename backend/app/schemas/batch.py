"""Batch job response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BatchJobOut(BaseModel):
    id: str
    filename: str
    status: str
    total_questions: int
    processed_questions: int
    failed_questions: int
    progress_percent: int
    result_available: bool
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class BatchJobListOut(BaseModel):
    items: list[BatchJobOut]
    total: int
