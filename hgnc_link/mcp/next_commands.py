"""Builders for `_meta.next_commands` entries: `{tool, arguments}` steps."""

from __future__ import annotations

from typing import Any

from hgnc_link.identifiers import infer_xref_source, looks_like_hgnc_id, looks_like_symbol

_GENE_TOOLS = {
    "resolve_symbol",
    "get_gene",
    "get_gene_cross_references",
    "resolve_gene_by_xref",
    "get_gene_group",
}


def cmd(tool: str, **arguments: Any) -> dict[str, Any]:
    """One ready-to-call next step."""
    return {"tool": tool, "arguments": arguments}


def default_error_next_commands(
    tool: str, error_code: str, arguments: dict[str, Any]
) -> list[dict[str, Any]]:
    """A sensible recovery step for any error lacking an explicit fallback.

    The caller's ``query`` is FREE-FORM (it can carry injection prose that survives
    code-point stripping), so it is echoed into a recovery ``next_command`` ONLY
    when it passes the fully-anchored, space-free symbol grammar (``looks_like_symbol``
    / ``looks_like_hgnc_id``). A non-conforming (e.g. instruction-shaped) value is
    never placed into a recovery argument; the caller is steered to capabilities.
    """
    if tool in ("resolve_symbol", "get_gene"):
        value = str(arguments.get("query", ""))
        if value and looks_like_symbol(value):
            # infer_xref_source matches on a prefix, so it is gated behind the
            # anchored symbol grammar above (which forbids whitespace/prose).
            source = infer_xref_source(value)
            if source:
                return [
                    cmd("resolve_gene_by_xref", source=source, value=value),
                    cmd("search_genes", query=value),
                ]
            return [cmd("search_genes", query=value), cmd("get_server_capabilities")]
    if error_code == "data_unavailable":
        return [cmd("get_hgnc_diagnostics")]
    return [cmd("get_server_capabilities")]


def _search_or_capabilities(query: str) -> list[dict[str, Any]]:
    """Echo ``query`` into a search_genes step ONLY when it passes the strict,
    space-free symbol grammar; a free-form value (which could carry injection
    prose) is never placed into a next_command argument."""
    if query and looks_like_symbol(query):
        return [cmd("search_genes", query=query)]
    return [cmd("get_server_capabilities")]


def after_resolve(resolution: dict[str, Any]) -> list[dict[str, Any]]:
    """After resolve_symbol: drill into the resolved gene, or disambiguate."""
    if resolution.get("ambiguous"):
        cands = resolution.get("candidates", [])[:3]
        chain = [
            cmd("get_gene", query=c["hgnc_id"])
            for c in cands
            if isinstance(c.get("hgnc_id"), str) and looks_like_hgnc_id(c["hgnc_id"])
        ]
        return chain or _search_or_capabilities(str(resolution.get("query", "")))
    hgnc_id = resolution.get("hgnc_id")
    if not hgnc_id:
        return _search_or_capabilities(str(resolution.get("query", "")))
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
    """After search_genes: fetch the top hit, or point home if empty.

    On an empty result the search ``query`` is echoed into a resolve_symbol retry
    ONLY when it is symbol-shaped (resolve_symbol needs an exact symbol/id anyway);
    a free-form descriptive query is not placed into the next_command.
    """
    if not hits:
        if looks_like_symbol(query):
            return [cmd("resolve_symbol", query=query), cmd("get_server_capabilities")]
        return [cmd("get_server_capabilities")]
    top = hits[0].get("hgnc_id")
    return [cmd("get_gene", query=top)] if top else [cmd("get_server_capabilities")]


def after_xref(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """After resolve_gene_by_xref: fetch the first matched gene."""
    if not results:
        return [cmd("get_server_capabilities")]
    first = results[0].get("hgnc_id")
    return [cmd("get_gene", query=first)] if first else [cmd("get_server_capabilities")]


def after_group(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """After get_gene_group: drill into the first member, then the next page."""
    if payload.get("ambiguous"):
        matches = payload.get("matches", [])[:2]
        return [
            cmd("get_gene_group", group=str(m["group_id"])) for m in matches if m.get("group_id")
        ]
    chain: list[dict[str, Any]] = []
    members = payload.get("members", [])
    if members and members[0].get("hgnc_id"):
        chain.append(cmd("get_gene", query=members[0]["hgnc_id"]))
    if payload.get("truncated") and payload.get("next_offset") is not None:
        chain.append(
            cmd(
                "get_gene_group",
                group=str(payload.get("group_id")),
                offset=payload["next_offset"],
                limit=payload.get("limit", 200),
            )
        )
    return chain or [cmd("get_server_capabilities")]


def withdrawn_recovery(replaced_by: list[dict[str, str]]) -> list[dict[str, Any]]:
    """After a withdrawn-entry error: chain to the live successor record(s).

    Only successor ids that pass the strict HGNC-id grammar are echoed into a
    recovery ``get_gene`` argument (the replacement records are curated, but the
    grammar check keeps any non-conforming value out of an executable next step).
    """
    targets = [
        r["hgnc_id"]
        for r in replaced_by
        if isinstance(r.get("hgnc_id"), str) and looks_like_hgnc_id(r["hgnc_id"])
    ]
    if not targets:
        return [cmd("get_server_capabilities")]
    return [cmd("get_gene", query=t) for t in targets[:2]]
