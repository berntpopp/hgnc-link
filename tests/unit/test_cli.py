"""Tests for the hgnc-link-data CLI (typer CliRunner + respx)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hgnc_link.config import HgncDataConfig
from hgnc_link.ingest import cli

_CS = "https://example.test/hgnc_complete_set.json"
_WD = "https://example.test/withdrawn.txt"
_DOC = {"response": {"docs": [{"hgnc_id": "HGNC:1097", "symbol": "BRAF", "name": "B-Raf"}]}}

runner = CliRunner()


@pytest.fixture
def patched_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HgncDataConfig:
    cfg = HgncDataConfig(data_dir=tmp_path, complete_set_url=_CS, withdrawn_url=_WD)
    monkeypatch.setattr(cli, "get_data_config", lambda: cfg)
    return cfg


def _mock_dumps() -> None:
    respx.get(_CS).mock(
        return_value=httpx.Response(200, content=json.dumps(_DOC).encode(), headers={"ETag": '"c"'})
    )
    respx.get(_WD).mock(
        return_value=httpx.Response(200, content=b"HGNC_ID\n", headers={"ETag": '"w"'})
    )


@respx.mock
def test_cli_build_then_status(patched_config: HgncDataConfig) -> None:
    _mock_dumps()
    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 0
    assert "Built HGNC database" in result.stdout
    status = runner.invoke(cli.app, ["status"])
    assert status.exit_code == 0
    assert "genes" in status.stdout


def test_cli_status_without_db(patched_config: HgncDataConfig) -> None:
    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 1
    assert "No HGNC database" in result.stdout


@respx.mock
def test_cli_refresh_not_modified(patched_config: HgncDataConfig) -> None:
    _mock_dumps()
    runner.invoke(cli.app, ["build"])
    respx.get(_CS).mock(return_value=httpx.Response(304))
    respx.get(_WD).mock(return_value=httpx.Response(304))
    result = runner.invoke(cli.app, ["refresh"])
    assert result.exit_code == 0
    assert "up to date" in result.stdout


@respx.mock
def test_cli_build_download_error(patched_config: HgncDataConfig) -> None:
    respx.get(_CS).mock(return_value=httpx.Response(500))
    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 1
    assert "download failed" in result.stdout
