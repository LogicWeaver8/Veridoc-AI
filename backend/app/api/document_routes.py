"""Document management endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.api.serializers import document_out
from app.core.errors import (
    AppError,
    DuplicateDocumentError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    DocumentListOut,
    DocumentOut,
    DuplicateUploadOut,
    MultiUploadOut,
    UploadErrorOut,
)
from app.utils.files import (
    delete_stored_file,
    file_type_from_extension,
    resolve_stored_path,
    save_upload,
)

logger = get_logger("documents_api")

router = APIRouter(prefix="/documents", tags=["documents"])
MAX_MULTI_FILES = 20


def _validate_text_payload(container, stored) -> None:
    """Reject binary payloads mislabelled as TXT/Markdown before they are stored.

    Text extraction is cheap for plain-text files, so it runs synchronously and
    errors surface as a 422 on the upload request itself.
    """
    file_type = file_type_from_extension(stored.extension)
    if file_type not in {"txt", "markdown"}:
        return
    path = resolve_stored_path(stored.relative_path, container.settings)
    container.extraction.extract(path, file_type)


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    effective_from: date | None = Form(default=None),
    version_label: str | None = Form(default=None, max_length=64),
    session: Session = Depends(get_session),
) -> DocumentOut:
    container = get_container(request)
    stored = await save_upload(file, container.settings)
    try:
        _validate_text_payload(container, stored)
        document, version = container.ingestion.create_document(
            session, stored, effective_from=effective_from, version_label=version_label
        )
    except Exception:
        delete_stored_file(stored.relative_path, container.settings)
        raise

    background_tasks.add_task(container.ingestion.process_document, document.id, version.id)
    return document_out(document)


@router.post("/upload-multiple", response_model=MultiUploadOut)
async def upload_multiple_documents(
    background_tasks: BackgroundTasks,
    request: Request,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> MultiUploadOut:
    if not files:
        raise ValidationFailedError("No files were provided.")
    if len(files) > MAX_MULTI_FILES:
        raise ValidationFailedError(f"Upload at most {MAX_MULTI_FILES} files at once.")

    container = get_container(request)
    uploaded: list[DocumentOut] = []
    duplicates: list[DuplicateUploadOut] = []
    errors: list[UploadErrorOut] = []

    for upload in files:
        filename = upload.filename or "document"
        stored = None
        try:
            stored = await save_upload(upload, container.settings)
            _validate_text_payload(container, stored)
            document, version = container.ingestion.create_document(session, stored)
            background_tasks.add_task(
                container.ingestion.process_document, document.id, version.id
            )
            uploaded.append(document_out(document))
        except DuplicateDocumentError as exc:
            if stored:
                delete_stored_file(stored.relative_path, container.settings)
            duplicates.append(
                DuplicateUploadOut(
                    filename=filename,
                    existing_document_id=exc.details.get("existing_document_id"),
                    message=exc.message,
                )
            )
        except AppError as exc:
            if stored:
                delete_stored_file(stored.relative_path, container.settings)
            errors.append(UploadErrorOut(filename=filename, message=exc.message))
        except Exception:
            logger.exception("Unexpected failure while uploading %s", filename)
            if stored:
                delete_stored_file(stored.relative_path, container.settings)
            errors.append(
                UploadErrorOut(filename=filename, message="The file could not be processed.")
            )

    return MultiUploadOut(uploaded=uploaded, duplicates=duplicates, errors=errors)


@router.get("", response_model=DocumentListOut)
def list_documents(
    request: Request,
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None),
    file_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DocumentListOut:
    documents, total = DocumentRepository(session).list(
        search=search, status=status, file_type=file_type, limit=limit, offset=offset
    )
    return DocumentListOut(
        items=[document_out(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str, request: Request, session: Session = Depends(get_session)
) -> DocumentOut:
    document = DocumentRepository(session).get(document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    return document_out(document)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str, request: Request, session: Session = Depends(get_session)
) -> Response:
    container = get_container(request)
    container.ingestion.delete_document(session, document_id)
    return Response(status_code=204)
