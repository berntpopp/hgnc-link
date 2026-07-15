"""Gene record tools: get_gene, search_genes, get_gene_cross_references."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from hgnc_link.constants import XREF_FILTER_ENUM
from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import after_get_gene, after_search, cmd
from hgnc_link.mcp.service_adapters import get_hgnc_service
from hgnc_link.mcp.tools._common import QueryStr, ResponseMode

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_gene_tools(mcp: FastMCP) -> None:
    """Register gene record / search / cross-reference tools."""

    @mcp.tool(
        name="get_gene",
        title="Get Gene Record",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"gene"},
        description=(
            "Return the full HGNC record for a gene, resolved from an HGNC id, "
            "current symbol, previous symbol, or alias. Includes name, status, "
            "locus group/type, location, aliases/previous symbols, gene groups, and "
            "all cross-references. response_mode controls verbosity (compact drops "
            "dates/provenance; minimal keeps identity + anchor ids). "
            "Signature: get_gene(query, response_mode=)."
        ),
    )
    async def get_gene(query: QueryStr, response_mode: ResponseMode = "compact") -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().get_gene(query, response_mode)
            payload["_meta"] = {"next_commands": after_get_gene(payload)}
            return payload

        return await run_mcp_tool(
            "get_gene",
            call,
            context=McpErrorContext("get_gene", arguments={"query": query}),
        )

    @mcp.tool(
        name="search_genes",
        title="Search Genes",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"gene"},
        description=(
            "Free-text search over gene symbols, names, aliases, and previous "
            "symbols (FTS, relevance-ranked). Returns ranked {hgnc_id, symbol, name, "
            "locus_type, score} summaries. Nomenclature-only: there is NO "
            "disease/phenotype semantics, so a descriptive query (e.g. 'polycystin "
            "kidney') only matches words present in a gene's nomenclature. Use "
            "resolve_symbol for an exact symbol/id; use this for partial names. "
            "Signature: search_genes(query, limit=, response_mode=)."
        ),
    )
    async def search_genes(
        query: Annotated[
            str,
            Field(
                description="Free-text query (symbol fragment, name, alias).",
                examples=["BRCA", "kinase", "TP53"],
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=200, description="Max hits (default 25).")] = 25,
        response_mode: ResponseMode = "compact",
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().search(query, limit=limit, mode=response_mode)
            payload["_meta"] = {"next_commands": after_search(query, payload.get("results", []))}
            return payload

        return await run_mcp_tool(
            "search_genes",
            call,
            context=McpErrorContext("search_genes", arguments={"query": query}),
        )

    @mcp.tool(
        name="get_gene_cross_references",
        title="Get Gene Cross-References",
        annotations=READ_ONLY_OPEN_WORLD,
        output_schema=None,
        tags={"gene", "xref"},
        description=(
            "Return external database cross-references for a gene (forward identifier "
            "mapping): NCBI Gene, Ensembl, UniProt, RefSeq, MANE Select, OMIM, UCSC, "
            "VEGA, CCDS, MGI, RGD, Orphanet, COSMIC, PubMed. response_mode sets the "
            "default field set: minimal=NCBI+Ensembl ids; compact (default)=the "
            "high-value ids (NCBI, Ensembl, UniProt, RefSeq, MANE Select, OMIM, CCDS); "
            "standard/full=every populated field. databases optionally filters to "
            "specific sources by field key OR friendly label (e.g. 'mane', 'ncbi', "
            "'uniprot') and OVERRIDES the response_mode tier; an unknown key is "
            "rejected with invalid_input + did-you-mean. Resolve the gene from an "
            "id/symbol/alias first. "
            "Signature: get_gene_cross_references(query, databases=, response_mode=)."
        ),
    )
    async def get_gene_cross_references(
        query: QueryStr,
        databases: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Optional cross-reference filter: a list of field keys or friendly "
                    "labels (e.g. 'ncbi', 'ensembl', 'uniprot', 'refseq', 'mane', 'omim', "
                    "'ucsc', 'vega', 'ccds', 'mgi', 'rgd', 'pubmed'). Overrides the "
                    "response_mode tier; an unknown key is rejected with invalid_input + "
                    "did_you_mean."
                ),
                examples=[["ensembl", "uniprot", "omim"], ["mane"]],
                # Declare the item vocabulary (S4) as EXACTLY the runtime-accepted set,
                # so the enum is never narrower than the runtime; the `str` item type
                # keeps the service's did-you-mean on the rejection path.
                json_schema_extra={"items": {"type": "string", "enum": list(XREF_FILTER_ENUM)}},
            ),
        ] = None,
        response_mode: ResponseMode = "compact",
    ) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().get_cross_references(
                query, databases=databases, mode=response_mode
            )
            hgnc_id = payload.get("hgnc_id")
            payload["_meta"] = {
                "next_commands": [cmd("get_gene", query=hgnc_id)]
                if hgnc_id
                else [cmd("get_server_capabilities")]
            }
            return payload

        return await run_mcp_tool(
            "get_gene_cross_references",
            call,
            context=McpErrorContext("get_gene_cross_references", arguments={"query": query}),
        )
