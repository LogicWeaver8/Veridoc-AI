"""Database engine and session management."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.base import Base  # noqa: F401  (import ensures models see the same base)


def create_engine_for_settings(settings: Settings) -> Engine:
    """Create an engine. SQLite gets sane defaults for a FastAPI app."""
    url = settings.resolved_database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_database(engine: Engine) -> None:
    """Create tables that do not exist yet.

    For a production deployment with schema changes, replace this with Alembic
    migrations. For a fresh development install, create_all is sufficient.
    """
    # Importing models registers them on Base.metadata.
    from app.models import batch_job, chat_message, conversation, document, document_chunk, document_version  # noqa: F401

    Base.metadata.create_all(bind=engine)
