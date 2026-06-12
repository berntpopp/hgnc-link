"""Async HTTP client for the live HGNC REST API (rest.genenames.org).

Used only as a fallback when the local SQLite index is unavailable (e.g. before
the first build completes) and as the target of integration tests. HGNC defaults
to XML, so we always request ``Accept: application/json``. HGNC asks clients to
stay under 10 requests/second; a concurrency cap plus jittered backoff keeps us
well within that.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

from hgnc_link.exceptions import (
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
)

if TYPE_CHECKING:
    from hgnc_link.config import HgncApiConfig

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 8.0


class HgncRestClient:
    """Minimal async client over the HGNC REST ``info``/``fetch``/``search`` API."""

    def __init__(
        self,
        config: HgncApiConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Build a client; an injected ``client`` is used as-is (for tests)."""
        self._config = config
        self._semaphore = asyncio.Semaphore(max(1, config.max_concurrency))
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout),
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": config.user_agent,
            },
        )

    async def _request(self, path: str) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                async with self._semaphore:
                    response = await self._client.get(path)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = ServiceUnavailableError(f"HGNC REST request failed: {exc}")
            else:
                if response.status_code in (403, 429):
                    last_exc = RateLimitError("HGNC REST rate limit hit (HTTP 403/429).")
                elif response.status_code in _RETRYABLE_STATUS:
                    last_exc = ServiceUnavailableError(
                        f"HGNC REST returned {response.status_code}."
                    )
                elif response.status_code >= 400:
                    raise ServiceUnavailableError(
                        f"HGNC REST returned {response.status_code} for {path}."
                    )
                else:
                    return response.json()  # type: ignore[no-any-return]
            if attempt < self._config.max_retries:
                delay = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
                await asyncio.sleep(random.uniform(0, delay))  # noqa: S311 - jitter only
        assert last_exc is not None
        raise last_exc

    async def info(self) -> dict[str, Any]:
        """Return service metadata (searchable/stored fields, lastModified)."""
        return await self._request("/info")

    async def fetch(self, field: str, value: str) -> list[dict[str, Any]]:
        """Return full records matching ``field == value`` exactly."""
        data = await self._request(f"/fetch/{field}/{quote(value, safe='')}")
        return list(data.get("response", {}).get("docs", []))

    async def search(self, value: str, field: str | None = None) -> list[dict[str, Any]]:
        """Return lightweight search hits (hgnc_id, symbol, score)."""
        path = (
            f"/search/{field}/{quote(value, safe='')}"
            if field
            else f"/search/{quote(value, safe='')}"
        )
        data = await self._request(path)
        return list(data.get("response", {}).get("docs", []))

    async def fetch_one(self, field: str, value: str) -> dict[str, Any]:
        """Return the single record for ``field == value`` or raise ``NotFoundError``."""
        docs = await self.fetch(field, value)
        if not docs:
            raise NotFoundError(f"No HGNC record for {field}={value}.")
        return docs[0]

    async def aclose(self) -> None:
        """Close the underlying client if we own it."""
        if self._owns_client:
            await self._client.aclose()
