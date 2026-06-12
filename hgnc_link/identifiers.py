"""HGNC identifier helpers: normalize the ``HGNC:NNNN`` <-> ``NNNN`` forms.

Every studied consumer (sysndd, kidney-genetics) hand-rolls the ``HGNC:`` strip
and re-add; centralising it here means callers never parse identifiers
themselves.
"""

from __future__ import annotations

import re

_HGNC_ID_RE = re.compile(r"^HGNC:(\d+)$", re.IGNORECASE)
_BARE_ID_RE = re.compile(r"^\d+$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/-]{0,63}$")


def normalize_hgnc_id(value: str) -> str | None:
    """Return the canonical ``HGNC:NNNN`` form for an ID, or ``None`` if not one.

    Accepts ``HGNC:1100``, ``hgnc:1100``, and the bare numeric ``1100`` forms.
    """
    text = (value or "").strip()
    match = _HGNC_ID_RE.match(text)
    if match:
        return f"HGNC:{match.group(1)}"
    if _BARE_ID_RE.match(text):
        return f"HGNC:{text}"
    return None


def looks_like_hgnc_id(value: str) -> bool:
    """True when ``value`` is an HGNC ID in either accepted form."""
    return normalize_hgnc_id(value) is not None


def looks_like_symbol(value: str) -> bool:
    """True for a plausible gene-symbol shape (and not an HGNC ID)."""
    text = (value or "").strip()
    if not text or looks_like_hgnc_id(text):
        return False
    return bool(_SYMBOL_RE.match(text))
