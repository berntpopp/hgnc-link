"""Reverse cross-reference lookup tool: resolve_gene_by_xref."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import after_xref
from hgnc_link.mcp.schemas import XREF_LOOKUP_SCHEMA
from hgnc_link.mcp.service_adapters import get_hgnc_service
from hgnc_link.mcp.tools._common import ResponseMode

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_xref_tools(mcp: FastMCP) -> None:
    """Register the reverse cross-reference lookup tool."""

    @mcp.tool(
        name="resolve_gene_by_xref",
        title="Resolve Gene by Cross-Reference",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=XREF_LOOKUP_SCHEMA,
        tags={"xref"},
        description=(
            "Reverse identifier mapping: find the HGNC gene(s) for an external "
            "database id. source is the database (entrez_id/ncbi, ensembl_gene_id, "
            "uniprot, refseq, omim, ucsc, vega, ccds, mgi, rgd) and value is the id "
            "(e.g. source='ensembl_gene_id', value='ENSG00000157764'). "
            "Signature: resolve_gene_by_xref(source, value, response_mode=)."
        ),
    )
    async def resolve_gene_by_xref(
        source: Annotated[
            str,
            Field(
                description="Cross-reference database, e.g. entrez_id, ensembl_gene_id, uniprot."
            ),
        ],
        value: Annotated[str, Field(description="The external identifier value to look up.")],
        response_mode: ResponseMode = "compact",
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().lookup_by_xref(source, value, response_mode)
            payload["_meta"] = {"next_commands": after_xref(payload.get("results", []))}
            return payload

        return await run_mcp_tool(
            "resolve_gene_by_xref",
            call,
            context=McpErrorContext(
                "resolve_gene_by_xref", arguments={"source": source, "value": value}
            ),
        )
