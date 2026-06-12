"""Tests for HGNC identifier normalization."""

from __future__ import annotations

import pytest

from hgnc_link.identifiers import looks_like_hgnc_id, looks_like_symbol, normalize_hgnc_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HGNC:1100", "HGNC:1100"),
        ("hgnc:1100", "HGNC:1100"),
        ("1100", "HGNC:1100"),
        ("  HGNC:5  ", "HGNC:5"),
        ("BRAF", None),
        ("", None),
        ("HGNC:", None),
        ("HGNC:12a", None),
    ],
)
def test_normalize_hgnc_id(value: str, expected: str | None) -> None:
    assert normalize_hgnc_id(value) == expected


def test_looks_like_hgnc_id() -> None:
    assert looks_like_hgnc_id("HGNC:1") is True
    assert looks_like_hgnc_id("42") is True
    assert looks_like_hgnc_id("BRAF") is False


def test_looks_like_symbol() -> None:
    assert looks_like_symbol("BRAF") is True
    assert looks_like_symbol("MT-ND1") is True
    assert looks_like_symbol("HGNC:1") is False  # an id, not a symbol
    assert looks_like_symbol("") is False
    assert looks_like_symbol("has space") is False
