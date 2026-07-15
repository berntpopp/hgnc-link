"""Pure helpers for cross-reference filtering and identifier validation.

Split out of :mod:`hgnc_link.services.hgnc_service` to keep that module within the
per-file line budget; these are stateless functions with no repository dependency.
"""

from __future__ import annotations

import difflib

from hgnc_link.constants import (
    NUMERIC_XREF_FIELDS,
    XREF_FIELDS,
    XREF_FILTER_ALIASES,
    XREF_TIER_COMPACT,
    XREF_TIER_MINIMAL,
)
from hgnc_link.exceptions import InvalidInputError
from hgnc_link.identifiers import looks_like_malformed_hgnc_id


def validate_xref_value(field: str, value: str) -> None:
    """Reject a value whose shape cannot match its source (issue #26 review).

    A numeric-id source (entrez_id/omim_id) requires a bare integer: ``673.99`` is a
    malformed id (``invalid_input``), NOT a version-stripped match on ``673`` and NOT
    a silent ``not_found``.
    """
    if field in NUMERIC_XREF_FIELDS and not value.isdigit():
        raise InvalidInputError(
            f"Malformed {field}: expected digits only.",
            field="value",
            hint=f"{field} is a numeric id, e.g. 673.",
        )


def reject_malformed_hgnc_id(raw: str) -> None:
    """Raise ``invalid_input`` for a value that attempts the ``HGNC:`` form but is invalid.

    ``HGNC:abc`` is a botched identifier, not an unknown symbol: answering it with
    ``not_found`` makes a malformed id indistinguishable from a gene that does not
    exist (issue #26 D5). ``allowed`` names the expected shape.
    """
    if looks_like_malformed_hgnc_id(raw):
        raise InvalidInputError(
            "Malformed HGNC id.",
            field="query",
            # A concrete, grammar-valid example of the expected shape (a pattern like
            # 'HGNC:<digits>' would be stripped by the allowed-value grammar).
            allowed=["HGNC:1100"],
            hint="An HGNC id is 'HGNC:' followed by digits, e.g. HGNC:1100.",
        )


def resolve_xref_filter(databases: list[str] | None) -> set[str] | None:
    """Normalize the ``databases`` filter to canonical field keys.

    Friendly labels/synonyms map to the field key; an unrecognized key raises
    ``invalid_input`` with a did-you-mean. ``None`` means "no filter".
    """
    if not databases:
        return None
    resolved: set[str] = set()
    unknown: list[str] = []
    for db in databases:
        canon = XREF_FILTER_ALIASES.get((db or "").strip().lower())
        if canon is None:
            unknown.append(db)
        else:
            resolved.add(canon)
    if unknown:
        allowed = [field for field, _ in XREF_FIELDS]
        guess = difflib.get_close_matches(
            (unknown[0] or "").strip().lower(), list(XREF_FILTER_ALIASES), n=1, cutoff=0.6
        )
        # The suggestion is a canonical field key from a CLOSED server-controlled set
        # (XREF_FILTER_ALIASES values), so it is safe to surface as the structured
        # `did_you_mean` field the tool description promises (issue #26 D4).
        did_you_mean = [XREF_FILTER_ALIASES[guess[0]]] if guess else None
        raise InvalidInputError(
            f"Unknown cross-reference database(s): {', '.join(unknown)}.",
            field="databases",
            allowed=allowed,
            hint="Use a field key or label, e.g. ensembl, uniprot, mane, omim.",
            did_you_mean=did_you_mean,
        )
    return resolved


def xref_tier_fields(mode: str) -> set[str] | None:
    """The default xref field whitelist for a verbosity tier (``None`` = all populated)."""
    if mode == "minimal":
        return set(XREF_TIER_MINIMAL)
    if mode == "compact":
        return set(XREF_TIER_COMPACT)
    return None  # standard / full: every populated field
