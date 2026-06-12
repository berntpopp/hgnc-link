"""JSON output schemas for the typed MCP tools (MCP structured output).

The schemas are deliberately **permissive** (``additionalProperties: true``,
nothing ``required``) because ``response_mode`` projects fields out and the error
envelope is returned by the same tool body and must also validate.
"""

from __future__ import annotations

from typing import Any

_META = {"type": "object", "additionalProperties": True}


def _envelope(**properties: Any) -> dict[str, Any]:
    """A permissive object schema carrying the common envelope keys + extras."""
    props: dict[str, Any] = {
        "success": {"type": "boolean"},
        "_meta": _META,
        "error_code": {"type": "string"},
        "message": {"type": "string"},
        "retryable": {"type": "boolean"},
        "recovery_action": {"type": "string"},
        "field": {"type": "string"},
        "allowed_values": {"type": "array"},
        "hint": {"type": "string"},
        "obsolete": {"type": "boolean"},
        "replaced_by": {"type": "array"},
        "candidates": {"type": "array"},
        **properties,
    }
    return {"type": "object", "additionalProperties": True, "properties": props}


_STR = {"type": "string"}
_STR_NULL = {"type": ["string", "null"]}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}
_ARR = {"type": "array"}
_OBJ = {"type": "object", "additionalProperties": True}

CAPABILITIES_SCHEMA = _envelope(
    server=_STR,
    server_version=_STR,
    hgnc_release=_STR,
    tools=_ARR,
    response_modes=_ARR,
    error_codes=_ARR,
)

DIAGNOSTICS_SCHEMA = _envelope(
    data_available=_BOOL,
    release=_STR,
    gene_count=_INT,
    withdrawn_count=_INT,
    symbol_lookup_rows=_INT,
    source_last_modified=_STR,
    built_utc=_STR,
    live_fallback_enabled=_BOOL,
)

RESOLVE_SCHEMA = _envelope(
    query=_STR,
    hgnc_id=_STR_NULL,
    approved_symbol=_STR_NULL,
    name=_STR_NULL,
    status=_STR_NULL,
    locus_type=_STR_NULL,
    location=_STR_NULL,
    match_type=_STR_NULL,
    ambiguous=_BOOL,
    candidate_count=_INT,
    candidates=_ARR,
    other_matches=_ARR,
    note=_STR,
)

RESOLVE_BATCH_SCHEMA = _envelope(
    query_count=_INT,
    resolved_count=_INT,
    unresolved_count=_INT,
    results=_ARR,
)

GENE_SCHEMA = _envelope(
    hgnc_id=_STR,
    symbol=_STR,
    name=_STR,
    status=_STR,
    locus_group=_STR,
    locus_type=_STR,
    location=_STR,
    match_type=_STR,
    requested_query=_STR,
    alias_symbol=_ARR,
    prev_symbol=_ARR,
    gene_group=_ARR,
    gene_group_id=_ARR,
    entrez_id=_STR,
    ensembl_gene_id=_STR,
    uniprot_ids=_ARR,
    refseq_accession=_ARR,
    mane_select=_ARR,
    omim_id=_ARR,
)

SEARCH_SCHEMA = _envelope(query=_STR, count=_INT, results=_ARR)

CROSS_REFERENCES_SCHEMA = _envelope(
    hgnc_id=_STR,
    symbol=_STR,
    match_type=_STR,
    database_count=_INT,
    cross_references=_OBJ,
)

XREF_LOOKUP_SCHEMA = _envelope(
    source=_STR,
    source_label=_STR,
    value=_STR,
    count=_INT,
    results=_ARR,
)

GENE_GROUP_SCHEMA = _envelope(
    group_id=_STR,
    group_name=_STR,
    member_count=_INT,
    returned=_INT,
    offset=_INT,
    limit=_INT,
    truncated=_BOOL,
    next_offset={"type": ["integer", "null"]},
    members=_ARR,
    ambiguous=_BOOL,
    match_count=_INT,
    matches=_ARR,
    score=_NUM,
)
