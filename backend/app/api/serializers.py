"""ORM -> API schema conversion helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.batch_job import BatchJob
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import VersionStatus
from app.schemas.batch import BatchJobOut
from app.schemas.chat import (
    AnswerOut,
    CitationOut,
    ConversationDetailOut,
    ConversationOut,
    MessageOut,
)
from app.schemas.document import DocumentOut, VersionOut
from app.services.chat_service import AnswerResult


def version_out(version: DocumentVersion) -> VersionOut:
    return VersionOut.model_validate(version)


def document_out(document: Document) -> DocumentOut:
    versions = sorted(document.versions, key=lambda item: item.version_number)
    active = next(
        (version for version in reversed(versions) if version.status == VersionStatus.ACTIVE),
        versions[-1] if versions else None,
    )
    metadata = document.doc_metadata or {}
    warnings = metadata.get("warnings", []) if isinstance(metadata, dict) else []

    return DocumentOut(
        id=document.id,
        filename=document.filename,
        file_type=document.file_type,
        status=document.status,
        size_bytes=document.size_bytes,
        file_hash=document.file_hash,
        error_message=document.error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
        version_count=len(versions),
        page_count=active.page_count if active else 0,
        chunk_count=active.chunk_count if active else 0,
        active_version=version_out(active) if active else None,
        versions=[version_out(version) for version in versions],
        warnings=list(warnings) if isinstance(warnings, list) else [],
    )


def message_out(message: ChatMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        answer_status=message.answer_status,
        confidence=message.confidence,
        citations=message.citations or [],
        message_metadata=message.message_metadata or {},
        created_at=message.created_at,
    )


def conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        message_count=len(conversation.messages),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def conversation_detail_out(conversation: Conversation) -> ConversationDetailOut:
    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        message_count=len(conversation.messages),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[message_out(message) for message in conversation.messages],
    )


def batch_job_out(job: BatchJob) -> BatchJobOut:
    progress = int(round(job.processed_questions / job.total_questions * 100)) if job.total_questions else 0
    return BatchJobOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        total_questions=job.total_questions,
        processed_questions=job.processed_questions,
        failed_questions=job.failed_questions,
        progress_percent=max(0, min(100, progress)),
        result_available=bool(job.result_path),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def answer_out(result: AnswerResult) -> AnswerOut:
    return AnswerOut(
        conversation_id=result.conversation_id or "",
        user_message_id=result.user_message_id or "",
        assistant_message_id=result.assistant_message_id or "",
        answer=result.answer,
        answer_status=result.answer_status.value,
        confidence=result.confidence,
        citations=[CitationOut(**citation) for citation in result.citations],
        evidence=result.evidence,
        requires_clarification=result.requires_clarification,
        notes=result.notes,
        provider=result.provider,
        model=result.model,
        created_at=result.created_at or datetime.now(UTC),
    )
