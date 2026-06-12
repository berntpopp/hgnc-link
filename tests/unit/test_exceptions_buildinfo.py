"""Tests for the exception hierarchy and build info."""

from __future__ import annotations

from hgnc_link.buildinfo import build_info
from hgnc_link.exceptions import HgncError, NotFoundError, WithdrawnEntryError


def test_hgnc_error_str_with_status() -> None:
    assert str(HgncError("boom", status_code=503)) == "[503] boom"
    assert str(HgncError("boom")) == "boom"


def test_withdrawn_is_notfound_with_message() -> None:
    exc = WithdrawnEntryError(
        "A1S9T", status="Merged/Split", replaced_by=[{"hgnc_id": "HGNC:12469", "symbol": "UBA1"}]
    )
    assert isinstance(exc, NotFoundError)
    assert "UBA1" in str(exc)
    assert exc.withdrawn_status == "Merged/Split"


def test_withdrawn_no_replacement_message() -> None:
    exc = WithdrawnEntryError("A12M1", status="Entry Withdrawn")
    assert "no replacement" in str(exc)


def test_build_info_keys(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HGNC_LINK_GIT_SHA", "deadbeef")
    info = build_info()
    assert info["git_sha"] == "deadbeef"
    assert "version" in info
