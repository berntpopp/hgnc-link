"""Builders for `_meta.next_commands` entries: `{tool, arguments}` steps."""

from __future__ import annotations

from typing import Any

from hgnc_link.identifiers import infer_xref_source, looks_like_hgnc_id, looks_like_symbol

_GENE_TOOLS = {
    "resolve_symbol",
    "get_gene",
    "get_gene_cross_references",
    "lookup_by_xref",
    "get_gene_group",
}


def cmd(tool: str, **arguments: Any) -> dict[str, Any]:
    """One ready-to-call next step."""
    return {"tool": tool, "arguments": arguments}


def default_error_next_commands(
    tool: str, error_code: str, arguments: dict[str, Any]
) -> list[dict[str, Any]]:
    """A sensible recovery step for any error lacking an explicit fallback."""
    if tool in ("resolve_symbol", "get_gene"):
        value = str(arguments.get("query", ""))
        source = infer_xref_source(value)
        if source:
            return [
                cmd("lookup_by_xref", source=source, value=value),
                cmd("search_genes", query=value),
            ]
        if value and looks_like_symbol(value):
            return [cmd("search_genes", query=value), cmd("get_server_capabilities")]
        if value and not looks_like_hgnc_id(value):
            return [cmd("search_genes", query=value), cmd("get_server_capabilities")]
    if error_code == "data_unavailable":
        return [cmd("get_hgnc_diagnostics")]
    return [cmd("get_server_capabilities")]


def after_resolve(resolution: dict[str, Any]) -> list[dict[str, Any]]:
    """After resolve_symbol: drill into the resolved gene, or disambiguate."""
    if resolution.get("ambiguous"):
        cands = resolution.get("candidates", [])[:3]
        chain = [cmd("get_gene", query=c["hgnc_id"]) for c in cands if c.get("hgnc_id")]
        return chain or [cmd("search_genes", query=str(resolution.get("query", "")))]
    hgnc_id = resolution.get("hgnc_id")
    if not hgnc_id:
        return [cmd("search_genes", query=str(resolution.get("query", "")))]
    return [
        cmd("get_gene", query=hgnc_id),
        cmd("get_gene_cross_references", query=hgnc_id),
    ]


def after_get_gene(gene: dict[str, Any]) -> list[dict[str, Any]]:
    """After get_gene: offer cross-references and (if any) the gene's group."""
    hgnc_id = gene.get("hgnc_id")
    if not hgnc_id:
        return [cmd("get_server_capabilities")]
    chain = [cmd("get_gene_cross_references", query=hgnc_id)]
    group_ids = gene.get("gene_group_id") or []
    if group_ids:
        chain.append(cmd("get_gene_group", group=str(group_ids[0])))
    return chain[:2]


def after_search(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """After search_genes: fetch the top hit, or point home if empty."""
    if not hits:
        return [cmd("resolve_symbol", query=query), cmd("get_server_capabilities")]
    top = hits[0].get("hgnc_id")
    return [cmd("get_gene", query=top)] if top else [cmd("get_server_capabilities")]


def after_xref(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """After lookup_by_xref: fetch the first matched gene."""
    if not results:
        return [cmd("get_server_capabilities")]
    first = results[0].get("hgnc_id")
    return [cmd("get_gene", query=first)] if first else [cmd("get_server_capabilities")]


def after_group(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """After get_gene_group: drill into the first member (or disambiguate)."""
    if payload.get("ambiguous"):
        matches = payload.get("matches", [])[:2]
        return [
            cmd("get_gene_group", group=str(m["group_id"])) for m in matches if m.get("group_id")
        ]
    members = payload.get("members", [])
    if members and members[0].get("hgnc_id"):
        return [cmd("get_gene", query=members[0]["hgnc_id"])]
    return [cmd("get_server_capabilities")]


def withdrawn_recovery(replaced_by: list[dict[str, str]]) -> list[dict[str, Any]]:
    """After a withdrawn-entry error: chain to the live successor record(s)."""
    targets = [r.get("hgnc_id") for r in replaced_by if r.get("hgnc_id")]
    if not targets:
        return [cmd("get_server_capabilities")]
    return [cmd("get_gene", query=t) for t in targets[:2]]
