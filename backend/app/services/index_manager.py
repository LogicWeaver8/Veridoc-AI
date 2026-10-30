"""Persistent hybrid index manager (vectors + BM25 + chunk metadata).

Single-process design: one IndexManager owns the index files and serialises all
mutations with a lock. It loads on startup and saves after every mutation, so a
restart does not require re-embedding every document.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.config import Settings
from app.core.logging import get_logger
from app.services.bm25 import BM25Index
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorIndex

logger = get_logger("index")


@dataclass
class ChunkRecord:
    """Everything needed to search and cite a chunk without a DB round trip."""

    chunk_id: str
    document_id: str
    version_id: str
    chunk_index: int
    text: str
    page_number: int | None
    section: str | None
    document_name: str = ""
    version_label: str = ""
    token_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkRecord":
        return cls(
            chunk_id=data["chunk_id"],
            document_id=data["document_id"],
            version_id=data["version_id"],
            chunk_index=int(data.get("chunk_index", 0)),
            text=data.get("text", ""),
            page_number=data.get("page_number"),
            section=data.get("section"),
            document_name=data.get("document_name", ""),
            version_label=data.get("version_label", ""),
            token_count=int(data.get("token_count", 0)),
        )


@dataclass
class IndexStats:
    chunk_count: int
    document_count: int
    backend: str
    embedding_provider: str
    embedding_model: str
    dimension: int
    updated_at: str | None = None
    needs_rebuild: bool = False
    size_bytes: int = 0
    extra: dict = field(default_factory=dict)


class IndexManager:
    def __init__(self, settings: Settings, embeddings: EmbeddingService) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self._lock = threading.RLock()
        self._vector = VectorIndex(embeddings.dimension, settings.vector_backend)
        self._records: list[ChunkRecord] = []
        self._by_id: dict[str, ChunkRecord] = {}
        self._bm25 = BM25Index()
        self._needs_rebuild = False
        self._updated_at: str | None = None
        self.load()

    # -- persistence --------------------------------------------------------
    @property
    def _vectors_path(self) -> Path:
        return self.settings.index_dir / "vectors.npy"

    @property
    def _meta_path(self) -> Path:
        return self.settings.index_dir / "meta.json"

    @property
    def _chunks_path(self) -> Path:
        return self.settings.index_dir / "chunks.jsonl"

    def load(self) -> None:
        with self._lock:
            if not self._meta_path.exists():
                logger.info("No existing index found; starting with an empty index.")
                return

            try:
                meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Index metadata is unreadable (%s); rebuild required.", exc)
                self._needs_rebuild = True
                return

            if meta.get("embedding_signature") != self.embeddings.signature:
                logger.warning(
                    "Index was built with a different embedding model (%s vs %s). "
                    "Rebuild the index from the admin endpoint.",
                    meta.get("embedding_signature"),
                    self.embeddings.signature,
                )
                self._needs_rebuild = True
                return

            try:
                ids = json.loads((self.settings.index_dir / "ids.json").read_text(encoding="utf-8"))
                records = [
                    ChunkRecord.from_dict(json.loads(line))
                    for line in self._chunks_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except (OSError, json.JSONDecodeError, KeyError) as exc:
                logger.warning("Index files are unreadable (%s); rebuild required.", exc)
                self._needs_rebuild = True
                return

            if len(ids) != len(records):
                logger.warning("Index ids/chunks mismatch; rebuild required.")
                self._needs_rebuild = True
                return

            if not self._vector.load(self.settings.index_dir):
                self._needs_rebuild = True
                return

            self._records = records
            self._by_id = {record.chunk_id: record for record in records}
            self._bm25.set_corpus([record.text for record in records])
            self._updated_at = meta.get("updated_at")
            logger.info("Loaded index with %d chunks.", len(records))

    def _save(self) -> None:
        self.settings.index_dir.mkdir(parents=True, exist_ok=True)
        self._vector.save(self.settings.index_dir)

        chunks_tmp = self._chunks_path.with_suffix(".jsonl.tmp")
        with chunks_tmp.open("w", encoding="utf-8") as handle:
            for record in self._records:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        os.replace(chunks_tmp, self._chunks_path)

        self._updated_at = datetime.now(UTC).isoformat()
        meta = {
            "embedding_signature": self.embeddings.signature,
            "embedding_provider": self.embeddings.provider_name,
            "embedding_model": self.embeddings.model_name,
            "dimension": self.embeddings.dimension,
            "backend": self._vector.backend,
            "chunk_count": len(self._records),
            "updated_at": self._updated_at,
        }
        meta_tmp = self._meta_path.with_suffix(".json.tmp")
        meta_tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        os.replace(meta_tmp, self._meta_path)

    def _refresh_bm25(self) -> None:
        self._bm25.set_corpus([record.text for record in self._records])

    # -- mutations ----------------------------------------------------------
    def add_chunks(self, chunks: list[ChunkRecord], vectors: np.ndarray | None = None) -> int:
        """Append new chunks with optional pre-computed vectors.

        Passing vectors lets the ingestion pipeline track embedding and indexing
        as separate stages. Existing chunk ids are ignored (idempotent).
        """
        with self._lock:
            new_chunks = [chunk for chunk in chunks if chunk.chunk_id not in self._by_id]
            if not new_chunks:
                return 0

            if vectors is None:
                vectors = self.embeddings.embed_texts([chunk.text for chunk in new_chunks])
            if len(vectors) != len(new_chunks):
                raise ValueError("Embedding count does not match chunk count.")
            self._vector.add([chunk.chunk_id for chunk in new_chunks], vectors)
            self._records.extend(new_chunks)
            for chunk in new_chunks:
                self._by_id[chunk.chunk_id] = chunk
            self._refresh_bm25()
            self._needs_rebuild = False
            self._save()
            return len(new_chunks)

    def rebuild(self, chunks: list[ChunkRecord]) -> int:
        """Replace the whole index, e.g. after changing the embedding model."""
        with self._lock:
            vectors = self.embeddings.embed_texts([chunk.text for chunk in chunks])
            self._vector.set_all([chunk.chunk_id for chunk in chunks], vectors)
            self._records = list(chunks)
            self._by_id = {chunk.chunk_id: chunk for chunk in chunks}
            self._refresh_bm25()
            self._needs_rebuild = False
            self._save()
            return len(chunks)

    def remove_document(self, document_id: str) -> int:
        with self._lock:
            removed_ids = {record.chunk_id for record in self._records if record.document_id == document_id}
            return self._remove_ids(removed_ids)

    def remove_version(self, version_id: str) -> int:
        with self._lock:
            removed_ids = {record.chunk_id for record in self._records if record.version_id == version_id}
            return self._remove_ids(removed_ids)

    def _remove_ids(self, removed_ids: set[str]) -> int:
        if not removed_ids:
            return 0
        self._vector.remove(removed_ids)
        self._records = [record for record in self._records if record.chunk_id not in removed_ids]
        for chunk_id in removed_ids:
            self._by_id.pop(chunk_id, None)
        self._refresh_bm25()
        self._save()
        return len(removed_ids)

    # -- search -------------------------------------------------------------
    def search_vector(
        self, query_vector: np.ndarray, top_k: int, allowed_version_ids: set[str] | None = None
    ) -> list[tuple[ChunkRecord, float]]:
        with self._lock:
            allowed_chunk_ids: set[str] | None = None
            if allowed_version_ids is not None:
                allowed_chunk_ids = {
                    record.chunk_id
                    for record in self._records
                    if record.version_id in allowed_version_ids
                }
                if not allowed_chunk_ids:
                    return []

            hits = self._vector.search(query_vector, top_k, allowed_chunk_ids)
            results: list[tuple[ChunkRecord, float]] = []
            for chunk_id, score in hits:
                record = self._by_id.get(chunk_id)
                if record is not None:
                    results.append((record, score))
            return results

    def search_bm25(
        self, query: str, top_k: int, allowed_version_ids: set[str] | None = None
    ) -> list[tuple[ChunkRecord, float]]:
        with self._lock:
            if not self._records:
                return []
            scores = self._bm25.scores(query)
            order = np.argsort(-scores)
            results: list[tuple[ChunkRecord, float]] = []
            for position in order:
                score = float(scores[position])
                if score <= 0:
                    break
                record = self._records[int(position)]
                if allowed_version_ids is not None and record.version_id not in allowed_version_ids:
                    continue
                results.append((record, score))
                if len(results) >= top_k:
                    break
            return results

    def get_record(self, chunk_id: str) -> ChunkRecord | None:
        with self._lock:
            return self._by_id.get(chunk_id)

    def all_records(self) -> list[ChunkRecord]:
        with self._lock:
            return list(self._records)

    # -- introspection ------------------------------------------------------
    def stats(self) -> IndexStats:
        with self._lock:
            size_bytes = 0
            if self.settings.index_dir.exists():
                size_bytes = sum(
                    path.stat().st_size
                    for path in self.settings.index_dir.glob("*")
                    if path.is_file()
                )
            return IndexStats(
                chunk_count=len(self._records),
                document_count=len({record.document_id for record in self._records}),
                backend=self._vector.backend,
                embedding_provider=self.embeddings.provider_name,
                embedding_model=self.embeddings.model_name,
                dimension=self.embeddings.dimension,
                updated_at=self._updated_at,
                needs_rebuild=self._needs_rebuild,
                size_bytes=size_bytes,
            )

    @property
    def needs_rebuild(self) -> bool:
        return self._needs_rebuild
