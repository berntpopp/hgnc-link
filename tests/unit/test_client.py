"""Tests for the live HGNC REST client error mapping (respx-mocked)."""

from __future__ import annotations

import httpx
import pytest
import respx

from hgnc_link.api.client import HgncRestClient
from hgnc_link.config import HgncApiConfig
from hgnc_link.exceptions import NotFoundError, RateLimitError, ServiceUnavailableError

_BASE = "https://rest.test"


def _client() -> HgncRestClient:
    return HgncRestClient(HgncApiConfig(base_url=_BASE, max_retries=0))


@respx.mock
async def test_rest_redirect_is_not_followed() -> None:
    target = respx.get("https://evil.example/info").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{_BASE}/info").mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/info"})
    )
    client = _client()
    with pytest.raises(ServiceUnavailableError, match="302"):
        await client.info()
    assert target.called is False
    await client.aclose()


@respx.mock
async def test_injected_client_cannot_enable_redirects() -> None:
    target = respx.get("https://evil.example/info").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{_BASE}/info").mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/info"})
    )
    injected = httpx.AsyncClient(base_url=_BASE, follow_redirects=True)
    client = HgncRestClient(
        HgncApiConfig(base_url=_BASE, max_retries=0),
        client=injected,
    )
    try:
        with pytest.raises(ServiceUnavailableError, match="302"):
            await client.info()
        assert target.called is False
    finally:
        await injected.aclose()


@respx.mock
async def test_fetch_parses_docs() -> None:
    respx.get(f"{_BASE}/fetch/symbol/BRAF").mock(
        return_value=httpx.Response(200, json={"response": {"docs": [{"hgnc_id": "HGNC:1097"}]}})
    )
    client = _client()
    docs = await client.fetch("symbol", "BRAF")
    assert docs[0]["hgnc_id"] == "HGNC:1097"
    await client.aclose()


@respx.mock
async def test_fetch_one_raises_not_found_when_empty() -> None:
    respx.get(f"{_BASE}/fetch/symbol/NOPE").mock(
        return_value=httpx.Response(200, json={"response": {"docs": []}})
    )
    client = _client()
    with pytest.raises(NotFoundError):
        await client.fetch_one("symbol", "NOPE")
    await client.aclose()


@respx.mock
async def test_rate_limit_maps_to_rate_limit_error() -> None:
    respx.get(f"{_BASE}/info").mock(return_value=httpx.Response(429))
    client = _client()
    with pytest.raises(RateLimitError):
        await client.info()
    await client.aclose()


@respx.mock
async def test_server_error_maps_to_service_unavailable() -> None:
    respx.get(f"{_BASE}/info").mock(return_value=httpx.Response(503))
    client = _client()
    with pytest.raises(ServiceUnavailableError):
        await client.info()
    await client.aclose()


@respx.mock
async def test_search_builds_path() -> None:
    respx.get(f"{_BASE}/search/prev_symbol/CPAMD9").mock(
        return_value=httpx.Response(200, json={"response": {"docs": [{"symbol": "A2ML1"}]}})
    )
    client = _client()
    hits = await client.search("CPAMD9", field="prev_symbol")
    assert hits[0]["symbol"] == "A2ML1"
    await client.aclose()
