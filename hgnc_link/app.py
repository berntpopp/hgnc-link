"""FastAPI host for hgnc-link (thin: health + service info + data bootstrap)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hgnc_link import __version__
from hgnc_link.buildinfo import build_info
from hgnc_link.config import settings
from hgnc_link.logging_config import configure_logging
from hgnc_link.mcp.service_adapters import aclose_hgnc_service
from hgnc_link.services.refresh import (
    bootstrap_data,
    start_refresh_scheduler,
    stop_refresh_scheduler,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# Backends are unauthenticated by design (edge auth lives at the router), so CORS
# credentials are meaningless. Keep them off; wiring them back on with a wildcard
# origin is a footgun the startup guard below rejects.
_CORS_ALLOW_CREDENTIALS = False


def _validate_cors(origins: list[str], allow_credentials: bool) -> None:
    """Fail closed on the unsafe wildcard-origin + credentials CORS combination.

    An unauthenticated backend holds no cookies/session, so credentials are
    pointless; combined with a ``*`` origin they are also forbidden by the CORS
    spec. Reject that combination at startup rather than silently shipping a
    permissive policy.
    """
    if allow_credentials and "*" in origins:
        raise ValueError(
            "CORS misconfiguration: allow_credentials=True with a wildcard '*' "
            "origin. Backends are unauthenticated by design; disable credentials "
            "or pin explicit origins."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Bootstrap the HGNC index and (optionally) start the refresh scheduler."""
    logger = configure_logging()
    logger.info("hgnc-link starting", host=settings.host, port=settings.port)
    await bootstrap_data(settings.data, logger)
    refresh_task = start_refresh_scheduler(settings.data, logger)
    try:
        yield
    finally:
        await stop_refresh_scheduler(refresh_task)
        await aclose_hgnc_service()
        logger.info("hgnc-link shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="hgnc-link",
        description="MCP/API server grounding gene nomenclature in the HGNC dataset.",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    _validate_cors(settings.cors_origins, _CORS_ALLOW_CREDENTIALS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=_CORS_ALLOW_CREDENTIALS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Liveness probe (reports build provenance for deploy checks)."""
        return {
            "status": "ok",
            "service": "hgnc-link",
            "transport": "streamable-http-stateless",
            **build_info(),
        }

    @app.get("/")
    async def root() -> dict[str, Any]:
        """Service information."""
        return {
            "name": "hgnc-link",
            "version": __version__,
            "data_source": "HGNC bulk dumps (genenames.org) -> local SQLite index",
            "mcp_endpoint": settings.mcp_path,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
