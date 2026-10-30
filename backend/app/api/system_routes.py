"""Health, statistics, index administration and settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_container, get_session
from app.schemas.system import (
    AppSettingsOut,
    HealthOut,
    IndexStatusOut,
    RebuildResponse,
    StatsOut,
)
from app.services.extraction_service import ocr_available
from app.services.vector_store import FAISS_AVAILABLE

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    container = get_container(request)
    index_stats = container.index.stats()
    return HealthOut(
        status="ok",
        app=container.settings.app_name,
        version=__version__,
        llm_provider=container.generation.provider_name,
        embedding_provider=container.embeddings.provider_name,
        index_chunks=index_stats.chunk_count,
    )


@router.get("/api/stats", response_model=StatsOut)
def stats(request: Request, session: Session = Depends(get_session)) -> StatsOut:
    container = get_container(request)
    return StatsOut(**container.stats.dashboard(session))


@router.get("/api/index/status", response_model=IndexStatusOut)
def index_status(request: Request) -> IndexStatusOut:
    container = get_container(request)
    stats = container.index.stats()
    return IndexStatusOut(
        chunk_count=stats.chunk_count,
        document_count=stats.document_count,
        backend=stats.backend,
        embedding_provider=stats.embedding_provider,
        embedding_model=stats.embedding_model,
        dimension=stats.dimension,
        updated_at=stats.updated_at,
        needs_rebuild=stats.needs_rebuild,
        size_bytes=stats.size_bytes,
        faiss_available=FAISS_AVAILABLE,
        ocr_available=ocr_available(),
    )


@router.post("/api/index/rebuild", response_model=RebuildResponse)
def rebuild_index(request: Request, session: Session = Depends(get_session)) -> RebuildResponse:
    container = get_container(request)
    count = container.ingestion.rebuild_index(session)
    return RebuildResponse(
        message=f"Index rebuilt from {count} stored chunks.",
        chunk_count=count,
        backend=container.index.stats().backend,
    )


@router.get("/api/system/settings", response_model=AppSettingsOut)
def app_settings(request: Request) -> AppSettingsOut:
    container = get_container(request)
    settings = container.settings
    stats = container.index.stats()
    return AppSettingsOut(
        app_name=settings.app_name,
        environment=settings.environment,
        llm_provider=container.generation.provider_name,
        llm_display_name=container.generation.display_name,
        llm_model=container.generation.model_name,
        llm_is_mock=container.generation.is_mock,
        llm_temperature=settings.llm_temperature,
        llm_timeout_seconds=settings.llm_timeout_seconds,
        ollama_base_url=settings.ollama_base_url,
        embedding_provider=stats.embedding_provider,
        embedding_model=stats.embedding_model,
        embedding_dimension=stats.dimension,
        vector_backend=stats.backend,
        chunk_size_tokens=settings.chunk_size_tokens,
        chunk_overlap_tokens=settings.chunk_overlap_tokens,
        embedding_batch_size=settings.embedding_batch_size,
        retrieval_candidates=settings.retrieval_candidates,
        final_evidence_chunks=settings.final_evidence_chunks,
        reranker_enabled=settings.reranker_enabled,
        max_upload_mb=settings.max_upload_mb,
        max_batch_questions=settings.max_batch_questions,
        ocr_enabled=settings.ocr_enabled,
        ocr_available=ocr_available(),
        faiss_available=FAISS_AVAILABLE,
    )
