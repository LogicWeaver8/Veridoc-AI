"""Chat orchestration: retrieval -> validation -> grounded answer -> citations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.enums import AnswerStatus, MessageRole
from app.repositories.conversation_repository import ConversationRepository
from app.services.citation_service import (
    build_citations,
    build_evidence_metadata,
    filter_relevant_chunks,
)
from app.services.generation_service import GenerationService
from app.services.retrieval_service import RetrievalService
from app.services.validation_service import ValidationService
from app.services.version_service import VersionService
from app.utils.text import expand_followup_query
from app.utils.time import utcnow

logger = get_logger("chat")

NOT_COVERED_ANSWER = (
    "I could not find this information in the uploaded documents. "
    "VeriDox AI answers only from indexed organisational documents and will not "
    "invent policies, numbers or procedures. Try rephrasing the question, or upload "
    "the relevant document if it is missing."
)

MAX_ANSWER_EVIDENCE = 5
HISTORY_MESSAGES = 6


@dataclass
class AnswerResult:
    answer: str
    answer_status: AnswerStatus
    confidence: int
    citations: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    requires_clarification: bool = False
    notes: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    expanded_query: str = ""
    assessment_reason: str = ""
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    created_at: datetime | None = None


class ChatService:
    def __init__(
        self,
        settings: Settings,
        retrieval: RetrievalService,
        validation: ValidationService,
        generation: GenerationService,
        versions: VersionService,
    ) -> None:
        self.settings = settings
        self.retrieval = retrieval
        self.validation = validation
        self.generation = generation
        self.versions = versions

    # -- core answer flow (no conversation persistence) --------------------
    def answer_question(
        self,
        session: Session,
        question: str,
        history: list[dict] | None = None,
        version_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
    ) -> AnswerResult:
        history = history or []
        previous_question = next(
            (str(message.get("content", "")) for message in reversed(history) if message.get("role") == "user"),
            None,
        )
        expanded_query = expand_followup_query(question, previous_question)

        selection = self.versions.select_versions(
            session, question, explicit_version_ids=version_ids, document_ids=document_ids
        )
        notes = list(selection.notes)

        if selection.requires_clarification:
            return AnswerResult(
                answer=selection.clarification_message or "Please specify which document version you mean.",
                answer_status=AnswerStatus.NOT_COVERED,
                confidence=0,
                requires_clarification=True,
                notes=notes,
                provider=self.generation.provider_name,
                model=self.generation.model_name,
                expanded_query=expanded_query,
                assessment_reason="Ambiguous document version.",
            )

        if not selection.allowed_version_ids:
            reason = selection.reason or "No processed document versions are available."
            return AnswerResult(
                answer=f"{NOT_COVERED_ANSWER}\n\n{reason}",
                answer_status=AnswerStatus.NOT_COVERED,
                confidence=0,
                notes=notes,
                provider=self.generation.provider_name,
                model=self.generation.model_name,
                expanded_query=expanded_query,
                assessment_reason=reason,
            )

        chunks = self.retrieval.retrieve(expanded_query, selection.allowed_version_ids)
        assessment = self.validation.assess(question, chunks)
        evidence_metadata = build_evidence_metadata(chunks)

        if assessment.status == AnswerStatus.NOT_COVERED:
            return AnswerResult(
                answer=NOT_COVERED_ANSWER,
                answer_status=AnswerStatus.NOT_COVERED,
                confidence=0,
                citations=[],
                evidence=evidence_metadata,
                notes=notes,
                provider=self.generation.provider_name,
                model=self.generation.model_name,
                expanded_query=expanded_query,
                assessment_reason=assessment.reason,
            )

        evidence_for_answer = filter_relevant_chunks(question, chunks)[:MAX_ANSWER_EVIDENCE]
        answer = self.generation.generate(
            question, evidence_for_answer, assessment.status, history
        )
        citations = build_citations(
            evidence_for_answer, limit=MAX_ANSWER_EVIDENCE, question=question
        )

        return AnswerResult(
            answer=answer,
            answer_status=assessment.status,
            confidence=assessment.confidence,
            citations=citations,
            evidence=evidence_metadata,
            notes=notes,
            provider=self.generation.provider_name,
            model=self.generation.model_name,
            expanded_query=expanded_query,
            assessment_reason=assessment.reason,
        )

    # -- conversation-aware ask ---------------------------------------------
    def ask(
        self,
        session: Session,
        question: str,
        conversation_id: str | None = None,
        version_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
    ) -> AnswerResult:
        repository = ConversationRepository(session)

        if conversation_id:
            conversation = repository.get(conversation_id)
            if conversation is None:
                raise NotFoundError("Conversation not found.")
        else:
            conversation = Conversation(id=str(uuid.uuid4()), title=self._title_from(question))
            repository.add(conversation)
            session.commit()

        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages[-HISTORY_MESSAGES:]
        ]

        user_message = ChatMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=question,
            citations=[],
            message_metadata={},
        )
        session.add(user_message)
        conversation.updated_at = utcnow()
        session.commit()

        result = self.answer_question(
            session, question, history, version_ids=version_ids, document_ids=document_ids
        )

        assistant_message = ChatMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=result.answer,
            answer_status=result.answer_status,
            confidence=result.confidence,
            citations=result.citations,
            message_metadata={
                "requires_clarification": result.requires_clarification,
                "notes": result.notes,
                "provider": result.provider,
                "model": result.model,
                "evidence": result.evidence,
                "expanded_query": result.expanded_query,
                "assessment_reason": result.assessment_reason,
            },
        )
        session.add(assistant_message)
        conversation.updated_at = utcnow()
        session.commit()

        result.conversation_id = conversation.id
        result.user_message_id = user_message.id
        result.assistant_message_id = assistant_message.id
        result.created_at = assistant_message.created_at
        return result

    # -- conversation management -------------------------------------------
    def create_conversation(self, session: Session, title: str | None = None) -> Conversation:
        conversation = Conversation(
            id=str(uuid.uuid4()), title=(title or "").strip()[:120] or "New conversation"
        )
        ConversationRepository(session).add(conversation)
        session.commit()
        return conversation

    def list_conversations(self, session: Session, limit: int = 100) -> list[Conversation]:
        return ConversationRepository(session).list(limit=limit)

    def get_conversation(self, session: Session, conversation_id: str) -> Conversation:
        conversation = ConversationRepository(session).get(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    def delete_conversation(self, session: Session, conversation_id: str) -> None:
        conversation = self.get_conversation(session, conversation_id)
        ConversationRepository(session).delete(conversation)
        session.commit()

    @staticmethod
    def _title_from(question: str) -> str:
        compact = " ".join(question.split())
        return (compact[:77] + "…") if len(compact) > 80 else compact
