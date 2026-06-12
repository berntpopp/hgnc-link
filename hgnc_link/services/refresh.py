"""Startup data bootstrap and the optional in-process refresh scheduler.

Cron is the recommended refresh mechanism (see docs/deployment.md), so the
in-process scheduler is OFF by default. ``bootstrap_data`` builds the index on
first start if absent — non-fatal: the server still starts and tools report
``data_unavailable`` until the build lands.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from typing import TYPE_CHECKING, Any

from hgnc_link.exceptions import DownloadError, HgncError
from hgnc_link.ingest.builder import ensure_database, rebuild
from hgnc_link.mcp.service_adapters import reset_hgnc_service

if TYPE_CHECKING:
    from hgnc_link.config import HgncDataConfig


async def bootstrap_data(config: HgncDataConfig, logger: Any) -> None:
    """Ensure the index exists, building it in a worker thread. Non-fatal."""
    try:
        path = await asyncio.to_thread(ensure_database, config)
        reset_hgnc_service()
        logger.info("hgnc_data_ready", db_path=str(path))
    except (HgncError, DownloadError, OSError) as exc:
        logger.warning("hgnc_data_bootstrap_failed", error=str(exc))


async def _refresh_loop(config: HgncDataConfig, logger: Any) -> None:
    interval = config.refresh_interval_hours * 3600
    while True:
        jitter = random.uniform(0, config.refresh_jitter_seconds)  # noqa: S311 - jitter only
        await asyncio.sleep(interval + jitter)
        try:
            result = await asyncio.to_thread(rebuild, config, force=False)
            if result.changed:
                reset_hgnc_service()
                logger.info("hgnc_data_refreshed", release=result.meta.release)
            else:
                logger.debug("hgnc_data_unchanged")
        except (HgncError, DownloadError, OSError) as exc:
            logger.warning("hgnc_data_refresh_failed", error=str(exc))


def start_refresh_scheduler(config: HgncDataConfig, logger: Any) -> asyncio.Task[None] | None:
    """Start the optional refresh loop; returns the task, or ``None`` if disabled."""
    if not config.refresh_enabled:
        return None
    logger.info("hgnc_refresh_scheduler_enabled", interval_hours=config.refresh_interval_hours)
    return asyncio.create_task(_refresh_loop(config, logger))


async def stop_refresh_scheduler(task: asyncio.Task[None] | None) -> None:
    """Cancel the refresh loop task if running."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
