"""Tests for logging, refresh/bootstrap, and service-adapter wiring."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from hgnc_link.config import HgncApiConfig, HgncDataConfig
from hgnc_link.logging_config import configure_logging
from hgnc_link.services.hgnc_service import HgncService


def test_configure_logging_returns_logger() -> None:
    logger = configure_logging()
    assert logger is not None
    logger.info("test event", k="v")


async def test_bootstrap_data_non_fatal_on_missing(tmp_path: Path) -> None:
    from hgnc_link.services.refresh import bootstrap_data

    cfg = HgncDataConfig(data_dir=tmp_path, auto_bootstrap=False)
    # No network, auto_bootstrap off -> ensure_database raises, but bootstrap swallows it.
    await bootstrap_data(cfg, configure_logging())  # must not raise


async def test_bootstrap_data_success(built_db: Path) -> None:
    from hgnc_link.mcp.service_adapters import reset_hgnc_service
    from hgnc_link.services.refresh import bootstrap_data

    cfg = HgncDataConfig(data_dir=built_db.parent, db_filename=built_db.name)
    await bootstrap_data(cfg, configure_logging())
    reset_hgnc_service()


def test_refresh_scheduler_disabled_returns_none() -> None:
    from hgnc_link.services.refresh import start_refresh_scheduler

    cfg = HgncDataConfig(refresh_enabled=False)
    assert start_refresh_scheduler(cfg, logging.getLogger("test")) is None


async def test_stop_refresh_scheduler_handles_none() -> None:
    from hgnc_link.services.refresh import stop_refresh_scheduler

    await stop_refresh_scheduler(None)


def test_service_adapter_singleton_and_reset(
    monkeypatch: pytest.MonkeyPatch, built_db: Path
) -> None:
    import hgnc_link.mcp.service_adapters as adapters

    fake = HgncService(None)
    adapters.set_hgnc_service(fake)
    assert adapters.get_hgnc_service() is fake
    adapters.reset_hgnc_service()
    # Point settings at the built DB so a fresh service opens the repo.
    monkeypatch.setattr(adapters.settings.data, "data_dir", built_db.parent)
    monkeypatch.setattr(adapters.settings.data, "db_filename", built_db.name)
    monkeypatch.setattr(adapters.settings.api, "enable_live_fallback", False)
    svc = adapters.get_hgnc_service()
    assert isinstance(svc, HgncService)
    assert svc.get_diagnostics()["data_available"] is True
    adapters.set_hgnc_service(None)


def test_api_config_user_agent() -> None:
    cfg = HgncApiConfig(contact_email="x@y.org")
    assert "mailto:x@y.org" in cfg.user_agent
    assert HgncApiConfig(base_url="https://rest.test/").base_url == "https://rest.test"


def test_data_config_db_path(tmp_path: Path) -> None:
    cfg = HgncDataConfig(data_dir=tmp_path, db_filename="x.sqlite")
    assert cfg.db_path == tmp_path / "x.sqlite"
