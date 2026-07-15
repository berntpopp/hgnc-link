"""Discovery tools: get_server_capabilities, get_hgnc_diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field

from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.capabilities import collect_tool_signatures, project_capabilities
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import cmd
from hgnc_link.mcp.service_adapters import get_hgnc_service

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_discovery_tools(mcp: FastMCP) -> None:
    """Register discovery tools on a FastMCP instance."""

    @mcp.tool(
        name="get_server_capabilities",
        title="Get Server Capabilities",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"discovery"},
        description=(
            "Return the hgnc-link discovery surface. detail='summary' (default) is "
            "light: identity/build/HGNC release, the tool list WITH call signatures, "
            "accepted argument aliases, response modes, recommended workflows, error "
            "taxonomy, and limits. detail='full' adds vocabularies (locus groups, "
            "status values, match types) and the cross-reference database catalogue. "
            "Call this first in a cold session, or read hgnc://tools / "
            "hgnc://capabilities. "
            "Signature: get_server_capabilities(detail=)."
        ),
    )
    async def get_server_capabilities(
        detail: Annotated[
            Literal["summary", "full"],
            Field(description="summary (default, light) or full (adds vocabularies/xref dbs)."),
        ] = "summary",
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            signatures = await collect_tool_signatures(mcp)
            return project_capabilities(detail, signatures)

        return await run_mcp_tool(
            "get_server_capabilities",
            call,
            context=McpErrorContext("get_server_capabilities"),
        )

    @mcp.tool(
        name="get_hgnc_diagnostics",
        title="Get HGNC Diagnostics",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"discovery"},
        description=(
            "Report the local HGNC index status: whether the data is built, the "
            "loaded release date, gene/withdrawn counts, schema version, and when it "
            "was built. Use this to confirm freshness or diagnose an unavailable-data "
            "error. "
            "Signature: get_hgnc_diagnostics()."
        ),
    )
    async def get_hgnc_diagnostics() -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().get_diagnostics()
            payload["_meta"] = {
                "next_commands": [cmd("resolve_symbol", query="BRAF")]
                if payload.get("data_available")
                else [cmd("get_server_capabilities")]
            }
            return payload

        return await run_mcp_tool(
            "get_hgnc_diagnostics",
            call,
            context=McpErrorContext("get_hgnc_diagnostics"),
        )
