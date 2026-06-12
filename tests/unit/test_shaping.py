"""Tests for response-mode shaping."""

from __future__ import annotations

from hgnc_link.services.shaping import RESPONSE_MODES, shape_gene, shape_summary


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


def test_full_and_standard_are_identity() -> None:
    g = _gene()
    assert shape_gene(g, "full") == g
    assert shape_gene(g, "standard") == g


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
