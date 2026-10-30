"""Database access helpers for batch jobs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.batch_job import BatchJob


class BatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> BatchJob | None:
        return self.session.get(BatchJob, job_id)

    def list(self, limit: int = 50, offset: int = 0) -> list[BatchJob]:
        statement = (
            select(BatchJob).order_by(BatchJob.created_at.desc()).limit(limit).offset(offset)
        )
        return list(self.session.scalars(statement).all())
