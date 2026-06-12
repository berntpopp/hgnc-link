"""Tests for the capabilities/discovery surface."""

from __future__ import annotations

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
