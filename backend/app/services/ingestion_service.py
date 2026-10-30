"""Document ingestion pipeline.

uploaded -> extracting -> chunking -> embedding -> indexing -> completed (or failed)

Each stage is committed so the UI can poll progress. Chunks are written to the
DB before indexing, which means a failed index can be repaired with the rebuild
endpoint without re-uploading the document.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.errors import AppError, DuplicateDocumentError, NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus, VersionStatus
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionService
from app.services.index_manager import ChunkRecord, IndexManager
from app.services.version_service import VersionService
from app.utils.files import StoredFile, delete_stored_file, file_type_from_extension, resolve_stored_path
from app.utils.text import TextChunker
from app.utils.time import utcnow

logger = get_logger("ingestion")


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        extraction: ExtractionService,
        embeddings: EmbeddingService,
        index: IndexManager,
        versions: VersionService,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.settings = settings
        self.extraction = extraction
        self.embeddings = embeddings
        self.index = index
        self.versions = versions
        self.session_factory = session_factory
        self.chunker = TextChunker(settings.chunk_size_tokens, settings.chunk_overlap_tokens)

    # -- creating documents -------------------------------------------------
    def create_document(
        self,
        session: Session,
        stored: StoredFile,
        effective_from: date | None = None,
        version_label: str | None = None,
    ) -> tuple[Document, DocumentVersion]:
        existing = session.scalar(select(Document).where(Document.file_hash == stored.sha256))
        if existing is not None:
            raise DuplicateDocumentError(
                f"This file has already been uploaded as '{existing.filename}'.",
                existing_document_id=existing.id,
            )

        document_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        effective = effective_from or date.today()
        file_type = file_type_from_extension(stored.extension)

        try:
            label = self.versions.next_label(session, document_id, version_label, effective)
        except ValueError as exc:
            raise ValidationFailedError(str(exc)) from exc

        document = Document(
            id=document_id,
            filename=stored.original_filename,
            file_type=file_type,
            stored_path=stored.relative_path,
            file_hash=stored.sha256,
            size_bytes=stored.size_bytes,
            status=DocumentStatus.UPLOADED,
            doc_metadata={},
        )
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_label=label,
            version_number=1,
            effective_from=effective,
            status=VersionStatus.ACTIVE,
            file_path=stored.relative_path,
            file_hash=stored.sha256,
            size_bytes=stored.size_bytes,
        )
        session.add_all([document, version])
        session.commit()
        logger.info("Created document %s (%s) version %s", document.filename, document.id, label)
        return document, version

    def add_version(
        self,
        session: Session,
        document_id: str,
        stored: StoredFile,
        effective_from: date | None = None,
        version_label: str | None = None,
        supersedes_version_id: str | None = None,
    ) -> DocumentVersion:
        document = session.get(Document, document_id)
        if document is None:
            raise NotFoundError("Document not found.")

        new_type = file_type_from_extension(stored.extension)
        if new_type != document.file_type:
            raise ValidationFailedError(
                f"Version files must have the same type as the original document "
                f"({document.file_type})."
            )

        if supersedes_version_id is not None:
            superseded = session.get(DocumentVersion, supersedes_version_id)
            if superseded is None or superseded.document_id != document_id:
                raise ValidationFailedError("The version to supersede does not belong to this document.")

        effective = effective_from or date.today()
        version_number = self.versions.next_version_number(session, document_id)
        try:
            label = self.versions.next_label(session, document_id, version_label, effective)
        except ValueError as exc:
            raise ValidationFailedError(str(exc)) from exc

        # Checked after the label so a duplicate label reports a validation
        # error rather than the less specific duplicate-content error.
        duplicate = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.file_hash == stored.sha256,
            )
        )
        if duplicate is not None:
            raise DuplicateDocumentError(
                f"This file is identical to version '{duplicate.version_label}' of this document."
            )

        version = DocumentVersion(
            id=str(uuid.uuid4()),
            document_id=document_id,
            version_label=label,
            version_number=version_number,
            effective_from=effective,
            supersedes_version_id=supersedes_version_id,
            status=VersionStatus.ACTIVE,
            file_path=stored.relative_path,
            file_hash=stored.sha256,
            size_bytes=stored.size_bytes,
        )
        session.add(version)
        document.stored_path = stored.relative_path
        document.file_hash = stored.sha256
        document.status = DocumentStatus.UPLOADED
        document.error_message = None
        self.versions.refresh_statuses(session, document_id)
        session.commit()
        logger.info(
            "Added version %s to document %s (%s)", label, document.filename, document.id
        )
        return version

    # -- background processing ---------------------------------------------
    def process_document(self, document_id: str, version_id: str) -> None:
        """Run the full pipeline. Called from a FastAPI BackgroundTask."""
        session = self.session_factory()
        document: Document | None = None
        version: DocumentVersion | None = None
        try:
            document = session.get(Document, document_id)
            version = session.get(DocumentVersion, version_id)
            if document is None or version is None:
                logger.warning("Skipping processing; document/version disappeared.")
                return

            document.status = DocumentStatus.EXTRACTING
            document.error_message = None
            session.commit()

            path = resolve_stored_path(version.file_path, self.settings)
            extraction = self.extraction.extract(path, document.file_type)

            document.status = DocumentStatus.CHUNKING
            session.commit()

            text_chunks = self.chunker.chunk_pages(
                [(page.page_number, page.text) for page in extraction.pages]
            )
            if not text_chunks:
                raise ValidationFailedError("No usable text chunks could be produced from this document.")

            # Re-processing safety: clear old chunks/index entries for this version.
            session.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id))
            self.index.remove_version(version.id)

            db_chunks: list[DocumentChunk] = []
            records: list[ChunkRecord] = []
            for text_chunk in text_chunks:
                chunk_id = str(uuid.uuid4())
                db_chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        document_id=document.id,
                        version_id=version.id,
                        chunk_index=text_chunk.chunk_index,
                        content=text_chunk.text,
                        page_number=text_chunk.page_number,
                        section=text_chunk.section,
                        token_count=text_chunk.token_count,
                    )
                )
                records.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        document_id=document.id,
                        version_id=version.id,
                        chunk_index=text_chunk.chunk_index,
                        text=text_chunk.text,
                        page_number=text_chunk.page_number,
                        section=text_chunk.section,
                        document_name=document.filename,
                        version_label=version.version_label,
                        token_count=text_chunk.token_count,
                    )
                )
            session.add_all(db_chunks)

            document.status = DocumentStatus.EMBEDDING
            session.commit()

            vectors = self.embeddings.embed_texts([record.text for record in records])

            document.status = DocumentStatus.INDEXING
            session.commit()

            self.index.add_chunks(records, vectors)

            version.page_count = len([page for page in extraction.pages if page.text.strip()])
            version.chunk_count = len(records)
            version.completed_at = utcnow()
            version.error_message = None
            document.status = DocumentStatus.COMPLETED
            document.doc_metadata = {
                "page_count": version.page_count,
                "chunk_count": version.chunk_count,
                "warnings": extraction.warnings,
                "ocr_pages": [page.page_number for page in extraction.pages if page.used_ocr],
                "embedding_signature": self.embeddings.signature,
            }
            session.commit()
            logger.info(
                "Ingested %s (%d chunks, %d pages)",
                document.filename, version.chunk_count, version.page_count,
            )

        except AppError as exc:
            self._mark_failed(session, document_id, version_id, exc.message)
        except Exception as exc:  # unexpected failure; log privately, store a safe message
            logger.exception("Unexpected ingestion failure for document %s", document_id)
            self._mark_failed(
                session, document_id, version_id,
                "Processing failed unexpectedly. Check the server logs for details.",
            )
        finally:
            session.close()

    def _mark_failed(
        self, session: Session, document_id: str, version_id: str, message: str
    ) -> None:
        session.rollback()
        try:
            document = session.get(Document, document_id)
            version = session.get(DocumentVersion, version_id)
            if document is not None:
                document.status = DocumentStatus.FAILED
                document.error_message = message
            if version is not None:
                version.status = VersionStatus.FAILED
                version.error_message = message
            session.commit()
        except Exception:  # pragma: no cover - DB failure while reporting a failure
            session.rollback()
            logger.exception("Could not persist failed status for %s", document_id)

    # -- deletion and maintenance ------------------------------------------
    def delete_document(self, session: Session, document_id: str) -> None:
        document = session.get(Document, document_id)
        if document is None:
            raise NotFoundError("Document not found.")

        file_paths = {document.stored_path}
        file_paths.update(version.file_path for version in document.versions)

        self.index.remove_document(document_id)
        session.delete(document)
        session.commit()

        for relative_path in file_paths:
            delete_stored_file(relative_path, self.settings)
        logger.info("Deleted document %s and its index entries", document_id)

    def rebuild_index(self, session: Session) -> int:
        rows = session.execute(
            select(DocumentChunk, Document, DocumentVersion)
            .join(Document, DocumentChunk.document_id == Document.id)
            .join(DocumentVersion, DocumentChunk.version_id == DocumentVersion.id)
        ).all()

        records = [
            ChunkRecord(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                version_id=chunk.version_id,
                chunk_index=chunk.chunk_index,
                text=chunk.content,
                page_number=chunk.page_number,
                section=chunk.section,
                document_name=document.filename,
                version_label=version.version_label,
                token_count=chunk.token_count,
            )
            for chunk, document, version in rows
        ]
        count = self.index.rebuild(records)
        logger.info("Rebuilt index with %d chunks", count)
        return count

    def recover_interrupted_documents(self) -> None:
        """Mark unfinished documents as failed after a restart."""
        interrupted = {
            DocumentStatus.UPLOADED,
            DocumentStatus.EXTRACTING,
            DocumentStatus.CHUNKING,
            DocumentStatus.EMBEDDING,
            DocumentStatus.INDEXING,
        }
        session = self.session_factory()
        try:
            documents = list(
                session.scalars(select(Document).where(Document.status.in_(interrupted))).all()
            )
            for document in documents:
                document.status = DocumentStatus.FAILED
                document.error_message = (
                    "Processing was interrupted by a server restart. Please re-upload the document."
                )
                for version in document.versions:
                    if version.completed_at is None:
                        version.status = VersionStatus.FAILED
                        version.error_message = document.error_message
            if documents:
                session.commit()
                logger.warning("Marked %d interrupted document(s) as failed.", len(documents))
        finally:
            session.close()
