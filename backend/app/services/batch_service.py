"""CSV batch question answering with progress tracking and downloadable results."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.errors import BatchJobError, NotFoundError
from app.core.logging import get_logger
from app.models.batch_job import BatchJob
from app.models.enums import BatchStatus
from app.repositories.batch_repository import BatchRepository
from app.services.chat_service import AnswerResult, ChatService
from app.utils.files import StoredFile, resolve_stored_path
from app.utils.time import utcnow

logger = get_logger("batch")

RESULT_COLUMNS = [
    "question",
    "answer",
    "status",
    "source_document",
    "document_version",
    "page_number",
    "section",
]


class BatchService:
    def __init__(
        self,
        settings: Settings,
        chat: ChatService,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.settings = settings
        self.chat = chat
        self.session_factory = session_factory

    # -- job creation -------------------------------------------------------
    def create_job(self, session: Session, stored: StoredFile) -> BatchJob:
        questions = self._read_questions(resolve_stored_path(stored.relative_path, self.settings))
        if not questions:
            raise BatchJobError("The CSV contains no questions.")
        if len(questions) > self.settings.max_batch_questions:
            raise BatchJobError(
                f"This CSV has {len(questions)} questions; the limit is "
                f"{self.settings.max_batch_questions} per job."
            )

        job = BatchJob(
            id=str(uuid.uuid4()),
            filename=stored.original_filename,
            stored_path=stored.relative_path,
            status=BatchStatus.PENDING,
            total_questions=len(questions),
        )
        session.add(job)
        session.commit()
        logger.info("Created batch job %s with %d questions", job.id, len(questions))
        return job

    # -- processing ----------------------------------------------------------
    def process_job(self, job_id: str) -> None:
        """Answer every question. Called from a FastAPI BackgroundTask."""
        session = self.session_factory()
        try:
            job = session.get(BatchJob, job_id)
            if job is None:
                logger.warning("Batch job %s disappeared before processing.", job_id)
                return

            job.status = BatchStatus.PROCESSING
            job.error_message = None
            session.commit()

            questions = self._read_questions(resolve_stored_path(job.stored_path, self.settings))
            results_path = self.settings.batch_results_dir / f"{job.id}.csv"
            self.settings.batch_results_dir.mkdir(parents=True, exist_ok=True)

            with results_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS)
                writer.writeheader()
                handle.flush()

                for index, question in enumerate(questions, start=1):
                    try:
                        answer = self.chat.answer_question(session, question)
                        row = self._row_for(question, answer)
                    except Exception:
                        logger.exception("Batch question %d/%d failed", index, len(questions))
                        session.rollback()
                        job = session.get(BatchJob, job_id)
                        if job is None:
                            raise BatchJobError("The batch job no longer exists.")
                        row = {
                            "question": question,
                            "answer": "This question could not be processed. See server logs for details.",
                            "status": "error",
                            "source_document": "",
                            "document_version": "",
                            "page_number": "",
                            "section": "",
                        }
                        job.failed_questions += 1

                    writer.writerow(row)
                    handle.flush()

                    job = session.get(BatchJob, job_id)
                    if job is not None:
                        job.processed_questions = index
                    if index % self.settings.batch_progress_commit_every == 0:
                        session.commit()

            job = session.get(BatchJob, job_id)
            if job is None:
                raise BatchJobError("The batch job no longer exists.")
            job.status = BatchStatus.COMPLETED
            job.processed_questions = len(questions)
            job.result_path = results_path.relative_to(self.settings.data_dir).as_posix()
            job.updated_at = utcnow()
            session.commit()
            logger.info("Batch job %s completed (%d questions)", job.id, len(questions))

        except Exception as exc:
            logger.exception("Batch job %s failed", job_id)
            session.rollback()
            try:
                job = session.get(BatchJob, job_id)
                if job is not None:
                    job.status = BatchStatus.FAILED
                    job.error_message = (
                        str(exc)[:500] if isinstance(exc, BatchJobError) else
                        "Batch processing failed. Check the server logs for details."
                    )
                    session.commit()
            except Exception:  # pragma: no cover
                session.rollback()
                logger.exception("Could not persist failed batch status.")
        finally:
            session.close()

    # -- read helpers --------------------------------------------------------
    def get_job(self, session: Session, job_id: str) -> BatchJob:
        job = BatchRepository(session).get(job_id)
        if job is None:
            raise NotFoundError("Batch job not found.")
        return job

    def list_jobs(self, session: Session, limit: int = 50) -> list[BatchJob]:
        return BatchRepository(session).list(limit=limit)

    def result_path(self, job: BatchJob) -> Path:
        if not job.result_path:
            raise NotFoundError("This job has no result file yet.")
        path = resolve_stored_path(job.result_path, self.settings)
        if not path.exists():
            raise NotFoundError("The result file is no longer available.")
        return path

    def recover_interrupted_jobs(self) -> None:
        session = self.session_factory()
        try:
            from sqlalchemy import select

            jobs = list(
                session.scalars(
                    select(BatchJob).where(
                        BatchJob.status.in_([BatchStatus.PENDING, BatchStatus.PROCESSING])
                    )
                ).all()
            )
            for job in jobs:
                job.status = BatchStatus.FAILED
                job.error_message = "The job was interrupted by a server restart. Please upload it again."
            if jobs:
                session.commit()
                logger.warning("Marked %d interrupted batch job(s) as failed.", len(jobs))
        finally:
            session.close()

    @staticmethod
    def _read_questions(path: Path) -> list[str]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise BatchJobError("The CSV file is empty.")
                question_column = next(
                    (
                        name
                        for name in reader.fieldnames
                        if name and name.strip().lower() == "question"
                    ),
                    None,
                )
                if question_column is None:
                    raise BatchJobError("The CSV must contain a 'question' column.")
                return [
                    (row.get(question_column) or "").strip()
                    for row in reader
                    if (row.get(question_column) or "").strip()
                ]
        except BatchJobError:
            raise
        except (OSError, csv.Error) as exc:
            raise BatchJobError("The CSV file could not be read.") from exc

    @staticmethod
    def _row_for(question: str, answer: AnswerResult) -> dict:
        citations = answer.citations
        documents = sorted({citation["document_name"] for citation in citations if citation.get("document_name")})
        versions = sorted({citation["version_label"] for citation in citations if citation.get("version_label")})
        pages = sorted(
            {
                str(citation["page_number"])
                for citation in citations
                if citation.get("page_number") is not None
            }
        )
        sections = sorted({citation["section"] for citation in citations if citation.get("section")})

        return {
            "question": question,
            "answer": answer.answer,
            "status": answer.answer_status.value,
            "source_document": "; ".join(documents),
            "document_version": "; ".join(versions),
            "page_number": "; ".join(pages),
            "section": "; ".join(sections),
        }
