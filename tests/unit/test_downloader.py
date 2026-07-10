"""Tests for the conditional bulk downloader (respx-mocked httpx)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from hgnc_link.config import HgncDataConfig
from hgnc_link.exceptions import DownloadError
from hgnc_link.ingest import downloader

_URL = "https://example.test/hgnc_complete_set.json"


class _ChunkedBody(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield b"1234"
        yield b"56789"


def _config(tmp_path: Path) -> HgncDataConfig:
    return HgncDataConfig(data_dir=tmp_path, complete_set_url=_URL)


@respx.mock
def test_bulk_overflow_preserves_old_file(tmp_path: Path) -> None:
    cfg = HgncDataConfig(data_dir=tmp_path, complete_set_url=_URL, max_download_bytes=8)
    destination = tmp_path / "complete.json"
    destination.write_bytes(b"old")
    respx.get(_URL).mock(return_value=httpx.Response(200, content=b"123456789"))
    with pytest.raises(DownloadError, match="exceeded 8 bytes"):
        downloader.download_file(cfg, _URL, "complete.json")
    assert destination.read_bytes() == b"old"
    assert list(tmp_path.glob("*.download.tmp")) == []


@respx.mock
def test_bulk_chunked_overflow_is_authoritative(tmp_path: Path) -> None:
    cfg = HgncDataConfig(data_dir=tmp_path, complete_set_url=_URL, max_download_bytes=8)
    destination = tmp_path / "complete.json"
    destination.write_bytes(b"old")
    respx.get(_URL).mock(return_value=httpx.Response(200, stream=_ChunkedBody()))
    with pytest.raises(DownloadError, match="exceeded 8 bytes"):
        downloader.download_file(cfg, _URL, "complete.json")
    assert destination.read_bytes() == b"old"
    assert list(tmp_path.glob("*.download.tmp")) == []


@respx.mock
def test_bulk_redirect_is_not_followed(tmp_path: Path) -> None:
    target = respx.get("https://evil.example/complete.json").mock(
        return_value=httpx.Response(200, content=b"evil")
    )
    respx.get(_URL).mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "https://evil.example/complete.json"},
        )
    )
    destination = tmp_path / "complete.json"
    destination.write_bytes(b"old")
    with pytest.raises(DownloadError, match="302"):
        downloader.download_file(_config(tmp_path), _URL, "complete.json")
    assert target.called is False
    assert destination.read_bytes() == b"old"


@respx.mock
def test_download_writes_file_and_cache(tmp_path: Path) -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, content=b'{"response":{"docs":[]}}', headers={"ETag": '"v1"'}
        )
    )
    cfg = _config(tmp_path)
    result = downloader.download_file(cfg, _URL, "complete.json")
    assert result.path is not None and result.path.exists()
    assert result.etag == '"v1"'
    cache = (tmp_path / downloader.CACHE_FILENAME).read_text()
    assert "v1" in cache


@respx.mock
def test_conditional_304_reuses_local(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    route = respx.get(_URL)
    route.mock(return_value=httpx.Response(200, content=b"{}", headers={"ETag": '"v1"'}))
    downloader.download_file(cfg, _URL, "complete.json")
    route.mock(return_value=httpx.Response(304))
    result = downloader.download_file(cfg, _URL, "complete.json")
    assert result.not_modified is True
    assert result.path is not None  # local copy reused


@respx.mock
def test_force_ignores_cache(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    respx.get(_URL).mock(return_value=httpx.Response(200, content=b"{}", headers={"ETag": '"v2"'}))
    downloader.download_file(cfg, _URL, "complete.json", force=True)
    request = respx.calls.last.request
    assert "if-none-match" not in {k.lower() for k in request.headers}


@respx.mock
def test_http_error_maps_to_download_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(DownloadError):
        downloader.download_file(_config(tmp_path), _URL, "complete.json")


@respx.mock
def test_download_bulk_returns_both(tmp_path: Path) -> None:
    cfg = HgncDataConfig(
        data_dir=tmp_path,
        complete_set_url=_URL,
        withdrawn_url="https://example.test/withdrawn.txt",
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, content=b"{}", headers={"ETag": '"c"'}))
    respx.get("https://example.test/withdrawn.txt").mock(
        return_value=httpx.Response(200, content=b"HGNC_ID\n", headers={"ETag": '"w"'})
    )
    bulk = downloader.download_bulk(cfg)
    assert bulk.changed is True
    assert bulk.complete_set.path and bulk.withdrawn.path
