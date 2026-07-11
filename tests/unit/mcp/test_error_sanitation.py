"""Unit contracts for the defensive error-message sanitizer.

``sanitize_message`` is the code-point backstop applied to every caller-visible
error/message string; ``safe_field_name`` additionally hard-caps a caller-supplied
argument name. Neither strips injection *prose* -- that is severed to fixed
strings at the source (see ``test_error_leak_fencing.py`` for the wiring proof).
"""

from __future__ import annotations

from hgnc_link.mcp._sanitize import (
    MAX_FIELD_NAME_CHARS,
    MAX_MESSAGE_CHARS,
    safe_field_name,
    sanitize_message,
)

# NUL + zero-width joiner + BOM + right-to-left override interleaved with prose.
_DIRTY = "boom\x00 zwj‍ bom﻿ rtl‮ tail"
_FORBIDDEN = ("\x00", "‍", "﻿", "‮")


def test_strips_nul_zero_width_bom_and_bidi() -> None:
    clean = sanitize_message(_DIRTY)
    for bad in _FORBIDDEN:
        assert bad not in clean
    # ordinary prose around the stripped code points survives
    assert "boom" in clean
    assert "tail" in clean


def test_preserves_ordinary_prose_verbatim() -> None:
    ordinary = "No HGNC record matches 'BRAF'."
    assert sanitize_message(ordinary) == ordinary


def test_preserves_tab_and_newline() -> None:
    # tab/newline/CR are deliberately NOT in the forbidden set (fleet parity).
    assert sanitize_message("a\tb\nc\rd") == "a\tb\nc\rd"


def test_length_capped_at_280() -> None:
    assert MAX_MESSAGE_CHARS == 280
    assert len(sanitize_message("x" * 5000)) == 280


def test_safe_field_name_preserves_normal_identifiers() -> None:
    for name in ("query", "response_mode", "respons_mode", "queries", "databases"):
        assert safe_field_name(name) == name


def test_safe_field_name_strips_codepoints_and_caps_length() -> None:
    assert "‮" not in safe_field_name("field‮name\x00")
    assert len(safe_field_name("a" * 500)) == MAX_FIELD_NAME_CHARS
