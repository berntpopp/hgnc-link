"""Argument ergonomics for MCP tools: aliases, did-you-mean, signatures.

Pure functions with no FastMCP dependency so they unit-test in isolation. The
middleware and the discovery surface both consume them, keeping one source of
truth for what a "valid argument" looks like.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from typing import Any

# Curated synonym -> canonical map, scoped to this server's parameter space. An
# alias only ever resolves to a canonical name that is a *real* parameter of the
# tool being called (see ``normalize_alias_args``), so a shared map is safe.
ARG_ALIASES: dict[str, str] = {
    # query: the universal identifier slot (symbol or HGNC id)
    "symbol": "query",
    "gene": "query",
    "gene_symbol": "query",
    "gene_name": "query",
    "hgnc": "query",
    "hgnc_id": "query",
    "id": "query",
    "identifier": "query",
    "term": "query",
    "q": "query",
    "text": "query",
    # batch
    "symbols": "queries",
    "genes": "queries",
    "ids": "queries",
    "terms": "queries",
    # cross-reference reverse lookup
    "db": "source",
    "database": "source",
    "xref": "source",
    "namespace": "source",
    "accession": "value",
    "external_id": "value",
    # gene group
    "family": "group",
    "gene_group": "group",
    "group_id": "group",
    "group_name": "group",
    # paging / verbosity
    "max": "limit",
    "count": "limit",
    "top": "limit",
    "mode": "response_mode",
    "verbosity": "response_mode",
    "databases_filter": "databases",
}


def normalize_alias_args(
    valid_params: Iterable[str], arguments: Mapping[str, Any]
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Rewrite known alias keys to their canonical parameter names.

    An alias is applied only when (a) the alias key is present, (b) the canonical
    target is a real parameter of the called tool, and (c) the canonical key is not
    already supplied explicitly. Returns ``(new_arguments, applied_pairs)``.
    """
    valid = set(valid_params)
    result = dict(arguments)
    applied: list[tuple[str, str]] = []
    for alias, canonical in ARG_ALIASES.items():
        if alias in result and canonical in valid:
            if canonical in result:
                result.pop(alias)  # explicit canonical wins; drop the alias
            else:
                result[canonical] = result.pop(alias)
                applied.append((alias, canonical))
    return result, applied


def did_you_mean(unknown: str, valid: Iterable[str]) -> str | None:
    """Best canonical suggestion for an unknown argument name, or ``None``."""
    valid_list = list(valid)
    aliased = ARG_ALIASES.get(unknown)
    if aliased is not None and aliased in valid_list:
        return aliased
    matches = difflib.get_close_matches(unknown, valid_list, n=1, cutoff=0.6)
    return matches[0] if matches else None


def tool_signature(name: str, schema: Mapping[str, Any]) -> str:
    """Render ``name(req, opt=, ...)`` from a JSON input schema."""
    props = list(schema.get("properties", {}).keys())
    required = set(schema.get("required") or [])
    parts = [p for p in props if p in required]
    parts += [f"{p}=" for p in props if p not in required]
    return f"{name}(" + ", ".join(parts) + ")"
