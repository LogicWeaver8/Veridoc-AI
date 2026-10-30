"""Persistent vector index.

FAISS (IndexFlatIP) is used when installed; otherwise a NumPy cosine index is
used. The canonical on-disk representation is ``vectors.npy`` + ``ids.json`` so
either backend can be rebuilt after a restart.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.config import Settings
from app.core.logging import get_logger

logger = get_logger("vector_store")

try:  # FAISS is optional
    import faiss  # type: ignore

    FAISS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the environment
    faiss = None  # type: ignore
    FAISS_AVAILABLE = False


class VectorIndex:
    def __init__(self, dimension: int, backend: str = "auto") -> None:
        self.dimension = dimension
        requested = backend.lower()
        self.backend = "faiss" if requested == "faiss" else "numpy"
        if requested in {"auto", "faiss"}:
            if FAISS_AVAILABLE:
                self.backend = "faiss"
            elif requested == "faiss":
                logger.warning("FAISS was requested but is not installed; using NumPy.")
                self.backend = "numpy"

        self._ids: list[str] = []
        self._matrix: np.ndarray = np.zeros((0, dimension), dtype=np.float32)
        self._index = self._build_faiss_index()

    # -- state management ---------------------------------------------------
    def _build_faiss_index(self):  # type: ignore[no-untyped-def]
        if self.backend != "faiss":
            return None
        index = faiss.IndexFlatIP(self.dimension)
        if len(self._matrix):
            index.add(self._matrix)
        return index

    def set_all(self, ids: list[str], matrix: np.ndarray) -> None:
        self._ids = list(ids)
        self._matrix = np.ascontiguousarray(matrix.astype(np.float32))
        self._index = self._build_faiss_index()

    def add(self, ids: list[str], matrix: np.ndarray) -> None:
        if not ids:
            return
        matrix = np.ascontiguousarray(matrix.astype(np.float32))
        self._ids.extend(ids)
        self._matrix = np.vstack([self._matrix, matrix]) if len(self._matrix) else matrix
        if self._index is not None:
            self._index.add(matrix)

    def remove(self, ids_to_remove: set[str]) -> None:
        if not ids_to_remove:
            return
        keep = [index for index, chunk_id in enumerate(self._ids) if chunk_id not in ids_to_remove]
        self._ids = [self._ids[index] for index in keep]
        self._matrix = self._matrix[keep] if keep else np.zeros((0, self.dimension), dtype=np.float32)
        self._index = self._build_faiss_index()  # flat index needs a rebuild after deletion

    # -- search -------------------------------------------------------------
    def search(
        self, query_vector: np.ndarray, top_k: int, allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        if not self._ids or top_k <= 0:
            return []

        query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query.shape[0] != self.dimension:
            raise ValueError("Query embedding dimension does not match the index.")

        if allowed_ids is not None:
            positions = [index for index, chunk_id in enumerate(self._ids) if chunk_id in allowed_ids]
            if not positions:
                return []
            scores = self._matrix[positions] @ query
            order = np.argsort(-scores)[:top_k]
            return [(self._ids[positions[i]], float(scores[i])) for i in order]

        if self._index is not None:
            distances, positions = self._index.search(query.reshape(1, -1), min(top_k, len(self._ids)))
            results = []
            for score, position in zip(distances[0], positions[0]):
                if position < 0:
                    continue
                results.append((self._ids[int(position)], float(score)))
            return results

        scores = self._matrix @ query
        order = np.argsort(-scores)[:top_k]
        return [(self._ids[i], float(scores[i])) for i in order]

    # -- persistence --------------------------------------------------------
    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self._matrix)
        (directory / "ids.json").write_text(
            __import__("json").dumps(self._ids), encoding="utf-8"
        )

    def load(self, directory: Path) -> bool:
        vectors_path = directory / "vectors.npy"
        ids_path = directory / "ids.json"
        if not vectors_path.exists() or not ids_path.exists():
            return False

        import json

        matrix = np.load(vectors_path).astype(np.float32)
        ids = json.loads(ids_path.read_text(encoding="utf-8"))
        if matrix.ndim != 2 or matrix.shape[1] != self.dimension or len(ids) != matrix.shape[0]:
            logger.warning("Ignoring vector index with incompatible dimensions.")
            return False

        self.set_all(ids, matrix)
        return True

    @property
    def size(self) -> int:
        return len(self._ids)
