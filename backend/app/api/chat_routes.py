"""Chat, conversation and citation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.api.serializers import answer_out, conversation_detail_out, conversation_out
from app.core.errors import ValidationFailedError
from app.schemas.chat import (
    AnswerOut,
    AskRequest,
    ConversationCreateRequest,
    ConversationDetailOut,
    ConversationOut,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=AnswerOut)
def ask_question(
    payload: AskRequest, request: Request, session: Session = Depends(get_session)
) -> AnswerOut:
    question = payload.question.strip()
    if not question:
        raise ValidationFailedError("The question cannot be empty.")

    container = get_container(request)
    chat: ChatService = container.chat
    result = chat.ask(
        session,
        question,
        conversation_id=payload.conversation_id,
        version_ids=payload.version_ids,
        document_ids=payload.document_ids,
    )
    return answer_out(result)


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    request: Request,
    payload: ConversationCreateRequest | None = None,
    session: Session = Depends(get_session),
) -> ConversationOut:
    container = get_container(request)
    conversation = container.chat.create_conversation(
        session, title=payload.title if payload else None
    )
    return conversation_out(conversation)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    request: Request,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> list[ConversationOut]:
    container = get_container(request)
    conversations = container.chat.list_conversations(session, limit=min(max(limit, 1), 200))
    return [conversation_out(conversation) for conversation in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str, request: Request, session: Session = Depends(get_session)
) -> ConversationDetailOut:
    container = get_container(request)
    conversation = container.chat.get_conversation(session, conversation_id)
    return conversation_detail_out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, request: Request, session: Session = Depends(get_session)
) -> Response:
    container = get_container(request)
    container.chat.delete_conversation(session, conversation_id)
    return Response(status_code=204)
