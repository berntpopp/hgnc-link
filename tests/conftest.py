"""Shared fixtures: a fixture-backed HGNC index, repository, service, and facade."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hgnc_link.config import HgncDataConfig
from hgnc_link.data.repository import HgncRepository
from hgnc_link.ingest.builder import build_database
from hgnc_link.services.hgnc_service import HgncService

FIXTURES_DIR = Path(__file__).resolve().parent
GENES_FIXTURE = FIXTURES_DIR / "fixtures_genes.json"
WITHDRAWN_FIXTURE = FIXTURES_DIR / "fixtures_withdrawn.txt"


def _structured(result: Any) -> dict[str, Any]:
    """Read structured_content defensively (with TextContent JSON fallback)."""
    sc = result.structured_content
    if isinstance(sc, dict):
        return sc
    return json.loads(result.content[0].text)


@pytest.fixture
def structured() -> Any:
    """Expose the structured-content reader to tests."""
    return _structured


@pytest.fixture(scope="session")
def built_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a small HGNC index from the real fixtures once per session."""
    data_dir = tmp_path_factory.mktemp("hgnc_data")
    config = HgncDataConfig(data_dir=data_dir, db_filename="hgnc.sqlite")
    build_database(
        config,
        complete_set_path=GENES_FIXTURE,
        withdrawn_path=WITHDRAWN_FIXTURE,
        etag='"fixture-etag"',
        last_modified="Fri, 12 Jun 2026 13:01:53 GMT",
    )
    return config.db_path


@pytest.fixture
def data_config(built_db: Path) -> HgncDataConfig:
    """A data config pointing at the built fixture database."""
    return HgncDataConfig(data_dir=built_db.parent, db_filename=built_db.name)


@pytest.fixture
def repo(built_db: Path) -> Any:
    """An open read-only repository over the fixture database."""
    repository = HgncRepository(built_db)
    yield repository
    repository.close()


@pytest.fixture
def service(repo: HgncRepository) -> HgncService:
    """A service backed by the fixture repository (no live fallback)."""
    return HgncService(repo)


@pytest.fixture
def facade(service: HgncService) -> Any:
    """A FastMCP facade with the fixture service injected; cleans up after."""
    from hgnc_link.mcp.facade import create_hgnc_mcp
    from hgnc_link.mcp.service_adapters import set_hgnc_service

    set_hgnc_service(service)
    mcp = create_hgnc_mcp()
    yield mcp
    set_hgnc_service(None)
