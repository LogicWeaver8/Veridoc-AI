"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import batch_routes, chat_routes, document_routes, system_routes, version_routes
from app.config import BACKEND_DIR, Settings, load_settings
from app.container import build_container
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger

logger = get_logger("main")


class SPAStaticFiles(StaticFiles):
    """Serve index.html for client-side routes, never for API paths.

    The SPA is mounted at "/", so it would otherwise answer unknown API routes
    with index.html instead of a structured 404.
    """

    def __init__(self, *, directory: str, api_prefixes: tuple[str, ...] = ()) -> None:
        super().__init__(directory=directory, html=True)
        self._reserved = tuple(prefix.strip("/") for prefix in api_prefixes)

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        # StaticFiles normalises the path with the OS separator; compare POSIX style.
        normalized = path.replace("\\", "/")
        if any(
            normalized == prefix or normalized.startswith(f"{prefix}/")
            for prefix in self._reserved
        ):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "not_found",
                        "message": "The requested API endpoint does not exist.",
                        "details": {},
                    }
                },
            )
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "loc": ".".join(str(part) for part in error.get("loc", [])),
                "msg": error.get("msg", "Invalid value"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "The request contains invalid data.",
                    "details": {"errors": errors},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "not_found" if exc.status_code == 404 else "http_error",
                    "message": message,
                    "details": {},
                }
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                    "details": {},
                }
            },
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        container.ingestion.recover_interrupted_documents()
        container.batch.recover_interrupted_jobs()
        stats = container.index.stats()
        logger.info(
            "Starting %s | env=%s | llm=%s | embeddings=%s (%d dims) | "
            "vector_backend=%s | indexed_chunks=%d",
            settings.app_name,
            settings.environment,
            container.generation.provider_name,
            container.embeddings.provider_name,
            container.embeddings.dimension,
            stats.backend,
            stats.chunk_count,
        )
        yield
        logger.info("Shutting down %s.", settings.app_name)
        container.engine.dispose()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=(
            "Enterprise Knowledge Assistant with evidence-grounded RAG, citations, "
            "document version intelligence and CSV batch processing."
        ),
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(system_routes.router)
    app.include_router(document_routes.router, prefix=settings.api_prefix)
    app.include_router(version_routes.router, prefix=settings.api_prefix)
    app.include_router(chat_routes.router, prefix=settings.api_prefix)
    app.include_router(batch_routes.router, prefix=settings.api_prefix)

    frontend_dist = BACKEND_DIR.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount(
            "/",
            SPAStaticFiles(
                directory=str(frontend_dist),
                api_prefixes=(settings.api_prefix, "health", "docs", "openapi.json", "redoc"),
            ),
            name="frontend",
        )
    else:

        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {
                "app": settings.app_name,
                "status": "ok",
                "docs": "/docs",
                "health": "/health",
            }

    return app


app = create_app()
