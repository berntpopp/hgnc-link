"""Resolution tools: resolve_symbol, resolve_symbols_batch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import after_resolve, cmd
from hgnc_link.mcp.schemas import RESOLVE_BATCH_SCHEMA, RESOLVE_SCHEMA
from hgnc_link.mcp.service_adapters import get_hgnc_service
from hgnc_link.mcp.tools._common import QueryStr, ResponseMode

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_resolve_tools(mcp: FastMCP) -> None:
    """Register symbol-resolution tools on a FastMCP instance."""

    @mcp.tool(
        name="resolve_symbol",
        title="Resolve Gene Symbol",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=RESOLVE_SCHEMA,
        tags={"resolve"},
        description=(
            "Resolve any gene symbol or HGNC id to its canonical record. Accepts a "
            "current symbol, a previous (withdrawn) symbol, an alias, or an HGNC id "
            "in either form (HGNC:1100 or 1100), case-insensitively. Returns "
            "{hgnc_id, approved_symbol, match_type (hgnc_id|current|previous|alias)}. "
            "An alias shared by several genes returns an ambiguous_query error with "
            "the candidate list (not silently picked); a withdrawn/merged symbol "
            "returns a not_found error that redirects to the successor record. "
            "Signature: resolve_symbol(query, response_mode=)."
        ),
    )
    async def resolve_symbol(
        query: QueryStr, response_mode: ResponseMode = "compact"
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().resolve(query, response_mode)
            payload["_meta"] = {"next_commands": after_resolve(payload)}
            return payload

        return await run_mcp_tool(
            "resolve_symbol",
            call,
            context=McpErrorContext("resolve_symbol", arguments={"query": query}),
        )

    @mcp.tool(
        name="resolve_symbols_batch",
        title="Resolve Gene Symbols (Batch)",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=RESOLVE_BATCH_SCHEMA,
        tags={"resolve"},
        description=(
            "Resolve a batch of gene symbols / HGNC ids in one call (max 200). Each "
            "entry is resolved with the same current->previous->alias cascade as "
            "resolve_symbol; an individual miss or withdrawal never fails the batch "
            "(it is marked unresolved / obsolete in that entry). Returns per-query "
            "results plus resolved/unresolved counts. "
            "Signature: resolve_symbols_batch(queries, response_mode=)."
        ),
    )
    async def resolve_symbols_batch(
        queries: Annotated[
            list[str],
            Field(max_length=200, description="Gene symbols and/or HGNC ids to resolve (max 200)."),
        ],
        response_mode: ResponseMode = "compact",
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().resolve_batch(queries, response_mode)
            payload["_meta"] = {"next_commands": [cmd("get_server_capabilities")]}
            return payload

        return await run_mcp_tool(
            "resolve_symbols_batch",
            call,
            context=McpErrorContext("resolve_symbols_batch", arguments={"queries": queries}),
        )
