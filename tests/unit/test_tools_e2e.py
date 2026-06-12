"""End-to-end tool calls through the real FastMCP facade (fixture-backed)."""

from __future__ import annotations

from typing import Any


async def test_capabilities_tool(facade: Any, structured: Any) -> None:
    res = await facade.call_tool("get_server_capabilities", {})
    payload = structured(res)
    assert payload["success"] is True
    assert payload["tool_count"] == 9


async def test_diagnostics_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_hgnc_diagnostics", {}))
    assert payload["data_available"] is True
    assert payload["gene_count"] == 8
    assert payload["_meta"]["next_commands"][0]["tool"] == "resolve_symbol"


async def test_resolve_tool_success(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "BRAF"}))
    assert payload["hgnc_id"] == "HGNC:1097"
    assert payload["match_type"] == "current"
    assert payload["_meta"]["next_commands"][0]["tool"] == "get_gene"


async def test_resolve_alias_via_arg_alias(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"symbol": "BRAF1"}))
    assert payload["match_type"] == "alias"
    assert payload["_meta"]["argument_aliases_applied"] == [["symbol", "query"]]


async def test_get_gene_modes(facade: Any, structured: Any) -> None:
    full = structured(
        await facade.call_tool("get_gene", {"query": "BRAF", "response_mode": "full"})
    )
    assert "date_modified" in full
    compact = structured(await facade.call_tool("get_gene", {"query": "BRAF"}))
    assert "date_modified" not in compact


async def test_withdrawn_redirect(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "A1S9T"}))
    assert payload["success"] is False
    assert payload["error_code"] == "not_found"
    assert payload["obsolete"] is True
    assert payload["_meta"]["next_commands"][0]["arguments"]["query"] == "HGNC:12469"


async def test_not_found(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene", {"query": "ZZZZZ"}))
    assert payload["error_code"] == "not_found"
    assert payload["recovery_action"] == "reformulate_input"


async def test_search_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("search_genes", {"query": "tumor"}))
    assert any(h["symbol"] == "TP53" for h in payload["results"])


async def test_cross_references_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene_cross_references", {"query": "TP53"}))
    assert "ensembl_gene_id" in payload["cross_references"]


async def test_lookup_by_xref_tool(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool(
            "lookup_by_xref", {"source": "ensembl_gene_id", "value": "ENSG00000157764"}
        )
    )
    assert payload["results"][0]["symbol"] == "BRAF"


async def test_lookup_by_xref_unknown_source(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("lookup_by_xref", {"source": "bogus", "value": "x"})
    )
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "source"
    assert payload["allowed_values"]


async def test_gene_group_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene_group", {"group": "1157"}))
    assert payload["group_name"] == "RAF family"
    assert any(m["symbol"] == "BRAF" for m in payload["members"])


async def test_batch_tool(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("resolve_symbols_batch", {"queries": ["BRAF", "A1S9T", "NOSUCH"]})
    )
    assert payload["resolved_count"] == 1
    assert payload["unresolved_count"] == 2


async def test_resolve_ambiguous_is_structured_error(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "DUPE"}))
    assert payload["success"] is False
    assert payload["error_code"] == "ambiguous_query"
    assert len(payload["candidates"]) == 2
    assert payload["recovery_action"] == "reformulate_input"
    assert payload["_meta"]["next_commands"][0]["tool"] == "get_gene"
