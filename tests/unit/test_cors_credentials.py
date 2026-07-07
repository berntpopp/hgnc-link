"""Security guard: the unauthenticated backend must not enable CORS credentials.

hgnc-link holds no cookies or session, so ``allow_credentials=True`` is
meaningless and a footgun if origins are ever widened to ``*``. This guard
pins credentials off, preserves the existing method list (GET/POST/OPTIONS —
several endpoints, incl. ``/health`` and root, are GET), and fails closed on
the wildcard-origin + credentials combination.

Research use only; not clinical decision support."""

from __future__ import annotations

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from hgnc_link.app import _validate_cors, create_app


def _cors_middleware(app) -> Middleware:  # type: ignore[no-untyped-def]
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return mw
    raise AssertionError("CORSMiddleware is not installed on the app")


def test_cors_credentials_disabled() -> None:
    mw = _cors_middleware(create_app())
    assert mw.kwargs["allow_credentials"] is False


def test_cors_preserves_method_list() -> None:
    mw = _cors_middleware(create_app())
    # Several endpoints are GET (/health, root); do not collapse to POST-only.
    assert mw.kwargs["allow_methods"] == ["GET", "POST", "OPTIONS"]


def test_health_ok() -> None:
    resp = TestClient(create_app()).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_wildcard_origin_with_credentials_rejected() -> None:
    with pytest.raises(ValueError, match="allow_credentials"):
        _validate_cors(["*"], allow_credentials=True)


def test_wildcard_origin_without_credentials_allowed() -> None:
    # Credentials off makes a wildcard origin safe; guard must not false-positive.
    _validate_cors(["*"], allow_credentials=False)
