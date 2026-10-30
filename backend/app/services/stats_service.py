"""Dashboard statistics."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentStatus
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.services.index_manager import IndexManager


class StatsService:
    def __init__(self, settings: Settings, index: IndexManager) -> None:
        self.settings = settings
        self.index = index

    def dashboard(self, session: Session) -> dict:
        status_rows = session.execute(
            select(Document.status, func.count(Document.id)).group_by(Document.status)
        ).all()
        by_status = {status: int(count) for status, count in status_rows}

        total_documents = sum(by_status.values())
        total_chunks = int(session.scalar(select(func.count(DocumentChunk.id))) or 0)
        total_conversations = int(session.scalar(select(func.count(Conversation.id))) or 0)
        total_messages = int(session.scalar(select(func.count(ChatMessage.id))) or 0)
        storage_bytes = int(session.scalar(select(func.sum(Document.size_bytes))) or 0)

        processing_statuses = {
            DocumentStatus.EXTRACTING,
            DocumentStatus.CHUNKING,
            DocumentStatus.EMBEDDING,
            DocumentStatus.INDEXING,
        }
        ingestion_counts = {
            "processed": by_status.get(DocumentStatus.COMPLETED, 0),
            "processing": sum(by_status.get(status, 0) for status in processing_statuses),
            "pending": by_status.get(DocumentStatus.UPLOADED, 0),
            "failed": by_status.get(DocumentStatus.FAILED, 0),
        }

        recent_documents = DocumentRepository(session).recent(limit=5)
        recent_conversations = ConversationRepository(session).list(limit=5)
        index = self.index.stats()

        return {
            "totals": {
                "documents": total_documents,
                "documents_completed": ingestion_counts["processed"],
                "documents_failed": ingestion_counts["failed"],
                "conversations": total_conversations,
                "messages": total_messages,
                "chunks": total_chunks,
                "storage_bytes": storage_bytes,
            },
            "documents_by_status": by_status,
            "ingestion_counts": ingestion_counts,
            "index": {
                "chunk_count": index.chunk_count,
                "document_count": index.document_count,
                "backend": index.backend,
                "embedding_provider": index.embedding_provider,
                "embedding_model": index.embedding_model,
                "dimension": index.dimension,
                "updated_at": index.updated_at,
                "needs_rebuild": index.needs_rebuild,
                "size_bytes": index.size_bytes,
            },
            "recent_documents": [
                {
                    "id": document.id,
                    "filename": document.filename,
                    "file_type": document.file_type,
                    "status": document.status,
                    "created_at": document.created_at,
                }
                for document in recent_documents
            ],
            "recent_conversations": [
                {
                    "id": conversation.id,
                    "title": conversation.title,
                    "message_count": len(conversation.messages),
                    "updated_at": conversation.updated_at,
                }
                for conversation in recent_conversations
            ],
        }
