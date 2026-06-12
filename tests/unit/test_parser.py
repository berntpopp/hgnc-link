"""Tests for the HGNC bulk-dump parser."""

from __future__ import annotations

from hgnc_link.ingest import parser


def test_normalize_doc_coerces_lists_and_scalars() -> None:
    doc = {
        "hgnc_id": "HGNC:1097",
        "symbol": "BRAF",
        "name": "B-Raf",
        "alias_symbol": ["BRAF1", "BRAF-1"],
        "prev_symbol": "OLD1|OLD2",
        "gene_group_id": [654, 1157],
        "entrez_id": "673",
    }
    rec = parser.normalize_doc(doc)
    assert rec["hgnc_id"] == "HGNC:1097"
    assert rec["symbol"] == "BRAF"
    assert rec["alias_symbol"] == ["BRAF1", "BRAF-1"]
    assert rec["prev_symbol"] == ["OLD1", "OLD2"]  # pipe-split
    assert rec["gene_group_id"] == ["654", "1157"]  # ints -> str
    assert rec["entrez_id"] == "673"
    assert rec["vega_id"] is None  # absent scalar -> None
    assert rec["uniprot_ids"] == []  # absent list -> []


def test_as_list_dedupes_and_strips() -> None:
    assert parser._as_list(" A | A | B ") == ["A", "B"]
    assert parser._as_list(None) == []
    assert parser._as_list(["x", "x", "y"]) == ["x", "y"]
    assert parser._as_list(673) == ["673"]


def test_load_complete_set_from_docs_list_and_filters_idless() -> None:
    docs = [{"hgnc_id": "HGNC:1", "symbol": "A"}, {"symbol": "no_id"}]
    out = parser.load_complete_set(docs)
    assert len(out) == 1 and out[0]["hgnc_id"] == "HGNC:1"


def test_symbol_lookup_rows_provenance() -> None:
    gene = parser.normalize_doc(
        {"hgnc_id": "HGNC:1", "symbol": "BRAF", "prev_symbol": ["OLD"], "alias_symbol": ["AL"]}
    )
    rows = parser.symbol_lookup_rows(gene)
    assert ("BRAF", "HGNC:1", "current") in rows
    assert ("OLD", "HGNC:1", "previous") in rows
    assert ("AL", "HGNC:1", "alias") in rows


def test_xref_rows_uppercases_and_explodes() -> None:
    gene = parser.normalize_doc(
        {"hgnc_id": "HGNC:1", "symbol": "X", "uniprot_ids": ["p1", "p2"], "entrez_id": "673"}
    )
    rows = parser.xref_rows(gene)
    assert ("uniprot_ids", "P1", "p1", "HGNC:1") in rows
    assert ("entrez_id", "673", "673", "HGNC:1") in rows


def test_group_rows_pairs_id_and_name() -> None:
    gene = parser.normalize_doc(
        {
            "hgnc_id": "HGNC:1",
            "symbol": "X",
            "gene_group": ["RAF family", "MAP kinases"],
            "gene_group_id": [1157, 654],
        }
    )
    rows = parser.group_rows(gene)
    assert ("1157", "RAF family", "HGNC:1") in rows
    assert ("654", "MAP kinases", "HGNC:1") in rows


def test_parse_withdrawn_entry_and_merged() -> None:
    text = (
        "HGNC_ID\tSTATUS\tWITHDRAWN_SYMBOL\tMERGED_INTO_REPORT(S)\n"
        "HGNC:1\tEntry Withdrawn\tA12M1\t\n"
        "HGNC:6\tMerged/Split\tA1S9T\tHGNC:12469|UBA1|Approved\n"
    )
    rows = parser.parse_withdrawn(text)
    assert rows[0]["status"] == "Entry Withdrawn"
    assert rows[0]["replaced_by"] == []
    assert rows[1]["replaced_by"] == [
        {"hgnc_id": "HGNC:12469", "symbol": "UBA1", "status": "Approved"}
    ]


def test_parse_withdrawn_multiple_targets() -> None:
    text = (
        "HGNC_ID\tSTATUS\tWITHDRAWN_SYMBOL\tMERGED\n"
        "HGNC:9\tMerged/Split\tX\tHGNC:1|A|Approved,HGNC:2|B|Approved\n"
    )
    rows = parser.parse_withdrawn(text)
    assert [r["symbol"] for r in rows[0]["replaced_by"]] == ["A", "B"]
