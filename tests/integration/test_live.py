"""Live integration tests against the HGNC REST API and bulk downloads.

Opt-in only: run with `pytest -m integration`. Skipped by the default test run.
"""

from __future__ import annotations

import pytest

from hgnc_link.api.client import HgncRestClient
from hgnc_link.config import HgncApiConfig

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def rest_client():  # type: ignore[no-untyped-def]
    client = HgncRestClient(HgncApiConfig(timeout=30))
    yield client
    await client.aclose()


async def test_live_fetch_braf(rest_client: HgncRestClient) -> None:
    doc = await rest_client.fetch_one("symbol", "BRAF")
    assert doc["hgnc_id"] == "HGNC:1097"
    assert doc["locus_type"] == "gene with protein product"
    assert "P15056" in doc["uniprot_ids"]


async def test_live_prev_symbol_resolution(rest_client: HgncRestClient) -> None:
    hits = await rest_client.search("CPAMD9", field="prev_symbol")
    assert hits and hits[0]["symbol"] == "A2ML1"
    assert hits[0]["hgnc_id"] == "HGNC:23336"


async def test_live_info_fields(rest_client: HgncRestClient) -> None:
    info = await rest_client.info()
    assert "symbol" in info["searchableFields"]
    assert "prev_symbol" in info["searchableFields"]
    assert info["numDoc"] > 40000


@pytest.mark.slow
async def test_live_bulk_build(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from hgnc_link.config import HgncDataConfig
    from hgnc_link.data.repository import HgncRepository
    from hgnc_link.ingest.builder import ensure_database
    from hgnc_link.services.hgnc_service import HgncService

    cfg = HgncDataConfig(data_dir=tmp_path)
    ensure_database(cfg)
    repo = HgncRepository(cfg.db_path)
    try:
        svc = HgncService(repo)
        assert svc.resolve("BRAF")["hgnc_id"] == "HGNC:1097"
        # MLL2 is an alias of KMT2D (the canonical sysndd/kidney test case).
        assert svc.resolve("MLL2")["approved_symbol"] in {"KMT2D", "KMT2A"}
        assert repo.get_meta()["gene_count"] > 40000
    finally:
        repo.close()
