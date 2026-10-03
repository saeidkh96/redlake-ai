from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.observability import RequestContextMiddleware, metrics_response
from app.db.session import Database
from app.storage import build_object_store

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(runtime_settings.debug)
        database = Database(runtime_settings.database_url)
        object_store = build_object_store(runtime_settings)
        app.state.settings = runtime_settings
        app.state.database = database
        app.state.object_store = object_store

        object_store.ensure_ready()
        if runtime_settings.auto_create_schema:
            database.create_schema()
        logger.info(
            "RedLake AI started",
            extra={
                "environment": runtime_settings.environment,
                "version": runtime_settings.app_version,
                "storage_backend": runtime_settings.storage_backend,
            },
        )
        try:
            yield
        finally:
            database.dispose()
            logger.info("RedLake AI stopped")

    app = FastAPI(
        title="RedLake AI",
        summary="Production-oriented intelligent data and AI platform",
        description=(
            "RedLake AI captures data with contracts, profiles and quality evidence before "
            "it enters the lakehouse. v0.1.0 implements the catalog and batch ingestion foundation."
        ),
        version=runtime_settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    if runtime_settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=runtime_settings.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled application error", extra={"path": request.url.path})
        detail = "Internal server error"
        if runtime_settings.debug:
            detail = str(error)
        return JSONResponse(status_code=500, content={"detail": detail})

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return metrics_response()

    app.include_router(api_router, prefix=runtime_settings.api_prefix)
    return app


app = create_app()
