"""Unit tests for extraction, chunking, embeddings and BM25."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import pymupdf

from app.config import Settings
from app.core.errors import ValidationFailedError
from app.services.bm25 import BM25Index
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionService
from app.utils.text import TextChunker, detect_heading


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(data_dir=tmp_path / "data", embedding_provider="hashing", ocr_enabled=False)
    values.update(overrides)
    return Settings(**values)


def test_text_extraction_reads_pages(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("Annual leave is 18 days.\n\nSick leave is 12 days.", encoding="utf-8")

    result = ExtractionService(make_settings(tmp_path)).extract(path, "txt")

    assert len(result.pages) == 1
    assert result.pages[0].page_number == 1
    assert "18 days" in result.pages[0].text


def test_markdown_extraction(tmp_path: Path) -> None:
    path = tmp_path / "handbook.md"
    path.write_text("# Leave\n\nEmployees get 18 annual leave days.", encoding="utf-8")
    result = ExtractionService(make_settings(tmp_path)).extract(path, "markdown")
    assert "18 annual leave days" in result.pages[0].text


def test_pdf_extraction_preserves_page_numbers(tmp_path: Path) -> None:
    pdf = pymupdf.open()
    first = pdf.new_page()
    first.insert_text((72, 72), "Section 1: Annual leave is 18 days per year.", fontsize=12)
    second = pdf.new_page()
    second.insert_text((72, 72), "Section 2: Sick leave is 12 days per year.", fontsize=12)
    path = tmp_path / "handbook.pdf"
    path.write_bytes(pdf.tobytes())
    pdf.close()

    result = ExtractionService(make_settings(tmp_path)).extract(path, "pdf")

    assert len(result.pages) == 2
    assert result.pages[0].page_number == 1
    assert result.pages[1].page_number == 2
    assert "Sick leave" in result.pages[1].text


def test_pdf_without_text_is_rejected_when_ocr_is_unavailable(tmp_path: Path) -> None:
    pdf = pymupdf.open()
    pdf.new_page()
    path = tmp_path / "blank.pdf"
    path.write_bytes(pdf.tobytes())
    pdf.close()

    with pytest.raises(ValidationFailedError):
        ExtractionService(make_settings(tmp_path)).extract(path, "pdf")


def test_empty_text_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")
    with pytest.raises(ValidationFailedError):
        ExtractionService(make_settings(tmp_path)).extract(path, "txt")


def test_binary_file_disguised_as_text_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "binary.txt"
    path.write_bytes(bytes([0, 1, 2, 3, 4, 5]) * 400)
    with pytest.raises(ValidationFailedError):
        ExtractionService(make_settings(tmp_path)).extract(path, "txt")


def test_heading_detection() -> None:
    assert detect_heading("SECTION 4: PER DIEM AND MEALS") == "PER DIEM AND MEALS"
    assert detect_heading("# Annual Leave") == "Annual Leave"
    assert detect_heading("This is a normal paragraph with several words.") is None
    assert detect_heading("LEAVE POLICY") == "LEAVE POLICY"


def test_chunker_respects_pages_sections_and_overlap() -> None:
    page_one = (
        "SECTION 2: ANNUAL LEAVE\n\n"
        + "Employees receive 18 days of annual paid leave each calendar year. " * 12
    )
    page_two = (
        "SECTION 3: SICK LEAVE\n\n"
        + "Employees receive 12 days of paid sick leave each year. " * 12
    )
    chunker = TextChunker(chunk_size_tokens=120, overlap_tokens=25)

    chunks = chunker.chunk_pages([(1, page_one), (2, page_two)])

    assert len(chunks) >= 4
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert any(chunk.section == "ANNUAL LEAVE" for chunk in chunks)
    assert any(chunk.section == "SICK LEAVE" for chunk in chunks)
    assert all(chunk.token_count <= 240 for chunk in chunks)
    assert all(chunk.text.strip() for chunk in chunks)


def test_hashing_embeddings_are_deterministic_and_normalised(tmp_path: Path) -> None:
    service = EmbeddingService(make_settings(tmp_path))
    first = service.embed_texts(["annual leave policy", "gym membership benefit"])
    second = service.embed_texts(["annual leave policy", "gym membership benefit"])

    assert first.shape == (2, 384)
    assert np.allclose(first, second)
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0, atol=1e-5)
    related = float(first[0] @ service.embed_query("annual leave days"))
    unrelated = float(first[1] @ service.embed_query("annual leave days"))
    assert related > unrelated


def test_bm25_prefers_matching_document() -> None:
    index = BM25Index()
    index.set_corpus(
        [
            "employees receive 18 days of annual paid leave",
            "gym membership is not provided by the company",
        ]
    )
    scores = index.scores("annual leave")
    assert scores[0] > scores[1]
    assert scores[0] > 0
