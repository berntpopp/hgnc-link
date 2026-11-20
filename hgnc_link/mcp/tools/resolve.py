"""Resolution tools: resolve_symbol, resolve_symbols_batch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastmcp.tools import ToolResult
from pydantic import Field

from hgnc_link.mcp.annotations import READ_ONLY_OPEN_WORLD
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool
from hgnc_link.mcp.next_commands import after_resolve, cmd
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
        output_schema=None,
        tags={"resolve"},
        description=(
            "Resolve any gene symbol, HGNC id or external gene id to its canonical record. "
            "For 2 or more genes, call resolve_symbols_batch once (up to 200, same accepted "
            "forms) instead of calling this tool per gene. "
            "Accepts a current symbol, a previous (withdrawn) symbol, an alias, an NCBI Gene "
            "synonym HGNC does not list, an HGNC id in either form (HGNC:1100 or "
            "1100), or an Ensembl gene id (ENSG00000157764), RefSeq accession, UniProt "
            "accession or NCBIGene:<n> CURIE, case-insensitively. Returns {hgnc_id, approved_symbol, name, status, "
            "locus_type, location, match_type (hgnc_id|current|previous|alias|"
            "ncbi_synonym|ensembl_gene_id|entrez_id|refseq_accession|mane_select|uniprot_ids)}; an "
            "id-type match_type names the external id type that matched; location is the "
            "cytogenetic band (chromosome location, e.g. 3p24.3). ncbi_synonym means only "
            "NCBI Gene (not HGNC) knows the symbol, and it ranks below every HGNC match. "
            "A bare number is always read as an HGNC id, never an NCBI Gene id (write NCBIGene:<n> "
            "for that): the result "
            "then carries a note, and next_commands offers resolve_gene_by_xref("
            "source='entrez_id'). "
            "An alias or synonym shared by several genes returns an ambiguous_query error with "
            "the candidate list (not silently picked); a withdrawn/merged symbol "
            "returns a not_found error that redirects to the successor record."
        ),
    )
    async def resolve_symbol(
        query: QueryStr, response_mode: ResponseMode = "compact"
    ) -> dict[str, Any] | ToolResult:
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
        output_schema=None,
        tags={"resolve"},
        description=(
            "Resolve or translate a batch of gene symbols, HGNC ids and/or external gene ids "
            "in one call (max 200). Accepts Ensembl gene ids (e.g. ENSG00000157764), RefSeq "
            "accessions, UniProt accessions and NCBIGene:<n> CURIEs, so a list of ENSG ids -> HGNC symbols is one "
            "call. Each "
            "entry is resolved exactly like resolve_symbol; an individual miss or "
            "withdrawal never fails the batch (it is marked unresolved / obsolete in that "
            "entry). Returns one row per input in input order (each keeps its input as "
            "query, with approved_symbol, hgnc_id, match_type), resolved/unresolved counts, "
            "and unresolved_queries (the inputs with no single match). "
            "Signature: resolve_symbols_batch(queries, response_mode=)."
        ),
    )
    async def resolve_symbols_batch(
        queries: Annotated[
            list[str],
            Field(
                max_length=200,
                description="Gene symbols, HGNC ids and/or Ensembl gene / RefSeq / UniProt / "
                "NCBIGene:<n> ids to resolve (max 200).",
                examples=[["BRCA1", "TP53", "HGNC:1100"], ["ENSG00000157764", "ENSG00000141510"]],
            ),
        ],
        response_mode: ResponseMode = "compact",
    ) -> dict[str, Any] | ToolResult:
        async def call() -> dict[str, Any]:
            payload = get_hgnc_service().resolve_batch(queries, response_mode)
            payload["_meta"] = {"next_commands": [cmd("get_server_capabilities")]}
            return payload

        return await run_mcp_tool(
            "resolve_symbols_batch",
            call,
            context=McpErrorContext("resolve_symbols_batch", arguments={"queries": queries}),
        )
