"""Builders for `_meta.next_commands` entries: `{tool, arguments}` steps.

Every identifier echoed into a next_command is validated first: an ``hgnc_id`` must
be canonical (``^HGNC:\\d+$``) and a caller ``query`` must pass the anchored,
space-free symbol grammar. A service-returned or caller value that does not conform
(e.g. a hostile upstream id, or an instruction-shaped query) is dropped rather than
placed into an executable recovery step.
"""

from __future__ import annotations

from typing import Any

from hgnc_link.identifiers import infer_xref_source, looks_like_symbol
from hgnc_link.safe_fields import is_canonical_hgnc_id


def cmd(tool: str, **arguments: Any) -> dict[str, Any]:
    """One ready-to-call next step."""
    return {"tool": tool, "arguments": arguments}


def _gene_steps(*hgnc_ids: Any) -> list[dict[str, Any]]:
    """get_gene steps for each canonical HGNC id (non-conforming ids dropped)."""
    return [cmd("get_gene", query=hid) for hid in hgnc_ids if is_canonical_hgnc_id(hid)]


def default_error_next_commands(
    tool: str, error_code: str, arguments: dict[str, Any]
) -> list[dict[str, Any]]:
    """A sensible recovery step for any error lacking an explicit fallback.

    The caller's ``query`` is FREE-FORM (it can carry injection prose that survives
    code-point stripping), so it is echoed into a recovery ``next_command`` ONLY
    when it passes the fully-anchored, space-free symbol grammar. A non-conforming
    (e.g. instruction-shaped) value is never placed into a recovery argument.
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
        chain = _gene_steps(*(c.get("hgnc_id") for c in cands))
        return chain or _search_or_capabilities(str(resolution.get("query", "")))
    hgnc_id = resolution.get("hgnc_id")
    if not is_canonical_hgnc_id(hgnc_id):
        return _search_or_capabilities(str(resolution.get("query", "")))
    return [
        cmd("get_gene", query=hgnc_id),
        cmd("get_gene_cross_references", query=hgnc_id),
    ]


def after_get_gene(gene: dict[str, Any]) -> list[dict[str, Any]]:
    """After get_gene: offer cross-references and (if any) the gene's group."""
    hgnc_id = gene.get("hgnc_id")
    if not is_canonical_hgnc_id(hgnc_id):
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
    return _gene_steps(top) or [cmd("get_server_capabilities")]


def after_xref(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """After resolve_gene_by_xref: fetch the first matched gene."""
    if not results:
        return [cmd("get_server_capabilities")]
    return _gene_steps(results[0].get("hgnc_id")) or [cmd("get_server_capabilities")]


def after_group(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """After get_gene_group: drill into the first member, then the next page."""
    if payload.get("ambiguous"):
        matches = payload.get("matches", [])[:2]
        return [
            cmd("get_gene_group", group=str(m["group_id"])) for m in matches if m.get("group_id")
        ]
    chain: list[dict[str, Any]] = []
    members = payload.get("members", [])
    if members:
        chain.extend(_gene_steps(members[0].get("hgnc_id")))
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

    Only successor ids that pass the strict canonical HGNC-id grammar are echoed
    into a recovery ``get_gene`` argument; a non-conforming value is dropped.
    """
    targets = _gene_steps(*(r.get("hgnc_id") for r in replaced_by))
    if not targets:
        return [cmd("get_server_capabilities")]
    return targets[:2]
