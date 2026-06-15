"""Tests for next_commands chaining builders."""

from __future__ import annotations

from hgnc_link.mcp.next_commands import (
    after_get_gene,
    after_group,
    after_resolve,
    after_search,
    after_xref,
    cmd,
    default_error_next_commands,
    withdrawn_recovery,
)


def test_cmd_shape() -> None:
    assert cmd("get_gene", query="BRAF") == {"tool": "get_gene", "arguments": {"query": "BRAF"}}


def test_after_resolve_success_and_ambiguous_and_empty() -> None:
    ok = after_resolve({"hgnc_id": "HGNC:1", "query": "BRAF"})
    assert ok[0] == cmd("get_gene", query="HGNC:1")
    amb = after_resolve({"ambiguous": True, "candidates": [{"hgnc_id": "HGNC:1"}], "query": "X"})
    assert amb[0]["tool"] == "get_gene"
    empty = after_resolve({"hgnc_id": None, "query": "X"})
    assert empty[0]["tool"] == "search_genes"


def test_after_get_gene_includes_group_when_present() -> None:
    chain = after_get_gene({"hgnc_id": "HGNC:1", "gene_group_id": ["1157"]})
    assert any(c["tool"] == "get_gene_group" for c in chain)
    assert after_get_gene({})[0]["tool"] == "get_server_capabilities"


def test_after_search_empty_points_home() -> None:
    assert after_search("X", [])[0]["tool"] == "resolve_symbol"
    assert after_search("X", [{"hgnc_id": "HGNC:1"}])[0] == cmd("get_gene", query="HGNC:1")


def test_after_xref_and_group() -> None:
    assert after_xref([{"hgnc_id": "HGNC:1"}])[0] == cmd("get_gene", query="HGNC:1")
    assert after_xref([])[0]["tool"] == "get_server_capabilities"
    assert after_group({"members": [{"hgnc_id": "HGNC:1"}]})[0] == cmd("get_gene", query="HGNC:1")
    amb = after_group({"ambiguous": True, "matches": [{"group_id": "1"}]})
    assert amb[0]["tool"] == "get_gene_group"


def test_withdrawn_recovery() -> None:
    assert withdrawn_recovery([{"hgnc_id": "HGNC:9"}])[0] == cmd("get_gene", query="HGNC:9")
    assert withdrawn_recovery([])[0]["tool"] == "get_server_capabilities"


def test_default_error_next_commands() -> None:
    # a symbol-shaped query routes to search
    assert (
        default_error_next_commands("get_gene", "not_found", {"query": "BRAF"})[0]["tool"]
        == "search_genes"
    )
    # data_unavailable -> diagnostics
    assert (
        default_error_next_commands("get_gene", "data_unavailable", {})[0]["tool"]
        == "get_hgnc_diagnostics"
    )
    # fallback
    assert (
        default_error_next_commands("resolve_gene_by_xref", "internal_error", {})[0]["tool"]
        == "get_server_capabilities"
    )
