"""Capabilities payload and hgnc:// discovery resources."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from hgnc_link import __version__
from hgnc_link.buildinfo import build_info
from hgnc_link.config import settings
from hgnc_link.constants import (
    HGNC_LICENSE,
    LOCUS_GROUPS,
    MATCH_TYPES,
    RECOMMENDED_CITATION,
    STATUS_VALUES,
    XREF_FIELDS,
    XREF_FILTER_ALIASES,
    XREF_SOURCE_ALIASES,
    XREF_TIER_COMPACT,
    XREF_TIER_MINIMAL,
)
from hgnc_link.ingest.builder import read_meta
from hgnc_link.mcp.arg_help import ARG_ALIASES, tool_signature
from hgnc_link.mcp.resources import (
    HGNC_REFERENCE_NOTES,
    HGNC_USAGE_NOTES,
    RESEARCH_USE_NOTICE,
)
from hgnc_link.services.shaping import DEFAULT_RESPONSE_MODE, RESPONSE_MODES

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Reverse the alias map to {canonical: [accepted synonyms]} for human-facing docs.
_ALIAS_DOC: dict[str, list[str]] = {}
for _alias, _canonical in sorted(ARG_ALIASES.items()):
    _ALIAS_DOC.setdefault(_canonical, []).append(_alias)

_SUMMARY_KEYS: tuple[str, ...] = (
    "server",
    "server_version",
    "build",
    "hgnc_release",
    "data_source",
    "research_use_only",
    "research_use_notice",
    "recommended_citation",
    "license",
    "tools",
    "tool_count",
    "response_modes",
    "default_response_mode",
    "recommended_workflows",
    "argument_alias_policy",
    "search_semantics",
    "error_codes",
    "limits",
    "read_only",
)

TOOLS: list[str] = [
    "get_server_capabilities",
    "get_hgnc_diagnostics",
    "resolve_symbol",
    "resolve_symbols_batch",
    "get_gene",
    "search_genes",
    "get_gene_cross_references",
    "resolve_gene_by_xref",
    "get_gene_group",
]


def _hgnc_release() -> str:
    """Best-effort loaded-release string (without forcing a DB build)."""
    meta = read_meta(settings.data.db_path)
    if meta is None:
        return "not-built"
    return meta.release or meta.source_last_modified or "unknown"


def build_capabilities() -> dict[str, Any]:
    """Return the discovery surface describing this server."""
    return {
        "server": "hgnc-link",
        "server_version": __version__,
        "build": build_info(),
        "hgnc_release": _hgnc_release(),
        "data_source": (
            "Local SQLite index built from the HGNC bulk dumps "
            "(hgnc_complete_set.json + withdrawn.txt), refreshed by cron."
        ),
        "research_use_only": True,
        "research_use_notice": RESEARCH_USE_NOTICE,
        "recommended_citation": RECOMMENDED_CITATION,
        "license": HGNC_LICENSE,
        "tools": TOOLS,
        "tool_count": len(TOOLS),
        "response_modes": list(RESPONSE_MODES),
        "default_response_mode": DEFAULT_RESPONSE_MODE,
        "match_types": list(MATCH_TYPES),
        "status_values": list(STATUS_VALUES),
        "locus_groups": list(LOCUS_GROUPS),
        "cross_reference_databases": [{"field": f, "label": label} for f, label in XREF_FIELDS],
        "cross_reference_filter_synonyms": sorted(XREF_FILTER_ALIASES),
        "cross_reference_tiers": {
            "minimal": list(XREF_TIER_MINIMAL),
            "compact": list(XREF_TIER_COMPACT),
            "standard": "all populated fields",
            "full": "all populated fields",
            "note": (
                "get_gene_cross_references emits this default field set per "
                "response_mode; an explicit databases= filter overrides the tier."
            ),
        },
        "xref_lookup_sources": sorted(set(XREF_SOURCE_ALIASES.values())),
        "provenance_policy": (
            "Static provenance (citation, HGNC release, full research-use notice "
            "text) is declared here and applies to ALL tool outputs; it is not "
            "repeated per-call to conserve context tokens. The clinical-safety "
            "disclaimer itself is the exception: per the fleet Response-Envelope "
            "Standard v1, every tool response also stamps "
            "_meta.unsafe_for_clinical_use: true (success and error, all "
            "response_modes) so it survives even if this capabilities call was "
            "never made."
        ),
        "per_call_meta": [
            "tool",
            "request_id",
            "next_commands",
            "unsafe_for_clinical_use",
        ],
        "id_normalization": "HGNC ids accepted/returned as both 'HGNC:1100' and '1100'.",
        "argument_alias_policy": (
            "argument_aliases are server-side synonyms accepted IN ADDITION to each "
            "tool's canonical parameter (e.g. symbol/gene/id -> query); an applied "
            "rewrite is disclosed under _meta.argument_aliases_applied. Tool "
            "inputSchemas stay strict (additionalProperties:false), so a "
            "schema-validating client should pass the CANONICAL name shown in "
            "tool_signatures; an unknown argument name returns invalid_input with a "
            "did-you-mean."
        ),
        "search_semantics": (
            "search_genes is nomenclature full-text search over symbol, name, alias, "
            "and previous-symbol only (relevance-ranked). It has NO disease/phenotype "
            "semantics: a descriptive query like 'polycystin kidney' will not surface "
            "PKD1/PKD2 unless those words appear in the gene's nomenclature. Use an "
            "exact symbol/id with resolve_symbol, or an external id with resolve_gene_by_xref."
        ),
        "recommended_workflows": [
            "any symbol/id -> resolve_symbol -> get_gene -> get_gene_cross_references",
            "outdated/alias symbol -> resolve_symbol (match_type tells you previous vs alias)",
            "external id (ensembl/entrez/uniprot/omim) -> resolve_gene_by_xref -> get_gene",
            "free text -> search_genes -> get_gene",
            "gene family -> get_gene_group (by id or name)",
            "many symbols at once -> resolve_symbols_batch",
        ],
        "not_found_contract": (
            "A symbol/id with no live record returns error_code 'not_found'. A "
            "withdrawn or merged symbol returns 'not_found' with obsolete:true + "
            "replaced_by + a next_command to the successor. An alias shared by "
            "several genes returns 'ambiguous_query' with the candidate list."
        ),
        "ambiguity_contract": (
            "Single-result tools (resolve_symbol, get_gene, get_gene_cross_references) "
            "return error_code 'ambiguous_query' with a candidates list and "
            "next_commands to each candidate. resolve_symbols_batch never fails the "
            "whole call: each ambiguous query is returned inline with ambiguous:true "
            "+ candidates so one ambiguity never blocks the others."
        ),
        "error_codes": [
            "invalid_input",
            "not_found",
            "ambiguous_query",
            "data_unavailable",
            "rate_limited",
            "upstream_unavailable",
            "internal_error",
        ],
        "limits": {
            "max_batch_queries": 200,
            "max_search_limit": 200,
            "max_group_limit": 1000,
        },
        "read_only": True,
        "notes": HGNC_REFERENCE_NOTES,
    }


async def collect_tool_signatures(mcp: FastMCP) -> dict[str, str]:
    """Map every registered tool to its rendered signature (from the live schema)."""
    tools = sorted(await mcp.list_tools(), key=lambda t: t.name)
    return {t.name: tool_signature(t.name, t.parameters or {}) for t in tools}


async def build_tools_overview(mcp: FastMCP) -> dict[str, Any]:
    """Lightweight discovery payload: name, one-line summary, and call signature."""
    tools = sorted(await mcp.list_tools(), key=lambda t: t.name)
    entries: list[dict[str, str]] = []
    for tool in tools:
        summary = (tool.description or "").split(". ")[0].strip()
        entries.append(
            {
                "name": tool.name,
                "summary": summary[:160],
                "signature": tool_signature(tool.name, tool.parameters or {}),
            }
        )
    return {"server": "hgnc-link", "tool_count": len(entries), "tools": entries}


def project_capabilities(detail: str, tool_signatures: dict[str, str]) -> dict[str, Any]:
    """Return the full capabilities payload, or a light summary (default)."""
    full = build_capabilities()
    full["tool_signatures"] = tool_signatures
    full["argument_aliases"] = _ALIAS_DOC
    if detail == "full":
        full["detail"] = "full"
        return full
    summary: dict[str, Any] = {k: full[k] for k in _SUMMARY_KEYS if k in full}
    summary["tool_signatures"] = tool_signatures
    summary["argument_aliases"] = _ALIAS_DOC
    summary["detail"] = "summary"
    summary["more"] = (
        "Call get_server_capabilities(detail='full') or read hgnc://capabilities "
        "for vocabularies and cross-reference databases; hgnc://tools lists signatures."
    )
    return summary


def register_capability_resources(mcp: FastMCP) -> None:
    """Register the hgnc:// resource family on a FastMCP instance."""

    @mcp.resource("hgnc://capabilities", mime_type="application/json")
    def capabilities() -> str:
        return json.dumps(build_capabilities(), indent=2)

    @mcp.resource("hgnc://tools", mime_type="application/json")
    async def tools_overview() -> str:
        return json.dumps(await build_tools_overview(mcp), indent=2)

    @mcp.resource("hgnc://usage", mime_type="text/plain")
    def usage() -> str:
        return HGNC_USAGE_NOTES

    @mcp.resource("hgnc://reference", mime_type="text/plain")
    def reference() -> str:
        return HGNC_REFERENCE_NOTES

    @mcp.resource("hgnc://research-use", mime_type="text/plain")
    def research_use() -> str:
        return RESEARCH_USE_NOTICE

    @mcp.resource("hgnc://citation", mime_type="text/plain")
    def citation() -> str:
        return RECOMMENDED_CITATION
