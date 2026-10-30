"""Domain errors mapped to safe, consistent HTTP responses.

Internal stack traces are logged but never returned to the client.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for expected application errors."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class DuplicateDocumentError(AppError):
    status_code = 409
    code = "duplicate_document"

    def __init__(self, message: str, *, existing_document_id: str | None = None) -> None:
        super().__init__(message, details={"existing_document_id": existing_document_id})


class ProviderError(AppError):
    """Raised when the configured LLM provider cannot produce an answer."""

    status_code = 502
    code = "llm_provider_error"


class IndexStateError(AppError):
    status_code = 503
    code = "index_unavailable"


class BatchJobError(AppError):
    status_code = 400
    code = "batch_job_error"
