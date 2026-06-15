"""Tests for the MCP envelope boundary."""

from __future__ import annotations

import pytest

from hgnc_link.exceptions import (
    AmbiguousQueryError,
    DataUnavailableError,
    InvalidInputError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    WithdrawnEntryError,
)
from hgnc_link.mcp.envelope import McpErrorContext, McpToolError, _classify, run_mcp_tool


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (NotFoundError("x"), "not_found"),
        (WithdrawnEntryError("X", status="Merged/Split"), "not_found"),
        (AmbiguousQueryError("x"), "ambiguous_query"),
        (InvalidInputError("x"), "invalid_input"),
        (DataUnavailableError("x"), "data_unavailable"),
        (RateLimitError("x"), "rate_limited"),
        (ServiceUnavailableError("x"), "upstream_unavailable"),
        (RuntimeError("boom"), "internal_error"),
    ],
)
def test_classify(exc: Exception, code: str) -> None:
    assert _classify(exc)[0] == code


async def test_success_injects_meta() -> None:
    async def call() -> dict[str, object]:
        return {"hgnc_id": "HGNC:1"}

    out = await run_mcp_tool("get_gene", call, context=McpErrorContext("get_gene"))
    assert out["success"] is True
    assert out["_meta"]["tool"] == "get_gene"
    assert "request_id" in out["_meta"]


async def test_lean_meta() -> None:
    async def call() -> dict[str, object]:
        return {"x": 1, "_meta": {"next_commands": []}}

    out = await run_mcp_tool("t", call, context=McpErrorContext("t"))
    assert set(out["_meta"]) <= {"tool", "request_id", "next_commands"}


async def test_error_is_returned_not_raised() -> None:
    async def call() -> dict[str, object]:
        raise NotFoundError("nope")

    out = await run_mcp_tool(
        "get_gene", call, context=McpErrorContext("get_gene", arguments={"query": "X"})
    )
    assert out["success"] is False
    assert out["error_code"] == "not_found"
    assert out["recovery_action"] == "reformulate_input"
    assert out["_meta"]["next_commands"]  # always present


async def test_invalid_input_carries_field_allowed_hint() -> None:
    async def call() -> dict[str, object]:
        raise InvalidInputError("bad", field="source", allowed=["a", "b"], hint="use a")

    out = await run_mcp_tool(
        "resolve_gene_by_xref", call, context=McpErrorContext("resolve_gene_by_xref")
    )
    assert out["field"] == "source"
    assert out["allowed_values"] == ["a", "b"]
    assert out["hint"] == "use a"


async def test_withdrawn_envelope_flags_obsolete_and_redirects() -> None:
    async def call() -> dict[str, object]:
        raise WithdrawnEntryError(
            "A1S9T",
            status="Merged/Split",
            replaced_by=[{"hgnc_id": "HGNC:12469", "symbol": "UBA1"}],
        )

    out = await run_mcp_tool("resolve_symbol", call, context=McpErrorContext("resolve_symbol"))
    assert out["obsolete"] is True
    assert out["replaced_by"][0]["symbol"] == "UBA1"
    assert out["_meta"]["next_commands"][0] == {
        "tool": "get_gene",
        "arguments": {"query": "HGNC:12469"},
    }


async def test_ambiguous_envelope_lists_candidates() -> None:
    async def call() -> dict[str, object]:
        raise AmbiguousQueryError(
            "ambig", candidates=[{"hgnc_id": "HGNC:1"}, {"hgnc_id": "HGNC:2"}]
        )

    out = await run_mcp_tool("get_gene", call, context=McpErrorContext("get_gene"))
    assert out["error_code"] == "ambiguous_query"
    assert len(out["candidates"]) == 2
    assert out["_meta"]["next_commands"][0]["tool"] == "get_gene"


async def test_mcp_tool_error_propagates_code() -> None:
    async def call() -> dict[str, object]:
        raise McpToolError(error_code="rate_limited", message="slow down")

    out = await run_mcp_tool("t", call, context=McpErrorContext("t"))
    assert out["error_code"] == "rate_limited"
    assert out["retryable"] is True
