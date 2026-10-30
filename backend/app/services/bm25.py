"""BM25 keyword retrieval.

Implemented locally so the application has no extra dependency. BM25 matters
for policy numbers, employee IDs, exact phrases and legal terminology that
dense embeddings often miss.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np

from app.utils.text import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_lengths: np.ndarray = np.zeros(0, dtype=np.float32)
        self._average_length: float = 0.0
        self._doc_count: int = 0

    def set_corpus(self, documents: list[str]) -> None:
        """(Re)build the index. Rebuilding is cheap for a few thousand chunks."""
        self._doc_count = len(documents)
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths = np.zeros(len(documents), dtype=np.float32)

        for doc_index, text in enumerate(documents):
            tokens = tokenize(text)
            lengths[doc_index] = len(tokens)
            for term, frequency in Counter(tokens).items():
                postings[term].append((doc_index, frequency))

        self._postings = dict(postings)
        self._doc_lengths = lengths
        self._average_length = float(lengths.mean()) if len(lengths) else 0.0

    def scores(self, query: str) -> np.ndarray:
        scores = np.zeros(self._doc_count, dtype=np.float32)
        if self._doc_count == 0 or self._average_length == 0:
            return scores

        query_terms = [term for term in tokenize(query) if term in self._postings]
        for term in query_terms:
            posting = self._postings[term]
            document_frequency = len(posting)
            idf = math.log(1 + (self._doc_count - document_frequency + 0.5) / (document_frequency + 0.5))
            for doc_index, frequency in posting:
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * self._doc_lengths[doc_index] / self._average_length
                )
                scores[doc_index] += idf * (frequency * (self.k1 + 1)) / denominator
        return scores

    @property
    def document_count(self) -> int:
        return self._doc_count
