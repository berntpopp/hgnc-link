"""Tests for response-mode shaping."""

from __future__ import annotations

from hgnc_link.services.shaping import (
    RESPONSE_MODES,
    shape_gene,
    shape_resolution,
    shape_summary,
)


def _gene() -> dict[str, object]:
    return {
        "hgnc_id": "HGNC:1",
        "symbol": "BRAF",
        "name": "B-Raf",
        "status": "Approved",
        "locus_type": "gene with protein product",
        "date_modified": "2023-01-20",
        "uuid": "abc",
        "alias_name": ["x"],
        "entrez_id": "673",
        "uniprot_ids": [],
    }


def test_response_modes_constant() -> None:
    assert RESPONSE_MODES == ("minimal", "compact", "standard", "full")


def test_full_is_identity_and_standard_is_a_strict_subset() -> None:
    """`full` is the complete record; `standard` genuinely returns less (issue #26 D3).

    They were byte-identical (a phantom tier); `standard` now omits the internal-only
    provenance fields so escalating standard->full pays for real extra detail.
    """
    g = _gene()
    assert shape_gene(g, "full") == g
    standard = shape_gene(g, "standard")
    assert standard != g
    assert "uuid" not in standard  # internal-only, full-only
    assert standard["date_modified"] == g["date_modified"]  # standard is still complete
    # full is a strict superset of standard.
    assert set(shape_gene(g, "full")) > set(standard)


def test_compact_drops_dates_and_empties() -> None:
    out = shape_gene(_gene(), "compact")
    assert "date_modified" not in out
    assert "uuid" not in out
    assert "uniprot_ids" not in out  # empty list dropped
    assert out["entrez_id"] == "673"


def test_minimal_keeps_only_core() -> None:
    out = shape_gene(_gene(), "minimal")
    assert set(out).issubset(
        {
            "hgnc_id",
            "symbol",
            "name",
            "status",
            "locus_group",
            "locus_type",
            "location",
            "match_type",
            "entrez_id",
            "ensembl_gene_id",
            "requested_query",
        }
    )
    assert "date_modified" not in out


def test_shape_resolution_modes() -> None:
    rec = {
        "query": "x",
        "hgnc_id": "HGNC:1",
        "approved_symbol": "S",
        "name": "n",
        "status": "Approved",
        "locus_type": "t",
        "location": "1p",
        "match_type": "current",
        "ambiguous": False,
    }
    assert set(shape_resolution(rec, "minimal")) == {
        "query",
        "hgnc_id",
        "approved_symbol",
        "match_type",
    }
    assert "name" in shape_resolution(rec, "compact")
    assert shape_resolution(rec, "full") == rec
    assert "candidates" not in shape_resolution(rec, "compact")


def test_shape_summary_modes() -> None:
    s = {
        "hgnc_id": "HGNC:1",
        "symbol": "BRAF",
        "name": "B-Raf",
        "symbol_type": "current",
        "status": None,
    }
    assert set(shape_summary(s, "minimal")) <= {"hgnc_id", "symbol", "match_type", "symbol_type"}
    assert "status" not in shape_summary(s, "compact")  # None dropped
    assert shape_summary(s, "full") == s
