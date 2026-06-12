"""Tests for the read-only SQLite repository over the fixture index."""

from __future__ import annotations

import pytest

from hgnc_link.data.repository import HgncRepository
from hgnc_link.exceptions import DataUnavailableError


def test_get_meta(repo: HgncRepository) -> None:
    meta = repo.get_meta()
    assert meta["gene_count"] == 8
    assert meta["withdrawn_count"] == 3
    assert meta["schema_version"] == 1


def test_get_gene_and_by_symbol(repo: HgncRepository) -> None:
    gene = repo.get_gene("HGNC:1097")
    assert gene is not None and gene["symbol"] == "BRAF"
    assert gene["uniprot_ids"] == ["P15056"]  # JSON list decoded
    assert "symbol_upper" not in gene  # internal column dropped
    assert repo.get_gene_by_symbol("braf")["hgnc_id"] == "HGNC:1097"
    assert repo.get_gene("HGNC:999999") is None


def test_lookup_symbol_priority(repo: HgncRepository) -> None:
    pairs = repo.lookup_symbol("BRAF1")  # alias of BRAF
    assert pairs == [("HGNC:1097", "alias")]
    pairs = repo.lookup_symbol("BRAF")
    assert pairs[0] == ("HGNC:1097", "current")


def test_withdrawn_lookup(repo: HgncRepository) -> None:
    wd = repo.get_withdrawn("HGNC:6")
    assert wd is not None and wd["status"] == "Merged/Split"
    assert wd["replaced_by"][0]["symbol"] == "UBA1"
    by_sym = repo.find_withdrawn_by_symbol("a1s9t")
    assert by_sym and by_sym[0]["hgnc_id"] == "HGNC:6"


def test_search_fts_and_like_fallback(repo: HgncRepository) -> None:
    hits = repo.search("tumor", limit=10)
    assert any(h["symbol"] == "TP53" for h in hits)
    # Pathological FTS input should not raise (falls back gracefully).
    assert isinstance(repo.search("AND OR *", limit=5), list)
    assert repo.search("", limit=5) == [] or isinstance(repo.search("", limit=5), list)


def test_lookup_by_xref(repo: HgncRepository) -> None:
    assert repo.lookup_by_xref("ensembl_gene_id", "ensg00000157764") == ["HGNC:1097"]
    assert repo.lookup_by_xref("entrez_id", "673") == ["HGNC:1097"]
    assert repo.lookup_by_xref("entrez_id", "0") == []


def test_gene_group_queries(repo: HgncRepository) -> None:
    assert repo.group_name_for_id("1157") == "RAF family"
    assert "HGNC:1097" in repo.group_members(group_id="1157", group_name=None)
    matches = repo.resolve_group_name("raf")
    assert any(m["group_id"] == "1157" for m in matches)


def test_missing_db_raises() -> None:
    with pytest.raises(DataUnavailableError):
        HgncRepository("/nonexistent/path/hgnc.sqlite")
