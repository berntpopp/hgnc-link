"""Tests for the SQLite builder lifecycle (ensure/rebuild/read_meta)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx
import pytest
import respx

from hgnc_link.config import HgncDataConfig
from hgnc_link.exceptions import DataUnavailableError
from hgnc_link.ingest import builder
from hgnc_link.ingest.lock import build_lock

_CS = "https://example.test/hgnc_complete_set.json"
_WD = "https://example.test/withdrawn.txt"
_NCBI = "https://example.test/Homo_sapiens.gene_info.gz"
_DOC = {
    "response": {
        "docs": [
            {"hgnc_id": "HGNC:1097", "symbol": "BRAF", "name": "B-Raf", "alias_symbol": ["BRAF1"]}
        ]
    }
}


def _config(tmp_path: Path) -> HgncDataConfig:
    return HgncDataConfig(
        data_dir=tmp_path, complete_set_url=_CS, withdrawn_url=_WD, ncbi_gene_info_url=_NCBI
    )


def _mock_ncbi() -> None:
    respx.get(_NCBI).mock(
        return_value=httpx.Response(
            200,
            content=gzip.compress(b"9606\t673\tBRAF\t-\tRAFB1\n"),
            headers={"Last-Modified": "Wed, 18 Nov 2026 11:15:48 GMT"},
        )
    )


def test_read_meta_roundtrip(built_db: Path) -> None:
    meta = builder.read_meta(built_db)
    assert meta is not None
    assert meta.gene_count == 9
    assert builder.read_meta(Path("/nope/x.sqlite")) is None


def test_ensure_database_no_bootstrap_raises(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.auto_bootstrap = False
    with pytest.raises(DataUnavailableError):
        builder.ensure_database(cfg)


@respx.mock
def test_ensure_database_bootstraps(tmp_path: Path) -> None:
    respx.get(_CS).mock(
        return_value=httpx.Response(200, content=json.dumps(_DOC).encode(), headers={"ETag": '"c"'})
    )
    respx.get(_WD).mock(
        return_value=httpx.Response(200, content=b"HGNC_ID\tSTATUS\tWITHDRAWN_SYMBOL\tM\n")
    )
    _mock_ncbi()
    cfg = _config(tmp_path)
    path = builder.ensure_database(cfg)
    assert path.exists()
    meta = builder.read_meta(path)
    assert meta is not None and meta.gene_count == 1
    assert meta.source_ncbi_gene_info_url == _NCBI
    assert meta.source_ncbi_gene_info_last_modified == "Wed, 18 Nov 2026 11:15:48 GMT"


@respx.mock
def test_rebuild_not_modified(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    respx.get(_CS).mock(
        return_value=httpx.Response(200, content=json.dumps(_DOC).encode(), headers={"ETag": '"c"'})
    )
    respx.get(_WD).mock(
        return_value=httpx.Response(200, content=b"HGNC_ID\n", headers={"ETag": '"w"'})
    )
    _mock_ncbi()
    builder.ensure_database(cfg)
    respx.get(_CS).mock(return_value=httpx.Response(304))
    respx.get(_WD).mock(return_value=httpx.Response(304))
    result = builder.rebuild(cfg, force=False)
    assert result.not_modified is True
    assert result.changed is False


def test_build_lock_is_reentrant_after_release(tmp_path: Path) -> None:
    with build_lock(tmp_path, timeout=5):
        pass
    with build_lock(tmp_path, timeout=5) as held:
        assert held is True
