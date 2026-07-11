"""Build caller-visible structured fields from trusted sources ONLY.

The definitive fleet rule: NEVER copy an exception attribute or an upstream value
into a caller-visible structured field. Every value a caller sees must be one of

* a FIXED, server-authored string,
* a member of a CLOSED ENUM, or
* an identifier VALIDATED against its exact grammar (non-conforming -> dropped).

Code-point stripping alone is NOT enough: injection prose carries no forbidden
code points, so a copied exception/upstream string survives it. These validators
rebuild each structured field from validated primitives instead of copying.

This module lives at the package root (it imports only ``constants``) so BOTH the
MCP error envelope and the service-layer batch item-row builder can share it, and
so the service layer can code-point-strip a correlation key without importing the
``mcp`` package.
"""

from __future__ import annotations

import re
from typing import Any

from hgnc_link.constants import MATCH_TYPES, STATUS_VALUES

# Byte-identical to the fleet Response-Envelope v1.1 forbidden code-point set.
FORBIDDEN_CODEPOINTS = frozenset(
    {
        *range(0x0000, 0x0009),
        *range(0x000B, 0x000D),
        *range(0x000E, 0x0020),
        *range(0x007F, 0x00A0),
        0x200B,
        0x200C,
        0x200D,
        0x2060,
        0xFEFF,
        *range(0x202A, 0x202F),
        *range(0x2066, 0x206A),
    }
)

# Exact grammars. Canonical HGNC id, gene-symbol token, an allowed-value token or
# a numeric range descriptor -- all anchored and whitespace-free (prose needs
# spaces, so an instruction phrase cannot match).
_HGNC_ID_RE = re.compile(r"^HGNC:\d+$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/-]{0,63}$")
_ALLOWED_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,63}$")
_ALLOWED_RANGE_RE = re.compile(r"^\d+\.\.\d+( items)?$")

# Closed enums (from the HGNC domain constants).
_WITHDRAWN_STATUSES = frozenset(s for s in STATUS_VALUES if s != "Approved")
_MATCH_TYPES = frozenset(MATCH_TYPES)
_FIXED_WITHDRAWN_STATUS = "withdrawn"


def strip_forbidden(text: str) -> str:
    """Remove every forbidden control/zero-width/bidi/NUL code point (no length cap)."""
    return "".join(char for char in text if ord(char) not in FORBIDDEN_CODEPOINTS)


def is_canonical_hgnc_id(value: Any) -> bool:
    """True only for a canonical ``HGNC:<digits>`` identifier."""
    return isinstance(value, str) and _HGNC_ID_RE.match(value) is not None


def safe_hgnc_id(value: Any) -> str | None:
    """Return ``value`` if it is a canonical HGNC id, else ``None``."""
    return value if is_canonical_hgnc_id(value) else None


def safe_symbol(value: Any) -> str | None:
    """Return ``value`` if it matches the gene-symbol grammar, else ``None``."""
    return value if isinstance(value, str) and _SYMBOL_RE.match(value) else None


def safe_symbol_type(value: Any) -> str | None:
    """Return ``value`` if it is a known match-type enum member, else ``None``."""
    return value if value in _MATCH_TYPES else None


def safe_withdrawn_status(value: Any) -> str:
    """Return ``value`` only if it is a known withdrawal status, else a fixed word."""
    return value if value in _WITHDRAWN_STATUSES else _FIXED_WITHDRAWN_STATUS


def safe_allowed_value(value: Any) -> bool:
    """True for an allowed-value token / range descriptor (no prose, no whitespace)."""
    return isinstance(value, str) and bool(
        _ALLOWED_TOKEN_RE.match(value) or _ALLOWED_RANGE_RE.match(value)
    )


def safe_allowed_values(values: Any) -> list[str]:
    """Filter a list to entries matching the allowed-value grammar; drop the rest."""
    if not isinstance(values, list):
        return []
    return [v for v in values if safe_allowed_value(v)]


def safe_candidate(candidate: Any) -> dict[str, Any] | None:
    """Rebuild a candidate from validated identifiers only; ``None`` if it has no valid id.

    Keeps a canonical ``hgnc_id`` (required), a grammar-valid ``symbol``, and an
    enum ``symbol_type``. The free-text ``name`` (and any other field) is DROPPED
    -- it cannot be grammar-validated, so it is never surfaced.
    """
    if not isinstance(candidate, dict):
        return None
    hid = safe_hgnc_id(candidate.get("hgnc_id"))
    if hid is None:
        return None
    out: dict[str, Any] = {"hgnc_id": hid}
    symbol = safe_symbol(candidate.get("symbol"))
    if symbol is not None:
        out["symbol"] = symbol
    symbol_type = safe_symbol_type(candidate.get("symbol_type"))
    if symbol_type is not None:
        out["symbol_type"] = symbol_type
    return out


def safe_candidates(candidates: Any) -> list[dict[str, Any]]:
    """Validate every candidate; drop those with no canonical HGNC id."""
    if not isinstance(candidates, list):
        return []
    return [c for c in (safe_candidate(x) for x in candidates) if c is not None]


def safe_replaced_by(items: Any) -> list[dict[str, Any]]:
    """Keep successor records with a canonical HGNC id (+ optional valid symbol)."""
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        hid = safe_hgnc_id(item.get("hgnc_id"))
        if hid is None:
            continue
        entry: dict[str, Any] = {"hgnc_id": hid}
        symbol = safe_symbol(item.get("symbol"))
        if symbol is not None:
            entry["symbol"] = symbol
        out.append(entry)
    return out
