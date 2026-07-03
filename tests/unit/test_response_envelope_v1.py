"""Locks the ratified GeneFoundry Response-Envelope Standard v1 (flat-banner
contract) at this backend's MCP wrapper boundary (``hgnc_link.mcp.envelope``).

Adapted from clingen-link (fleet exemplar, PR #20:
https://github.com/berntpopp/clingen-link/pull/20) for this repo's actual
envelope implementation.

Ground truth vs the task-brief assumption: hgnc-link does NOT use a separate
``mcp/errors.py`` + ``build_meta`` pattern. Both success ``_meta`` injection
and the flat error envelope are built inline in ``hgnc_link/mcp/envelope.py``
via :func:`hgnc_link.mcp.envelope.run_mcp_tool` (success path) and the
module-private ``_error_envelope`` (failure path, exercised here indirectly
through ``run_mcp_tool`` -- the only way a tool body's exception becomes a
client-facing envelope). This is architecturally the *same* run_mcp_tool
pattern as clingen-link, not the build_meta pattern described in the task
brief; there is nothing named ``build_meta`` anywhere in this repository.

Fleet decision (2026-07-03): ``_meta.unsafe_for_clinical_use`` must appear on
EVERY tool response -- success AND error, at all response_modes -- not once
via ``get_server_capabilities``. hgnc-link now stamps that key on every
per-call ``_meta`` dict (see ``mcp/envelope.py``); the static
``research_use_only`` / ``research_use_notice`` fields in
``get_server_capabilities`` remain the source of the full disclaimer text and
citation/release provenance, which are still declared once to conserve
tokens -- see ``provenance_policy`` / ``per_call_meta`` in
``mcp/capabilities.py``.
"""

from __future__ import annotations

from hgnc_link.exceptions import NotFoundError, RateLimitError
from hgnc_link.mcp.capabilities import build_capabilities
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool


async def test_success_envelope_is_flat_with_lean_meta() -> None:
    """SUCCESS: {"success": True, <payload>, "_meta": {...}}, flat (no nesting).

    hgnc-link's per-call ``_meta`` carries ``tool``, ``request_id``,
    ``unsafe_for_clinical_use`` (plus optional ``next_commands`` /
    ``argument_aliases_applied`` when a tool body supplies them). See module
    docstring.
    """

    async def call() -> dict[str, object]:
        return {"hgnc_id": "HGNC:1097", "symbol": "BRAF"}

    result = await run_mcp_tool("get_gene", call, context=McpErrorContext("get_gene"))

    assert result["success"] is True
    assert result["hgnc_id"] == "HGNC:1097"
    assert result["symbol"] == "BRAF"
    assert result["_meta"]["tool"] == "get_gene"
    assert isinstance(result["_meta"]["request_id"], str)
    assert result["_meta"]["request_id"]
    # Fleet Response-Envelope Standard v1 (2026-07-03): every success envelope
    # stamps the clinical-safety disclaimer per-call.
    assert result["_meta"]["unsafe_for_clinical_use"] is True


async def test_error_envelope_is_flat_never_nested_and_never_raises() -> None:
    """FAILURE: flat in-band dict, NEVER a bare exception, NEVER nested error{}.

    run_mcp_tool is the sole boundary that converts a raised exception into a
    client-facing envelope; asserting on its return value (rather than
    catching an exception) is itself part of the contract -- the exception
    must never escape to the caller.
    """

    async def call() -> dict[str, object]:
        raise NotFoundError("No matching HGNC record found.")

    result = await run_mcp_tool(
        "get_gene", call, context=McpErrorContext("get_gene", arguments={"query": "ZZZZZ"})
    )

    assert result["success"] is False
    assert result["error_code"] == "not_found"
    assert isinstance(result["message"], str)
    assert result["message"]
    assert result["retryable"] is False
    assert isinstance(result["recovery_action"], str)
    assert result["recovery_action"]
    assert "error" not in result
    assert result["_meta"]["tool"] == "get_gene"
    # Fleet Response-Envelope Standard v1 (2026-07-03): error envelopes stamp
    # the clinical-safety disclaimer per-call too, not just on success.
    assert result["_meta"]["unsafe_for_clinical_use"] is True


async def test_error_envelope_flags_retryable_codes_true() -> None:
    """Retryable error classes (e.g. rate_limited) set retryable: True."""

    async def call() -> dict[str, object]:
        raise RateLimitError("HGNC REST API rate limit hit.")

    result = await run_mcp_tool("resolve_symbol", call, context=McpErrorContext("resolve_symbol"))

    assert result["success"] is False
    assert result["error_code"] == "rate_limited"
    assert result["retryable"] is True
    assert "error" not in result
    assert result["_meta"]["tool"] == "resolve_symbol"
    assert result["_meta"]["unsafe_for_clinical_use"] is True


def test_research_use_disclaimer_is_declared_once_in_capabilities() -> None:
    """The static disclaimer text/citation/release info still lives here too.

    hgnc-link declares ``research_use_only`` / ``research_use_notice``
    (full text + citation + HGNC release) exactly once in
    ``get_server_capabilities`` to conserve tokens; the machine-checkable
    ``unsafe_for_clinical_use`` flag is additionally stamped on every
    per-call ``_meta`` (see the success/error envelope tests above) and is
    documented here via ``per_call_meta``.
    """
    caps = build_capabilities()

    assert caps["research_use_only"] is True
    assert caps["research_use_notice"]
    assert caps["per_call_meta"] == [
        "tool",
        "request_id",
        "next_commands",
        "unsafe_for_clinical_use",
    ]
