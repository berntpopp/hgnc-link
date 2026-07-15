"""Reverse cross-reference lookup tool: resolve_gene_by_xref."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from hgnc_link.constants import XREF_LOOKUP_SOURCE_ENUM
from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import after_xref
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
        output_schema=None,
        tags={"xref"},
        description=(
            "Reverse identifier mapping: find the HGNC gene(s) for an external "
            "database id. source is the database (entrez_id/ncbi, ensembl_gene_id, "
            "uniprot, refseq, mane_select, omim, ucsc, vega, ccds, mgi, rgd) and value "
            "is the id (e.g. source='ensembl_gene_id', value='ENSG00000157764'). A "
            "version suffix is tolerated (ENSG00000012048.23 resolves like "
            "ENSG00000012048), and a MANE Select transcript (ENST…/NM_…) resolves back "
            "to its gene. "
            "Signature: resolve_gene_by_xref(source, value, response_mode=)."
        ),
    )
    async def resolve_gene_by_xref(
        source: Annotated[
            str,
            Field(
                description=(
                    "Cross-reference database. Canonical keys: entrez_id, "
                    "ensembl_gene_id, uniprot_ids, refseq_accession, mane_select, "
                    "omim_id, ucsc_id, vega_id, ccds_id, ena, mgd_id, rgd_id. Common "
                    "synonyms (ncbi, ensembl, uniprot, refseq, mane, omim, mgi, rgd) "
                    "are also accepted."
                ),
                examples=["ensembl_gene_id", "refseq", "mane_select"],
                # Declare the canonical closed vocabulary (S4). The pydantic type stays
                # `str` so the runtime remains a SUPERSET (it also accepts the synonyms
                # above): every schema-valid value is always runtime-valid.
                json_schema_extra={"enum": list(XREF_LOOKUP_SOURCE_ENUM)},
            ),
        ],
        value: Annotated[
            str,
            Field(
                description="The external identifier value to look up (a version suffix is fine).",
                examples=["ENSG00000157764", "NM_004333.6", "P15056"],
            ),
        ],
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
