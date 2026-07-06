"""Lazily-constructed singleton HgncService for MCP tools.

The repository is opened against the already-built SQLite index (the server
lifespan bootstraps it in a background thread; see ``hgnc_link.app``). If the
index is not present yet, the service is built without a repository — tools then
return ``data_unavailable`` (or use the optional live REST fallback).
"""

from __future__ import annotations

import logging

from hgnc_link.api.client import HgncRestClient
from hgnc_link.config import settings
from hgnc_link.data.repository import HgncRepository
from hgnc_link.exceptions import DataUnavailableError
from hgnc_link.services.hgnc_service import HgncService

logger = logging.getLogger(__name__)

_service: HgncService | None = None


def _build_service() -> HgncService:
    repo: HgncRepository | None = None
    db_path = settings.data.db_path
    if db_path.exists():
        try:
            repo = HgncRepository(db_path)
        except DataUnavailableError as exc:  # pragma: no cover - corrupt db
            logger.warning("hgnc_repo_open_failed path=%s err=%s", db_path, exc)
    rest = HgncRestClient(settings.api) if settings.api.enable_live_fallback else None
    return HgncService(repo, rest_client=rest)


def get_hgnc_service() -> HgncService:
    """Return a process-wide :class:`HgncService` (built on first use)."""
    global _service
    if _service is None:
        _service = _build_service()
    return _service


def reset_hgnc_service() -> None:
    """Drop the cached service so the next call re-opens the (refreshed) index."""
    global _service
    _service = None


async def aclose_hgnc_service() -> None:
    """Close the singleton's optional REST client on shutdown and drop it.

    The live fallback is off by default (unwired dead code), but if it is opted
    in the constructed httpx client must be closed on lifespan shutdown so its
    connection pool is not leaked. Safe to call when no service was built.
    """
    global _service
    if _service is not None:
        await _service.aclose()
        _service = None


def set_hgnc_service(service: HgncService | None) -> None:
    """Override the singleton (used by tests)."""
    global _service
    _service = service
