"""Gene group / family browse tool: get_gene_group."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import after_group
from hgnc_link.mcp.service_adapters import get_hgnc_service
from hgnc_link.mcp.tools._common import ResponseMode

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_group_tools(mcp: FastMCP) -> None:
    """Register the gene group browse tool."""

    @mcp.tool(
        name="get_gene_group",
        title="Get Gene Group",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"group"},
        description=(
            "Browse a HGNC gene group/family by numeric group id (e.g. '1157') or by "
            "name (e.g. 'RAF family'). Returns the member genes as symbol-ordered "
            "summaries. Members are paginated with limit + offset; the response "
            "carries member_count, returned, truncated, and next_offset, and (when "
            "truncated) a next_commands entry that fetches the next page. A name "
            "matching several groups returns the candidate groups so you can re-call "
            "with a specific id. "
            "Signature: get_gene_group(group, limit=, offset=, response_mode=)."
        ),
    )
    async def get_gene_group(
        group: Annotated[
            str,
            Field(
                description="Gene group id (numeric) or group name.",
                examples=["1157", "RAF family"],
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=1000, description="Max members (default 200).")] = 200,
        offset: Annotated[
            int, Field(ge=0, description="Skip this many members for pagination (default 0).")
        ] = 0,
        response_mode: ResponseMode = "compact",
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().get_gene_group(
                group, limit=limit, offset=offset, mode=response_mode
            )
            payload["_meta"] = {"next_commands": after_group(payload)}
            return payload

        return await run_mcp_tool(
            "get_gene_group",
            call,
            context=McpErrorContext("get_gene_group", arguments={"group": group}),
        )
