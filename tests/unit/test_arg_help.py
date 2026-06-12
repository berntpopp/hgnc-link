"""Tests for argument ergonomics (aliases, did-you-mean, signatures)."""

from __future__ import annotations

from hgnc_link.mcp.arg_help import (
    describe_constraints,
    did_you_mean,
    normalize_alias_args,
    tool_signature,
)


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


def test_describe_constraints_enum() -> None:
    result = describe_constraints({"enum": ["a", "b", "c"], "type": "string"})
    assert result is not None
    allowed, human = result
    assert allowed == ["a", "b", "c"]
    assert "one of" in human


def test_describe_constraints_range() -> None:
    result = describe_constraints({"type": "integer", "minimum": 1, "maximum": 200})
    assert result is not None
    allowed, human = result
    assert allowed == ["1..200"]
    assert "between 1 and 200" in human


def test_describe_constraints_none_for_plain() -> None:
    assert describe_constraints({"type": "string"}) is None
