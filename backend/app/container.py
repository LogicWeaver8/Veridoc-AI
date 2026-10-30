"""Application container: wires settings, database and services together.

Services receive their dependencies explicitly; routes read the container from
``request.app.state.container``. This keeps tests able to build an isolated app
with a temporary data directory.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.session import create_engine_for_settings, create_session_factory, init_database
from app.services.batch_service import BatchService
from app.services.chat_service import ChatService
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionService
from app.services.generation_service import GenerationService
from app.services.index_manager import IndexManager
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.services.stats_service import StatsService
from app.services.validation_service import ValidationService
from app.services.version_service import VersionService


@dataclass
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    embeddings: EmbeddingService
    index: IndexManager
    extraction: ExtractionService
    ingestion: IngestionService
    retrieval: RetrievalService
    validation: ValidationService
    generation: GenerationService
    versions: VersionService
    chat: ChatService
    batch: BatchService
    stats: StatsService


def build_container(settings: Settings) -> AppContainer:
    settings.ensure_directories()
    engine = create_engine_for_settings(settings)
    init_database(engine)
    session_factory = create_session_factory(engine)

    embeddings = EmbeddingService(settings)
    index = IndexManager(settings, embeddings)
    extraction = ExtractionService(settings)
    versions = VersionService()

    ingestion = IngestionService(
        settings, extraction, embeddings, index, versions, session_factory
    )
    retrieval = RetrievalService(settings, embeddings, index)
    validation = ValidationService(settings)
    generation = GenerationService(settings)
    chat = ChatService(settings, retrieval, validation, generation, versions)
    batch = BatchService(settings, chat, session_factory)
    stats = StatsService(settings, index)

    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        embeddings=embeddings,
        index=index,
        extraction=extraction,
        ingestion=ingestion,
        retrieval=retrieval,
        validation=validation,
        generation=generation,
        versions=versions,
        chat=chat,
        batch=batch,
        stats=stats,
    )
