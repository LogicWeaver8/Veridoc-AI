"""Safe file handling for uploads: validation, hashing and storage."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config import Settings
from app.core.errors import ValidationFailedError
from app.core.logging import get_logger

logger = get_logger("files")

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 ._\-()]+")
CHUNK_READ_SIZE = 1024 * 1024


@dataclass
class StoredFile:
    original_filename: str
    stored_filename: str
    absolute_path: Path
    relative_path: str
    size_bytes: int
    sha256: str
    extension: str


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_READ_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_original_name(filename: str | None) -> str:
    """Keep only a clean base filename; never trust the client's path."""
    raw = Path(filename or "").name
    raw = unicodedata.normalize("NFKD", raw)
    raw = _SAFE_NAME_RE.sub("_", raw).strip(" ._")
    if not raw:
        raw = "document"
    if len(raw) > 180:
        stem, suffix = Path(raw).stem, Path(raw).suffix
        raw = stem[: 180 - len(suffix)] + suffix
    return raw


def validate_extension(
    filename: str, settings: Settings, allowed_extensions: set[str] | None = None
) -> str:
    allowed_types = allowed_extensions or settings.allowed_extensions
    extension = Path(filename).suffix.lower()
    if extension not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        raise ValidationFailedError(
            f"Unsupported file type '{extension or 'unknown'}'. Allowed types: {allowed}."
        )
    return extension


def file_type_from_extension(extension: str) -> str:
    if extension == ".pdf":
        return "pdf"
    if extension in {".md", ".markdown"}:
        return "markdown"
    return "txt"


def _new_stored_name(extension: str) -> str:
    return f"{uuid.uuid4().hex}{extension}"


async def save_upload(
    upload: UploadFile,
    settings: Settings,
    allowed_extensions: set[str] | None = None,
    directory: Path | None = None,
) -> StoredFile:
    """Validate and persist an upload while enforcing the size limit.

    The file is streamed in chunks, so a malicious Content-Length header cannot
    bypass the maximum size check. A SHA-256 hash is computed on the fly.
    """
    original_name = safe_original_name(upload.filename)
    extension = validate_extension(original_name, settings, allowed_extensions)

    stored_name = _new_stored_name(extension)
    destination = (directory or settings.upload_dir) / stored_name
    destination.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0

    try:
        with destination.open("wb") as output:
            while True:
                block = await upload.read(CHUNK_READ_SIZE)
                if not block:
                    break
                size += len(block)
                if size > max_bytes:
                    raise ValidationFailedError(
                        f"File exceeds the {settings.max_upload_mb} MB upload limit."
                    )
                digest.update(block)
                output.write(block)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise ValidationFailedError("The uploaded file is empty.")

    return StoredFile(
        original_filename=original_name,
        stored_filename=stored_name,
        absolute_path=destination,
        relative_path=destination.relative_to(settings.data_dir).as_posix(),
        size_bytes=size,
        sha256=digest.hexdigest(),
        extension=extension,
    )


def resolve_stored_path(relative_path: str, settings: Settings) -> Path:
    """Resolve a relative storage path and reject path traversal attempts."""
    candidate = (settings.data_dir / relative_path).resolve()
    root = settings.data_dir.resolve()
    if not candidate.is_relative_to(root):
        raise ValidationFailedError("Invalid stored file path.")
    return candidate


def delete_stored_file(relative_path: str | None, settings: Settings) -> None:
    """Delete a file inside the data directory, ignoring missing files."""
    if not relative_path:
        return
    try:
        path = resolve_stored_path(relative_path, settings)
    except ValidationFailedError:
        logger.warning("Refusing to delete suspicious path: %s", relative_path)
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - filesystem edge case
        logger.warning("Could not delete %s: %s", path, exc)


def validate_csv_upload(filename: str) -> None:
    if Path(filename).suffix.lower() != ".csv":
        raise ValidationFailedError("Batch uploads must be CSV files (.csv).")
