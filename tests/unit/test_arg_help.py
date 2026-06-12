"""Tests for argument ergonomics (aliases, did-you-mean, signatures)."""

from __future__ import annotations

from hgnc_link.mcp.arg_help import did_you_mean, normalize_alias_args, tool_signature


def test_normalize_alias_applies_only_for_real_params() -> None:
    new, applied = normalize_alias_args(["query", "response_mode"], {"symbol": "BRAF"})
    assert new == {"query": "BRAF"}
    assert applied == [("symbol", "query")]


def test_explicit_canonical_wins_over_alias() -> None:
    new, applied = normalize_alias_args(["query"], {"symbol": "X", "query": "Y"})
    assert new == {"query": "Y"}
    assert applied == []  # alias dropped, no rewrite recorded


def test_alias_ignored_when_canonical_not_a_param() -> None:
    new, applied = normalize_alias_args(["source", "value"], {"symbol": "X"})
    assert new == {"symbol": "X"}  # query is not a param of this tool
    assert applied == []


def test_did_you_mean_alias_then_fuzzy() -> None:
    assert did_you_mean("symbol", ["query", "response_mode"]) == "query"
    assert did_you_mean("querie", ["query", "limit"]) == "query"
    assert did_you_mean("zzz", ["query"]) is None


def test_tool_signature_orders_required_first() -> None:
    schema = {"properties": {"query": {}, "response_mode": {}}, "required": ["query"]}
    assert tool_signature("get_gene", schema) == "get_gene(query, response_mode=)"
