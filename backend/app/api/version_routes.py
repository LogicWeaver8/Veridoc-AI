"""Document version endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.api.serializers import document_out, version_out
from app.core.errors import NotFoundError
from app.models.document_version import DocumentVersion
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentOut, VersionOut
from app.utils.files import (
    delete_stored_file,
    file_type_from_extension,
    resolve_stored_path,
    save_upload,
)

router = APIRouter(prefix="/documents", tags=["versions"])


@router.get("/{document_id}/versions", response_model=list[VersionOut])
def list_versions(
    document_id: str, request: Request, session: Session = Depends(get_session)
) -> list[VersionOut]:
    if DocumentRepository(session).get(document_id, with_versions=False) is None:
        raise NotFoundError("Document not found.")
    versions = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    ).all()
    return [version_out(version) for version in versions]


@router.post("/{document_id}/versions", response_model=DocumentOut, status_code=201)
async def add_document_version(
    document_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    effective_from: date | None = Form(default=None),
    version_label: str | None = Form(default=None, max_length=64),
    supersedes_version_id: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> DocumentOut:
    container = get_container(request)
    stored = await save_upload(file, container.settings)
    try:
        file_type = file_type_from_extension(stored.extension)
        if file_type in {"txt", "markdown"}:
            container.extraction.extract(
                resolve_stored_path(stored.relative_path, container.settings), file_type
            )
        version = container.ingestion.add_version(
            session,
            document_id,
            stored,
            effective_from=effective_from,
            version_label=version_label,
            supersedes_version_id=supersedes_version_id,
        )
    except Exception:
        delete_stored_file(stored.relative_path, container.settings)
        raise

    background_tasks.add_task(container.ingestion.process_document, document_id, version.id)
    session.expire_all()
    document = DocumentRepository(session).get(document_id)
    if document is None:  # pragma: no cover - raced deletion
        raise NotFoundError("Document not found.")
    return document_out(document)
