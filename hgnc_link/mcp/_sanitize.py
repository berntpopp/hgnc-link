"""Defensive sanitation for caller-visible MCP error / message strings.

hgnc-link is a ``no-untrusted-text`` backend: every tool returns curated HGNC
nomenclature, so there is no primary ``untrusted_content.py`` fence module to
reuse. This tiny helper is the defence-in-depth backstop for the *error* path:
it strips the fleet Response-Envelope v1.1 forbidden control / zero-width /
bidirectional / NUL code points from every caller-visible ``message`` / ``error``
string, so a hostile upstream body or a caller-influenced identifier echoed into
an error frame can never smuggle those code points into the model's context.

``sanitize_message`` strips code points but NOT prose -- attacker-influenceable
prose (an upstream response body, the ``str(exc)`` of an upstream/API error, or a
rejected input value) is additionally *severed* to a fixed, server-authored
string at its source (the API client, the batch item-row builder, the repository
open/read errors, and the argument-validation reason map). This module only ever
runs on strings whose prose is already trusted/server-authored.
"""

from __future__ import annotations

# Byte-identical to the fleet Response-Envelope v1.1 forbidden code-point set (the
# same set the module-fenced backends' ``untrusted_content.py`` removes): C0/C1
# controls except tab/newline/CR, zero-width joiners/space/BOM, and the bidi
# embedding/override/isolate controls.
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

MAX_MESSAGE_CHARS = 280
MAX_FIELD_NAME_CHARS = 64


def sanitize_message(text: str) -> str:
    """Strip forbidden control/zero-width/bidi/NUL code points and length-cap.

    Applied to every caller-visible message/error string so a hostile upstream
    (or a caller-influenced 4xx/5xx body) can never smuggle control, zero-width,
    bidirectional, or NUL code points into an error frame. Caller-visible
    messages are server-authored guidance data; attacker-influenceable prose is
    additionally kept out of them at the source (severed to fixed strings), so
    this backstop only has to remove the forbidden code points.
    """
    clean = "".join(char for char in text if ord(char) not in FORBIDDEN_CODEPOINTS)
    return clean[:MAX_MESSAGE_CHARS]


def safe_field_name(name: str) -> str:
    """Return a caller-supplied argument NAME safe to echo in an error frame.

    The invalid / unknown argument name is caller-controlled, so strip the
    forbidden code points and hard-cap the length (an argument name is a
    low-cardinality identifier) before it is echoed into a message or the
    ``field`` key of an ``invalid_input`` envelope.
    """
    return sanitize_message(name)[:MAX_FIELD_NAME_CHARS]
