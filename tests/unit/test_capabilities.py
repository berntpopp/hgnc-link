"""Tests for the capabilities/discovery surface."""

from __future__ import annotations

import pytest

from hgnc_link.mcp.capabilities import (
    TOOLS,
    build_capabilities,
    build_tools_overview,
    collect_tool_signatures,
    project_capabilities,
)


def test_build_capabilities_core() -> None:
    cap = build_capabilities()
    assert cap["server"] == "hgnc-link"
    assert cap["tool_count"] == len(TOOLS)
    assert "not_found" in cap["error_codes"]
    assert "ambiguous_query" in cap["error_codes"]
    assert cap["default_response_mode"] == "compact"
    assert cap["read_only"] is True


def test_capabilities_documents_ambiguity_contract() -> None:
    cap = build_capabilities()
    assert "ambiguity_contract" in cap
    assert "batch" in cap["ambiguity_contract"].lower()
    assert "cross_reference_filter_synonyms" in cap
    assert "mane" in cap["cross_reference_filter_synonyms"]


def test_capabilities_documents_xref_tiers() -> None:
    cap = build_capabilities()
    tiers = cap["cross_reference_tiers"]
    assert tiers["minimal"] == ["entrez_id", "ensembl_gene_id"]
    assert "mane_select" in tiers["compact"]
    assert tiers["standard"] == "all populated fields"


def test_capabilities_documents_argument_alias_policy() -> None:
    cap = build_capabilities()
    assert "argument_alias_policy" in cap
    policy = cap["argument_alias_policy"].lower()
    assert "server" in policy and "canonical" in policy


def test_capabilities_documents_search_semantics() -> None:
    cap = build_capabilities()
    assert "search_semantics" in cap
    assert "nomenclature" in cap["search_semantics"].lower()


def test_capabilities_surfaces_build_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    # The live finding was unknown/null build provenance in the capabilities surface.
    monkeypatch.setenv("HGNC_LINK_GIT_SHA", "abc123def456")
    monkeypatch.setenv("HGNC_LINK_BUILT_AT", "2026-06-12T00:00:00+00:00")
    cap = build_capabilities()
    assert cap["build"]["git_sha"] == "abc123def456"
    assert cap["build"]["built_at"] == "2026-06-12T00:00:00+00:00"
    assert cap["build"]["version"]


def test_project_summary_vs_full() -> None:
    sigs = {t: f"{t}()" for t in TOOLS}
    summary = project_capabilities("summary", sigs)
    assert summary["detail"] == "summary"
    assert "cross_reference_databases" not in summary  # heavy block omitted
    assert summary["tool_signatures"] == sigs
    full = project_capabilities("full", sigs)
    assert full["detail"] == "full"
    assert "cross_reference_databases" in full


async def test_collect_signatures_and_overview(facade) -> None:  # type: ignore[no-untyped-def]
    sigs = await collect_tool_signatures(facade)
    assert set(sigs) == set(TOOLS)
    assert sigs["get_gene"].startswith("get_gene(")
    overview = await build_tools_overview(facade)
    assert overview["tool_count"] == len(TOOLS)
    assert all(e["summary"] for e in overview["tools"])


def test_databases_item_enum_is_never_narrower_than_runtime() -> None:
    """The advertised `databases` item enum equals the full runtime-accepted set (review #5)."""
    from hgnc_link.constants import XREF_FILTER_ALIASES, XREF_FILTER_ENUM

    assert set(XREF_FILTER_ENUM) == set(XREF_FILTER_ALIASES)
