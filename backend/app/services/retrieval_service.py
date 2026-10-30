"""Hybrid retrieval: FAISS/NumPy vector search + BM25 fused with RRF.

Optional CrossEncoder reranking is applied when enabled and installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.core.logging import get_logger
from app.services.embedding_service import EmbeddingService
from app.services.index_manager import ChunkRecord, IndexManager

logger = get_logger("retrieval")


@dataclass
class RetrievedChunk:
    record: ChunkRecord
    vector_score: float | None = None
    bm25_score: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None
    extra: dict = field(default_factory=dict)


class RetrievalService:
    def __init__(
        self, settings: Settings, embeddings: EmbeddingService, index: IndexManager
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.index = index
        self._reranker = None
        self._reranker_failed = False

    def retrieve(
        self,
        question: str,
        allowed_version_ids: set[str] | None = None,
        final_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Run vector + keyword search and fuse results with Reciprocal Rank Fusion."""
        if not question.strip():
            return []

        candidate_k = self.settings.retrieval_candidates
        query_vector = self.embeddings.embed_query(question)

        vector_hits = self.index.search_vector(query_vector, candidate_k, allowed_version_ids)
        bm25_hits = self.index.search_bm25(question, candidate_k, allowed_version_ids)

        fused: dict[str, RetrievedChunk] = {}

        def add_hits(hits: list[tuple[ChunkRecord, float]], source: str) -> None:
            for rank, (record, score) in enumerate(hits):
                entry = fused.get(record.chunk_id)
                if entry is None:
                    entry = RetrievedChunk(record=record)
                    fused[record.chunk_id] = entry
                entry.fused_score += 1.0 / (self.settings.rrf_k + rank + 1)
                if source == "vector":
                    entry.vector_score = score
                else:
                    entry.bm25_score = score

        add_hits(vector_hits, "vector")
        add_hits(bm25_hits, "bm25")

        results = sorted(fused.values(), key=lambda item: item.fused_score, reverse=True)
        results = results[:candidate_k]

        if self.settings.reranker_enabled and results:
            results = self._rerank(question, results)

        limit = final_k or self.settings.final_evidence_chunks
        return results[:limit]

    # -- optional cross-encoder reranking -----------------------------------
    def _rerank(self, question: str, results: list[RetrievedChunk]) -> list[RetrievedChunk]:
        reranker = self._get_reranker()
        if reranker is None:
            return results
        try:
            pairs = [(question, item.record.text) for item in results]
            scores = reranker.predict(pairs)
            for item, score in zip(results, scores):
                item.rerank_score = float(score)
            return sorted(results, key=lambda item: item.rerank_score or 0.0, reverse=True)
        except Exception as exc:  # pragma: no cover - model/runtime failure
            logger.warning("Reranking failed and was skipped: %s", exc)
            return results

    def _get_reranker(self):  # type: ignore[no-untyped-def]
        if self._reranker is not None or self._reranker_failed:
            return self._reranker
        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading reranker %s ...", self.settings.reranker_model)
            self._reranker = CrossEncoder(self.settings.reranker_model)
        except Exception as exc:
            self._reranker_failed = True
            logger.warning(
                "Reranker is enabled but unavailable (%s). Continuing without reranking.", exc
            )
            self._reranker = None
        return self._reranker
