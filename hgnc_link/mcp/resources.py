"""Static string resources for MCP instructions and discovery resources."""

from __future__ import annotations

from hgnc_link.constants import HGNC_LICENSE

RESEARCH_USE_NOTICE = (
    "Research use only; not for clinical decision support, diagnosis, "
    "treatment, or patient management."
)

HGNC_SERVER_INSTRUCTIONS = (
    "HGNC-Link grounds gene-nomenclature work in the HUGO Gene Nomenclature "
    "Committee dataset (genenames.org). It is backed by a local index built from "
    "the HGNC bulk dumps and refreshed by cron, so lookups are fast and offline.\n"
    "- Resolve first: resolve_symbol(query=) maps ANY symbol (current, previous, "
    "or alias; case-insensitive) or HGNC id (HGNC:1100 or 1100) to the canonical "
    "{hgnc_id, approved_symbol, match_type}. It surfaces ambiguity (an alias used "
    "by several genes) instead of silently picking, and redirects withdrawn/merged "
    "symbols to their successor. resolve_symbols_batch(queries=[...]) does many at "
    "once and never fails on an individual miss.\n"
    "- Records: get_gene(query=) returns the full record (also alias/previous "
    "aware). search_genes(query=, limit=) is FTS over symbol/name/alias/previous.\n"
    "- Cross-references: get_gene_cross_references(query=, databases=) maps a gene "
    "to NCBI/Ensembl/UniProt/RefSeq/OMIM/MANE/etc; resolve_gene_by_xref(source=, value=) "
    "is the reverse (e.g. ensembl_gene_id -> gene). get_gene_group(group=) browses "
    "a gene family by id or name.\n"
    "- Verbosity: every tool takes response_mode (minimal | compact | standard | "
    "full, default compact). Synonyms like symbol/gene/id/hgnc_id are accepted as "
    "aliases for query.\n"
    "- Chaining: every response carries _meta.next_commands, a ready-to-call list "
    "of {tool, arguments} steps, on success AND error. A wrong argument name/type "
    "returns the same structured invalid_input envelope (valid names + a "
    "did-you-mean). Discovery: get_server_capabilities or get_hgnc_diagnostics, or "
    "read hgnc://capabilities / hgnc://tools. "
    f"{RESEARCH_USE_NOTICE}"
)

HGNC_USAGE_NOTES = (
    "Start with resolve_symbol to normalise any gene name/id to its approved HGNC "
    "symbol + id, then get_gene for the full record and get_gene_cross_references "
    "for external ids. Use search_genes for free text, resolve_gene_by_xref to go from an "
    "external id back to HGNC, and get_gene_group to browse a family. Follow "
    "_meta.next_commands to advance without guessing the next tool. resolve_symbol "
    "carries match_type (current/previous/alias/hgnc_id) so you know whether the "
    "input was an outdated symbol."
)

HGNC_REFERENCE_NOTES = (
    "Error codes: invalid_input, not_found, ambiguous_query, upstream_unavailable, "
    "rate_limited, internal. A withdrawn/merged symbol "
    "returns not_found with obsolete:true + replaced_by + a next_command to the "
    "successor record. The local index is built from hgnc_complete_set.json + "
    "withdrawn.txt (HGNC updates Tue/Fri) and refreshed by an external cron job; "
    "get_hgnc_diagnostics reports the loaded release and counts. "
    f"{HGNC_LICENSE}"
)
