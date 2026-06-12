"""Response-mode projection for HGNC payloads.

``standard`` / ``full`` are the identity (the complete record). ``compact``
(the default) drops dates, raw provenance, and rarely-needed name variants.
``minimal`` keeps only the identity + locus + the two anchor cross-references.
"""

from __future__ import annotations

from typing import Any

RESPONSE_MODES: tuple[str, ...] = ("minimal", "compact", "standard", "full")
DEFAULT_RESPONSE_MODE = "compact"

# Fields dropped from a full gene record in compact mode (verbose / provenance).
_GENE_DROP_COMPACT: frozenset[str] = frozenset(
    {
        "date_approved_reserved",
        "date_symbol_changed",
        "date_name_changed",
        "date_modified",
        "uuid",
        "location_sortable",
        "lsdb",
        "ena",
        "pubmed_id",
        "rna_central_id",
        "agr",
        "cosmic",
        "orphanet",
        "alias_name",
        "prev_name",
    }
)

# Fields kept in minimal mode (everything else is dropped from the gene record).
_GENE_KEEP_MINIMAL: frozenset[str] = frozenset(
    {
        "query",
        "requested_query",
        "hgnc_id",
        "symbol",
        "name",
        "status",
        "locus_group",
        "locus_type",
        "location",
        "match_type",
        "entrez_id",
        "ensembl_gene_id",
        "_meta",
    }
)

_PRESERVE_KEYS: frozenset[str] = frozenset({"_meta", "success"})


def shape_gene(record: dict[str, Any], mode: str) -> dict[str, Any]:
    """Project a flat gene-record payload to the requested verbosity."""
    if mode in ("standard", "full"):
        return record
    if mode == "minimal":
        return {k: v for k, v in record.items() if k in _GENE_KEEP_MINIMAL}
    # compact: drop verbose fields, and drop empty list/None values for brevity.
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key in _GENE_DROP_COMPACT and key not in _PRESERVE_KEYS:
            continue
        if key not in _PRESERVE_KEYS and (value is None or value == [] or value == ""):
            continue
        out[key] = value
    return out


def shape_summary(summary: dict[str, Any], mode: str) -> dict[str, Any]:
    """Project a search/resolve summary row to the requested verbosity."""
    if mode == "minimal":
        keep = {"hgnc_id", "symbol", "match_type", "symbol_type"}
        return {k: v for k, v in summary.items() if k in keep}
    if mode in ("standard", "full"):
        return summary
    # compact: drop null/empty.
    return {k: v for k, v in summary.items() if v is not None and v != ""}
