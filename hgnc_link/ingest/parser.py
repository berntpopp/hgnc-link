"""Parse HGNC bulk dumps into normalized records and derived index rows.

The HGNC complete-set JSON (``response.docs[]``) and the REST ``fetch`` payloads
share identical field names/shapes, so :func:`normalize_doc` accepts either.
Multi-value fields arrive as JSON arrays (dump/REST) or pipe-delimited strings
(TSV); both are coerced to clean string lists. ``withdrawn.txt`` is parsed
separately into retired-ID -> successor redirects.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from hgnc_link.constants import LIST_FIELDS, SCALAR_FIELDS, XREF_FIELDS


def _as_list(value: Any) -> list[str]:
    """Coerce a scalar / list / pipe-delimited string into a clean string list."""
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(v).strip() for v in value]
    elif isinstance(value, str):
        items = [tok.strip() for tok in value.split("|")]
    else:
        items = [str(value).strip()]
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _scalar(value: Any) -> str | None:
    """Coerce a value to a trimmed scalar string, or ``None`` when empty."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw HGNC record into scalar + list fields.

    Returns a dict with every :data:`SCALAR_FIELDS` key (scalar or ``None``) and
    every :data:`LIST_FIELDS` key (a possibly-empty list of strings).
    """
    record: dict[str, Any] = {}
    for field in SCALAR_FIELDS:
        record[field] = _scalar(doc.get(field))
    for field in LIST_FIELDS:
        record[field] = _as_list(doc.get(field))
    return record


def load_complete_set(
    source: str | Path | dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load HGNC ``docs`` from a JSON file path, a parsed object, or a docs list."""
    if isinstance(source, list):
        docs = source
    else:
        if isinstance(source, dict):
            data = source
        else:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        docs = data.get("response", {}).get("docs", data.get("docs", []))
    return [d for d in docs if isinstance(d, dict) and d.get("hgnc_id")]


def iter_normalized_genes(
    source: str | Path | dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return normalized gene records for every doc in the complete set."""
    return [normalize_doc(doc) for doc in load_complete_set(source)]


def symbol_lookup_rows(gene: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Exploded ``(lookup_symbol_upper, hgnc_id, symbol_type)`` rows for a gene.

    ``symbol_type`` is ``current`` for the approved symbol, ``previous`` for each
    ``prev_symbol``, and ``alias`` for each ``alias_symbol``. Current wins on
    collision (handled by insert ordering in the builder).
    """
    hgnc_id = gene["hgnc_id"]
    rows: list[tuple[str, str, str]] = []
    symbol = gene.get("symbol")
    if symbol:
        rows.append((symbol.upper(), hgnc_id, "current"))
    for prev in gene.get("prev_symbol", []):
        rows.append((prev.upper(), hgnc_id, "previous"))
    for alias in gene.get("alias_symbol", []):
        rows.append((alias.upper(), hgnc_id, "alias"))
    return rows


def xref_rows(gene: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """Exploded ``(source, value_upper, value, hgnc_id)`` rows for reverse lookup."""
    hgnc_id = gene["hgnc_id"]
    rows: list[tuple[str, str, str, str]] = []
    for field, _label in XREF_FIELDS:
        value = gene.get(field)
        values = value if isinstance(value, list) else ([value] if value else [])
        for raw in values:
            text = str(raw).strip()
            if text:
                rows.append((field, text.upper(), text, hgnc_id))
    return rows


def group_rows(gene: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Exploded ``(group_id, group_name, hgnc_id)`` rows for family browse."""
    hgnc_id = gene["hgnc_id"]
    ids = gene.get("gene_group_id", [])
    names = gene.get("gene_group", [])
    rows: list[tuple[str, str, str]] = []
    for idx, gid in enumerate(ids):
        name = names[idx] if idx < len(names) else ""
        rows.append((str(gid).strip(), str(name).strip(), hgnc_id))
    return rows


def parse_withdrawn(text: str) -> list[dict[str, Any]]:
    """Parse ``withdrawn.txt`` into retired-ID -> successor redirect records.

    Columns: ``HGNC_ID``, ``STATUS`` (``Entry Withdrawn`` / ``Merged/Split``),
    ``WITHDRAWN_SYMBOL``, ``MERGED_INTO_REPORT(S)`` (``HGNC_ID|SYMBOL|STATUS``,
    comma-separated when multiple). Returns dicts with a parsed ``replaced_by``
    list of ``{hgnc_id, symbol, status}``.
    """
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    rows = list(reader)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row or row[0].strip().upper() in ("HGNC_ID", ""):
            continue
        hgnc_id = row[0].strip()
        status = row[1].strip() if len(row) > 1 else ""
        symbol = row[2].strip() if len(row) > 2 else ""
        merged_raw = row[3].strip() if len(row) > 3 else ""
        replaced_by: list[dict[str, str]] = []
        if merged_raw:
            for part in merged_raw.split(","):
                fields = [f.strip() for f in part.split("|")]
                if len(fields) >= 2 and fields[0]:
                    replaced_by.append(
                        {
                            "hgnc_id": fields[0],
                            "symbol": fields[1],
                            "status": fields[2] if len(fields) > 2 else "",
                        }
                    )
        out.append(
            {
                "hgnc_id": hgnc_id,
                "status": status,
                "withdrawn_symbol": symbol,
                "replaced_by": replaced_by,
            }
        )
    return out
