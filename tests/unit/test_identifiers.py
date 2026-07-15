"""Tests for HGNC identifier normalization."""

from __future__ import annotations

import pytest

from hgnc_link.identifiers import (
    infer_xref_source,
    looks_like_hgnc_id,
    looks_like_symbol,
    normalize_hgnc_id,
)


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


def test_infer_xref_source() -> None:
    assert infer_xref_source("ENSG00000157764") == "ensembl_gene_id"
    assert infer_xref_source("ENST00000646891") is None  # transcript: reverse lookup can't match
    assert infer_xref_source("P15056") == "uniprot"
    assert infer_xref_source("NM_004333") == "refseq"
    assert infer_xref_source("BRAF") is None
    assert infer_xref_source("P53") is None  # too short to be a UniProt accession


def test_source_enum_is_never_narrower_than_runtime() -> None:
    """The advertised `source` enum equals the full runtime-accepted set (review #4)."""
    from hgnc_link.constants import XREF_LOOKUP_SOURCE_ENUM, XREF_SOURCE_ALIASES

    assert set(XREF_LOOKUP_SOURCE_ENUM) == set(XREF_SOURCE_ALIASES)
    # the advertised examples and canonical/synonym labels are all in the enum
    for advertised in ("refseq", "mane_select", "ensembl_gene_id", "ncbi", "ensembl"):
        assert advertised in XREF_LOOKUP_SOURCE_ENUM
