"""Embedding generation.

Two providers are supported:

* ``sentence-transformers`` - real neural embeddings. Downloads a model, so it
  is only used when explicitly configured.
* ``hashing`` - deterministic, dependency-free lexical vectors. This is the
  default so the application runs offline without downloading anything.

Both providers return L2-normalised float32 vectors, so cosine similarity is a
dot product.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter

import numpy as np

from app.config import Settings
from app.core.logging import get_logger
from app.utils.text import tokenize

logger = get_logger("embeddings")


class HashingEmbedder:
    """Deterministic hashing vectoriser (a hashed bag-of-words with bigrams).

    It is not a neural model. It is clearly labelled as a development fallback
    so nobody mistakes it for semantic embeddings. BM25 runs alongside it, so
    keyword-heavy enterprise questions still retrieve well.
    """

    name = "hashing-dev"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = tokenize(text)
            if not tokens:
                continue
            counts = Counter(tokens)
            for token, count in counts.items():
                self._accumulate(vectors[row], token, weight=1.0 + math.log(count))
            # Bigrams add a small amount of phrase awareness.
            for first, second in zip(tokens, tokens[1:]):
                self._accumulate(vectors[row], f"{first}_{second}", weight=0.5)

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vectors / norms).astype(np.float32)

    def _accumulate(self, vector: np.ndarray, feature: str, weight: float) -> None:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dimension
        sign = 1.0 if (value >> 63) & 1 else -1.0
        vector[index] += sign * weight


class SentenceTransformerEmbedder:
    """Wraps sentence-transformers; imported lazily to keep startup fast."""

    def __init__(self, model_name: str, batch_size: int) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.name = "sentence-transformers"
        self.batch_size = batch_size
        logger.info("Loading embedding model %s ...", model_name)
        self.model = SentenceTransformer(model_name)
        self.dimension = int(self.model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.batch_size = settings.embedding_batch_size
        requested = settings.embedding_provider.strip().lower().replace("_", "-")

        self._engine: HashingEmbedder | SentenceTransformerEmbedder
        if requested in {"sentence-transformers", "sentence-transformers", "st"}:
            try:
                self._engine = SentenceTransformerEmbedder(
                    settings.embedding_model, settings.embedding_batch_size
                )
            except Exception as exc:
                logger.warning(
                    "sentence-transformers unavailable (%s). Falling back to the "
                    "hashing-dev embedder. Install requirements-ai.txt to use neural embeddings.",
                    exc,
                )
                self._engine = HashingEmbedder(settings.embedding_dim)
        else:
            self._engine = HashingEmbedder(settings.embedding_dim)

        self.dimension = self._engine.dimension

    @property
    def provider_name(self) -> str:
        return self._engine.name

    @property
    def model_name(self) -> str:
        return getattr(self._engine, "model_name", "builtin-hashing-v1")

    @property
    def signature(self) -> str:
        """Identifies the vector space; indexes from another signature are invalid."""
        return f"{self.provider_name}:{self.model_name}:{self.dimension}"

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        batches: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batches.append(self._engine.embed(texts[start : start + self.batch_size]))
        return np.vstack(batches).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]
