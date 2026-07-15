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


# pydantic value-error codes that mean "wrong TYPE", mapped to a human phrase that
# names the expected type. A type error rendered as a range error ("must be between 1
# and 200" for limit='ten') misleads the model into thinking its value is out of range
# rather than the wrong type (issue #26 D5).
_TYPE_ERROR_PHRASE: dict[str, str] = {
    "int_parsing": "must be an integer",
    "int_type": "must be an integer",
    "float_parsing": "must be a number",
    "float_type": "must be a number",
    "bool_parsing": "must be true or false",
    "bool_type": "must be true or false",
    "string_type": "must be a string",
    "list_type": "must be an array",
}


def describe_constraints(
    field_schema: Mapping[str, Any], error_type: str | None = None
) -> tuple[list[str], str] | None:
    """Surface a field's enum/range for an invalid-*value* error.

    Returns ``(allowed_values, human_phrase)`` for an ``enum`` or a bounded
    numeric field (digging through ``anyOf``/``allOf``/``oneOf``), or ``None`` for
    a field with no value constraint (so the caller falls back to a name error).

    When ``error_type`` names a pydantic TYPE error, the human phrase names the
    expected type ("must be an integer") instead of the range, while
    ``allowed_values`` still carries the range/enum for guidance.
    """
    type_phrase = _TYPE_ERROR_PHRASE.get(error_type or "")

    def _finish(allowed: list[str], human: str) -> tuple[list[str], str]:
        # A type error names the TYPE; the range/enum still rides along in allowed.
        return allowed, type_phrase or human

    nodes: list[Any] = [field_schema]
    for key in ("anyOf", "allOf", "oneOf"):
        nodes.extend(field_schema.get(key, []))
    for node in nodes:
        if isinstance(node, Mapping) and node.get("enum"):
            vals = [str(v) for v in node["enum"]]
            return _finish(vals, "must be one of: " + ", ".join(vals))
    lo: Any = None
    hi: Any = None
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        lo = node.get("minimum", node.get("exclusiveMinimum", lo))
        hi = node.get("maximum", node.get("exclusiveMaximum", hi))
    if lo is not None or hi is not None:
        lo_s = str(int(lo)) if lo is not None else "?"
        hi_s = str(int(hi)) if hi is not None else "?"
        return _finish([f"{lo_s}..{hi_s}"], f"must be between {lo_s} and {hi_s}")
    min_items: Any = None
    max_items: Any = None
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        min_items = node.get("minItems", min_items)
        max_items = node.get("maxItems", max_items)
    if min_items is not None or max_items is not None:
        lo_s = str(int(min_items)) if min_items is not None else "0"
        hi_s = str(int(max_items)) if max_items is not None else "?"
        return _finish([f"{lo_s}..{hi_s} items"], f"must have between {lo_s} and {hi_s} items")
    # No enum/range/items constraint, but still a plain type error: name the type.
    if type_phrase:
        return [], type_phrase
    return None


def tool_signature(name: str, schema: Mapping[str, Any]) -> str:
    """Render ``name(req, opt=, ...)`` from a JSON input schema."""
    props = list(schema.get("properties", {}).keys())
    required = set(schema.get("required") or [])
    parts = [p for p in props if p in required]
    parts += [f"{p}=" for p in props if p not in required]
    return f"{name}(" + ", ".join(parts) + ")"
