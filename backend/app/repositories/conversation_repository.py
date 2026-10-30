"""Database access helpers for conversations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, conversation_id: str, with_messages: bool = True) -> Conversation | None:
        statement = select(Conversation).where(Conversation.id == conversation_id)
        if with_messages:
            statement = statement.options(selectinload(Conversation.messages))
        return self.session.scalar(statement)

    def list(self, limit: int = 100, offset: int = 0) -> list[Conversation]:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement).all())

    def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.session.delete(conversation)
