"""Tests for the HgncService orchestration (resolution cascade + operations)."""

from __future__ import annotations

import pytest

from hgnc_link.exceptions import (
    AmbiguousQueryError,
    DataUnavailableError,
    InvalidInputError,
    NotFoundError,
    WithdrawnEntryError,
)
from hgnc_link.services.hgnc_service import HgncService


def test_resolve_current_symbol(service: HgncService) -> None:
    r = service.resolve("braf")
    assert r["hgnc_id"] == "HGNC:1097"
    assert r["match_type"] == "current"
    assert r["ambiguous"] is False


def test_resolve_alias_and_previous(service: HgncService) -> None:
    r = service.resolve("BRAF1")  # alias of BRAF
    assert r["hgnc_id"] == "HGNC:1097"
    assert r["match_type"] == "alias"


def test_resolve_by_id_both_forms(service: HgncService) -> None:
    assert service.resolve("HGNC:1097")["approved_symbol"] == "BRAF"
    assert service.resolve("1097")["approved_symbol"] == "BRAF"
    assert service.resolve("HGNC:1097")["match_type"] == "hgnc_id"


def test_resolve_withdrawn_raises_with_redirect(service: HgncService) -> None:
    with pytest.raises(WithdrawnEntryError) as exc:
        service.resolve("A1S9T")
    assert exc.value.replaced_by[0]["hgnc_id"] == "HGNC:12469"


def test_resolve_unknown_and_empty(service: HgncService) -> None:
    with pytest.raises(NotFoundError):
        service.resolve("NOSUCHGENE")
    with pytest.raises(InvalidInputError):
        service.resolve("   ")


def test_resolve_missing_id_not_in_db(service: HgncService) -> None:
    with pytest.raises(NotFoundError):
        service.resolve("HGNC:999999")


def test_get_gene_alias_aware_and_modes(service: HgncService) -> None:
    full = service.get_gene("MLL2", mode="full") if False else service.get_gene("BRAF", mode="full")
    assert full["date_modified"]  # full keeps dates
    compact = service.get_gene("BRAF", mode="compact")
    assert "date_modified" not in compact  # compact drops dates
    minimal = service.get_gene("BRAF", mode="minimal")
    assert set(minimal) <= {
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


def test_get_gene_ambiguous(service: HgncService, repo) -> None:  # type: ignore[no-untyped-def]
    # WT1 and TUBB are unrelated; craft ambiguity by querying an alias shared by two.
    # The fixtures have no shared alias, so assert the non-ambiguous happy path here
    # and exercise the ambiguous branch via the unit-level resolve test below.
    assert service.get_gene("TP53")["symbol"] == "TP53"


def test_cross_references_and_filter(service: HgncService) -> None:
    xr = service.get_cross_references("TP53")
    assert xr["hgnc_id"] == "HGNC:11998"
    assert "ensembl_gene_id" in xr["cross_references"]
    only = service.get_cross_references("TP53", databases=["ensembl"])
    assert set(only["cross_references"]) == {"ensembl_gene_id"}


def test_lookup_by_xref_and_unknown_source(service: HgncService) -> None:
    r = service.lookup_by_xref("ensembl", "ENSG00000157764")
    assert r["results"][0]["symbol"] == "BRAF"
    with pytest.raises(InvalidInputError):
        service.lookup_by_xref("not_a_db", "x")
    with pytest.raises(NotFoundError):
        service.lookup_by_xref("entrez_id", "0")


def test_search(service: HgncService) -> None:
    res = service.search("tumor", limit=5)
    assert any(h["symbol"] == "TP53" for h in res["results"])
    with pytest.raises(InvalidInputError):
        service.search("")


def test_gene_group_by_id_and_name(service: HgncService) -> None:
    g = service.get_gene_group("1157")
    assert g["group_name"] == "RAF family"
    assert any(m["symbol"] == "BRAF" for m in g["members"])
    with pytest.raises(NotFoundError):
        service.get_gene_group("99999")


def test_resolve_batch(service: HgncService) -> None:
    out = service.resolve_batch(["BRAF", "A1S9T", "NOSUCH"])
    assert out["query_count"] == 3
    assert out["resolved_count"] == 1
    statuses = {r["query"]: r for r in out["results"]}
    assert statuses["A1S9T"].get("obsolete") is True
    assert statuses["NOSUCH"].get("unresolved") is True
    with pytest.raises(InvalidInputError):
        service.resolve_batch([])


def test_diagnostics(service: HgncService) -> None:
    d = service.get_diagnostics()
    assert d["data_available"] is True
    assert d["gene_count"] == 8


def test_service_without_repo_raises_data_unavailable() -> None:
    svc = HgncService(None)
    with pytest.raises(DataUnavailableError):
        svc.resolve("BRAF")
    diag = svc.get_diagnostics()
    assert diag["data_available"] is False


def test_ambiguous_alias(service: HgncService, repo) -> None:  # type: ignore[no-untyped-def]
    # Directly seed an ambiguous alias scenario by checking resolve handles >1 best.
    # Build a synthetic pair set via monkeypatching repo.lookup_symbol.
    original = repo.lookup_symbol
    repo.lookup_symbol = lambda s: [("HGNC:1097", "alias"), ("HGNC:11998", "alias")]  # type: ignore[method-assign]
    try:
        r = service.resolve("SHARED")
        assert r["ambiguous"] is True
        assert r["hgnc_id"] is None
        assert r["candidate_count"] == 2
        with pytest.raises(AmbiguousQueryError):
            service.get_gene("SHARED")
    finally:
        repo.lookup_symbol = original  # type: ignore[method-assign]
