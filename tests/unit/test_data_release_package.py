"""Reproducible data-release build + packaging (genefoundry-router#63 option A)."""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

import hgnc_link.ingest.cli as cli_mod
from hgnc_link.config import HgncDataConfig
from hgnc_link.ingest.builder import build_database
from hgnc_link.ingest.downloader import BulkDownload, DownloadResult
from hgnc_link.ingest.release import package_release

ROOT = Path(__file__).resolve().parents[2]
GENES = ROOT / "tests" / "fixtures_genes.json"
WITHDRAWN = ROOT / "tests" / "fixtures_withdrawn.txt"
AUTHORIZATION = ROOT / "release" / "data-authorization.json"
LAST_MODIFIED = "Tue, 15 Sep 2026 13:48:06 GMT"


def _build(directory: Path) -> Path:
    config = HgncDataConfig(data_dir=directory, db_filename="hgnc.sqlite")
    build_database(
        config,
        complete_set_path=GENES,
        withdrawn_path=WITHDRAWN,
        etag='"e"',
        last_modified=LAST_MODIFIED,
        build_utc="2026-09-15T13:48:06+00:00",
    )
    return config.db_path


def test_pinned_build_is_byte_reproducible_and_not_wal(tmp_path: Path) -> None:
    first = _build(tmp_path / "a")
    second = _build(tmp_path / "b")

    assert first.read_bytes() == second.read_bytes()
    connection = sqlite3.connect(f"file:{first}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert connection.execute("SELECT build_utc, build_duration_s FROM meta").fetchone() == (
            "2026-09-15T13:48:06+00:00",
            None,
        )
    finally:
        connection.close()


def test_package_writes_verifiable_content_addressed_assets(tmp_path: Path) -> None:
    database = _build(tmp_path / "build")
    output = tmp_path / "release"

    manifest = package_release(
        database,
        complete_set=GENES,
        withdrawn=WITHDRAWN,
        authorization=AUTHORIZATION,
        output=output,
        revision="0" * 40,
    )

    expanded = hashlib.sha256(database.read_bytes()).hexdigest()
    assert manifest["release_tag"] == f"data-hgnc-{expanded[:16]}"
    assert sorted(p.name for p in output.iterdir()) == [
        "SHA256SUMS",
        "data-authorization.json",
        "hgnc.sqlite.gz",
        "manifest.json",
    ]
    bundle = output / "hgnc.sqlite.gz"
    assert gzip.decompress(bundle.read_bytes()) == database.read_bytes()
    assert manifest["compressed_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert (
        manifest["source"]["complete_set_sha256"] == hashlib.sha256(GENES.read_bytes()).hexdigest()
    )
    assert (
        manifest["source"]["withdrawn_sha256"] == hashlib.sha256(WITHDRAWN.read_bytes()).hexdigest()
    )
    assert manifest["license"]["spdx"] == "CC0-1.0"
    assert json.loads((output / "manifest.json").read_text()) == manifest
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    again = package_release(
        database,
        complete_set=GENES,
        withdrawn=WITHDRAWN,
        authorization=AUTHORIZATION,
        output=tmp_path / "release2",
        revision="0" * 40,
    )
    assert again["compressed_sha256"] == manifest["compressed_sha256"]


def _fake_download(directory: Path, last_modified: str | None) -> BulkDownload:
    complete = directory / "hgnc_complete_set.json"
    withdrawn = directory / "withdrawn.txt"
    complete.write_bytes(GENES.read_bytes())
    withdrawn.write_bytes(WITHDRAWN.read_bytes())
    return BulkDownload(
        complete_set=DownloadResult(path=complete, etag="E", last_modified=last_modified),
        withdrawn=DownloadResult(path=withdrawn, etag="W", last_modified=last_modified),
    )


def test_cli_reproducible_build_then_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = HgncDataConfig(data_dir=tmp_path / "data", db_filename="hgnc.sqlite")
    config.data_dir.mkdir()
    download = _fake_download(config.data_dir, LAST_MODIFIED)
    monkeypatch.setattr(cli_mod, "get_data_config", lambda: config)
    monkeypatch.setattr(cli_mod, "download_bulk", lambda cfg, *, force=False: download)
    runner = CliRunner()

    assert runner.invoke(cli_mod.app, ["build", "--reproducible"]).exit_code == 0
    result = runner.invoke(
        cli_mod.app, ["package", "--output", str(tmp_path / "out"), "--revision", "a" * 40]
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["transformation"]["build_utc"] == "2026-09-15T13:48:06+00:00"


def test_cli_reproducible_build_requires_last_modified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = HgncDataConfig(data_dir=tmp_path, db_filename="hgnc.sqlite")
    download = _fake_download(tmp_path, None)
    monkeypatch.setattr(cli_mod, "get_data_config", lambda: config)
    monkeypatch.setattr(cli_mod, "download_bulk", lambda cfg, *, force=False: download)

    result = CliRunner().invoke(cli_mod.app, ["build", "--reproducible"])

    assert result.exit_code == 1
    assert not config.db_path.exists()
