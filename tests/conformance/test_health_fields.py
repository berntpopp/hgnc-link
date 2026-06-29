"""Unit test: /health must return {status, version, transport}."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hgnc_link.app import app


def test_health_returns_required_fields() -> None:
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok", f"missing status: {data}"
    assert "version" in data, f"missing version: {data}"
    assert data["transport"] == "streamable-http-stateless", f"missing/wrong transport: {data}"
