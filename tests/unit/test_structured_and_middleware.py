"""Structured-output declaration and argument-middleware behaviour."""

from __future__ import annotations

from typing import Any


async def test_every_tool_declares_output_schema(facade: Any) -> None:
    tools = await facade.list_tools()
    assert tools
    assert all(t.output_schema is not None for t in tools)


async def test_batch_queries_schema_capped_at_200(facade: Any) -> None:
    # The 200-cap should be visible in the published schema (client-side parity).
    tool = await facade.get_tool("resolve_symbols_batch")
    queries = tool.parameters["properties"]["queries"]
    assert queries["maxItems"] == 200


async def test_batch_overflow_returns_helpful_envelope(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("resolve_symbols_batch", {"queries": ["BRAF"] * 201})
    )
    assert payload["success"] is False
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "queries"
    assert "200" in (payload["message"] + str(payload.get("hint", "")))


async def test_structured_content_and_textcontent_fallback(facade: Any) -> None:
    res = await facade.call_tool("resolve_symbol", {"query": "BRAF"})
    assert isinstance(res.structured_content, dict)
    assert res.content and res.content[0].text  # back-compat JSON block


async def test_bad_arg_name_returns_invalid_input(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene", {"geme": "BRAF"}))
    assert payload["success"] is False
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "query"  # missing required after alias miss
    assert "get_gene(" in payload["hint"]
    assert payload["_meta"]["next_commands"][0]["tool"] == "get_server_capabilities"


async def test_unknown_arg_suggests_canonical(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("get_gene", {"query": "BRAF", "respons_mode": "full"})
    )
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "respons_mode"
    assert "response_mode" in (payload["message"] + str(payload.get("hint", "")))
