"""Conditional download of the HGNC bulk dumps (complete set + withdrawn).

HGNC publishes the dumps on a public GCS bucket that honours ``ETag`` /
``Last-Modified``. We cache the last-seen validators per URL and issue
conditional ``GET`` requests, so a re-download only transfers a body when the
upstream data actually changed (a daily cron check is then almost always a cheap
``304``). The complete set is the primary trigger for a rebuild.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from hgnc_link.exceptions import DownloadError

if TYPE_CHECKING:
    from hgnc_link.config import HgncDataConfig

COMPLETE_SET_FILENAME = "hgnc_complete_set.json"
WITHDRAWN_FILENAME = "withdrawn.txt"
CACHE_FILENAME = "download_cache.json"
_CHUNK_SIZE = 1 << 16


@dataclass
class DownloadResult:
    """Outcome of a conditional download of one file."""

    path: Path | None = None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    content_length: int | None = None


@dataclass
class BulkDownload:
    """Outcome of downloading the complete set + withdrawn list together."""

    complete_set: DownloadResult
    withdrawn: DownloadResult

    @property
    def changed(self) -> bool:
        """True when either file transferred a fresh body this call."""
        return not self.complete_set.not_modified or not self.withdrawn.not_modified


def _cache_path(config: HgncDataConfig) -> Path:
    return config.data_dir / CACHE_FILENAME


def _read_cache(config: HgncDataConfig) -> dict[str, dict[str, str | None]]:
    cache_path = _cache_path(config)
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(
    config: HgncDataConfig, url: str, *, etag: str | None, last_modified: str | None
) -> None:
    cache_path = _cache_path(config)
    data = _read_cache(config)
    data[url] = {"etag": etag, "last_modified": last_modified}
    cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stream_to_file(
    response: httpx.Response,
    path: Path,
    *,
    max_bytes: int,
    max_seconds: float,
) -> None:
    content_length = _int_or_none(response.headers.get("Content-Length"))
    if content_length is not None and content_length > max_bytes:
        raise DownloadError(f"download Content-Length {content_length} exceeded {max_bytes} bytes")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".download.tmp")
    tmp_path = Path(tmp_name)
    written = 0
    started = time.monotonic()
    try:
        with os.fdopen(fd, "wb") as handle:
            for chunk in response.iter_bytes(_CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise DownloadError(f"download exceeded {max_bytes} bytes")
                if time.monotonic() - started > max_seconds:
                    raise DownloadError(f"download exceeded {max_seconds:g} seconds")
                handle.write(chunk)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def download_file(
    config: HgncDataConfig,
    url: str,
    filename: str,
    *,
    force: bool = False,
) -> DownloadResult:
    """Conditionally download ``url`` to ``data_dir/filename``.

    Sends ``If-None-Match`` / ``If-Modified-Since`` from the cache unless
    ``force``. A ``304`` reuses the existing local file without a body transfer.
    """
    config.data_dir.mkdir(parents=True, exist_ok=True)
    dest = config.data_dir / filename
    headers = {"User-Agent": config.user_agent}
    if not force:
        cached = _read_cache(config).get(url, {})
        if cached.get("etag"):
            headers["If-None-Match"] = str(cached["etag"])
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = str(cached["last_modified"])

    try:
        with (
            httpx.Client(follow_redirects=False, timeout=config.download_timeout) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            if response.status_code == httpx.codes.NOT_MODIFIED:
                return DownloadResult(
                    path=dest if dest.exists() else None,
                    etag=headers.get("If-None-Match"),
                    last_modified=headers.get("If-Modified-Since"),
                    not_modified=True,
                )
            response.raise_for_status()
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
            content_length = _int_or_none(response.headers.get("Content-Length"))
            _stream_to_file(
                response,
                dest,
                max_bytes=config.max_download_bytes,
                max_seconds=config.max_download_seconds,
            )
    except httpx.HTTPStatusError as exc:
        raise DownloadError(
            f"GET {url} failed: {exc.response.status_code}",
            status_code=exc.response.status_code,
        ) from exc
    except httpx.HTTPError as exc:
        raise DownloadError(f"GET {url} failed: {exc}") from exc

    _write_cache(config, url, etag=etag, last_modified=last_modified)
    return DownloadResult(
        path=dest,
        etag=etag,
        last_modified=last_modified,
        not_modified=False,
        content_length=content_length,
    )


def download_bulk(config: HgncDataConfig, *, force: bool = False) -> BulkDownload:
    """Download the complete set + withdrawn list (conditionally unless ``force``)."""
    complete = download_file(config, config.complete_set_url, COMPLETE_SET_FILENAME, force=force)
    withdrawn = download_file(config, config.withdrawn_url, WITHDRAWN_FILENAME, force=force)
    return BulkDownload(complete_set=complete, withdrawn=withdrawn)
