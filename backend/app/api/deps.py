"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.container import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_session(request: Request) -> Iterator[Session]:
    container: AppContainer = request.app.state.container
    session = container.session_factory()
    try:
        yield session
    finally:
        session.close()
