"""Database access helpers for documents."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, document_id: str, with_versions: bool = True) -> Document | None:
        statement = select(Document).where(Document.id == document_id)
        if with_versions:
            statement = statement.options(selectinload(Document.versions))
        return self.session.scalar(statement)

    def get_by_hash(self, file_hash: str) -> Document | None:
        return self.session.scalar(select(Document).where(Document.file_hash == file_hash))

    def list(
        self,
        search: str | None = None,
        status: str | None = None,
        file_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        conditions = []
        if search:
            conditions.append(Document.filename.ilike(f"%{search.strip()}%"))
        if status:
            conditions.append(Document.status == status)
        if file_type:
            conditions.append(Document.file_type == file_type)

        statement = (
            select(Document)
            .options(selectinload(Document.versions))
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count(Document.id))
        for condition in conditions:
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        documents = list(self.session.scalars(statement).all())
        total = int(self.session.scalar(count_statement) or 0)
        return documents, total

    def recent(self, limit: int = 5) -> list[Document]:
        statement = (
            select(Document)
            .options(selectinload(Document.versions))
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())
