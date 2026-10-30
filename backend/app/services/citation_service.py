"""Citation construction.

Citations are generated exclusively from retrieved chunk metadata. The LLM
never supplies document names, page numbers or sections.
"""

from __future__ import annotations

import re

from app.services.retrieval_service import RetrievedChunk
from app.utils.text import detect_heading, term_coverage

MAX_CITATIONS = 4
MAX_EXCERPT_CHARS = 500
MIN_CHUNK_COVERAGE = 0.2


def _excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit]
    last_space = truncated.rfind(" ")
    if last_space > 100:
        truncated = truncated[:last_space]
    return truncated + "…"


def filter_relevant_chunks(
    question: str, chunks: list[RetrievedChunk], min_coverage: float = MIN_CHUNK_COVERAGE
) -> list[RetrievedChunk]:
    """Drop retrieved chunks that share almost no terms with the question.

    Retrieval always returns neighbours; this keeps answer text and citations
    focused on passages that actually talk about the question's subject.
    """
    if not chunks:
        return []
    coverages = [term_coverage(question, chunk.record.text) for chunk in chunks]
    top = max(coverages)
    threshold = max(min_coverage, top * 0.7)
    relevant = [chunk for chunk, coverage in zip(chunks, coverages) if coverage >= threshold]
    return relevant or chunks[:1]


def _best_section(text: str, fallback: str | None, question: str | None) -> str | None:
    """Pick the sub-section of a chunk that best matches the question.

    A chunk may span several sections; the citation should name the section
    that actually contains the answer rather than the document title.
    """
    if not question:
        return fallback

    sections: list[tuple[str | None, str]] = []
    current_heading = fallback
    current_blocks: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        heading = detect_heading(block)
        if heading:
            if current_blocks:
                sections.append((current_heading, "\n".join(current_blocks)))
            current_heading = heading
            current_blocks = [block]
        else:
            current_blocks.append(block)
    if current_blocks:
        sections.append((current_heading, "\n".join(current_blocks)))

    if len(sections) <= 1:
        return fallback

    best_heading, best_text = max(sections, key=lambda item: term_coverage(question, item[1]))
    if best_heading and term_coverage(question, best_text) >= MIN_CHUNK_COVERAGE:
        return best_heading
    return fallback


def build_citations(
    chunks: list[RetrievedChunk], limit: int = MAX_CITATIONS, question: str | None = None
) -> list[dict]:
    """Build de-duplicated citation objects, ordered by retrieval rank."""
    citations: list[dict] = []
    seen_keys: set[tuple] = set()

    for chunk in chunks:
        record = chunk.record
        section = _best_section(record.text, record.section, question)
        key = (record.document_id, record.version_id, record.page_number, section)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        citations.append(
            {
                "chunk_id": record.chunk_id,
                "document_id": record.document_id,
                "document_name": record.document_name,
                "version_id": record.version_id,
                "version_label": record.version_label,
                "page_number": record.page_number,
                "section": section,
                "excerpt": _excerpt(record.text),
                # RRF fused scores are tiny rank constants (~1/60); report a
                # similarity-style value that is meaningful to clients instead.
                "relevance": round(
                    chunk.rerank_score
                    if chunk.rerank_score is not None
                    else chunk.vector_score
                    if chunk.vector_score is not None
                    else chunk.fused_score,
                    4,
                ),
            }
        )
        if len(citations) >= limit:
            break

    return citations


def build_evidence_metadata(chunks: list[RetrievedChunk]) -> list[dict]:
    """Compact retrieval evidence for the API response (debugging/transparency)."""
    return [
        {
            "chunk_id": chunk.record.chunk_id,
            "document_id": chunk.record.document_id,
            "document_name": chunk.record.document_name,
            "version_id": chunk.record.version_id,
            "version_label": chunk.record.version_label,
            "page_number": chunk.record.page_number,
            "section": chunk.record.section,
            "vector_score": round(chunk.vector_score, 4) if chunk.vector_score is not None else None,
            "bm25_score": round(chunk.bm25_score, 4) if chunk.bm25_score is not None else None,
            "fused_score": round(chunk.fused_score, 6),
        }
        for chunk in chunks
    ]
