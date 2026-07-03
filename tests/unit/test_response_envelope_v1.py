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

Known drift vs the ratified standard (see module-level test docstrings
below for detail): the standard calls for ``_meta.unsafe_for_clinical_use``
on every SUCCESS envelope. hgnc-link deliberately omits that key per-call --
see the "Per-call _meta is kept lean" note atop ``mcp/envelope.py`` and the
``provenance_policy``/``per_call_meta`` fields in ``mcp/capabilities.py``.
The research-use disclaimer is instead declared once, statically, in
``get_server_capabilities`` (``research_use_only`` / ``research_use_notice``).
This file asserts what the repo actually ships, not the aspirational key.
"""

from __future__ import annotations

from hgnc_link.exceptions import NotFoundError, RateLimitError
from hgnc_link.mcp.capabilities import build_capabilities
from hgnc_link.mcp.envelope import McpErrorContext, run_mcp_tool


async def test_success_envelope_is_flat_with_lean_meta() -> None:
    """SUCCESS: {"success": True, <payload>, "_meta": {...}}, flat (no nesting).

    Ground truth: hgnc-link's per-call ``_meta`` carries only ``tool`` and
    ``request_id`` (plus optional ``next_commands`` /
    ``argument_aliases_applied`` when a tool body supplies them) -- there is
    no per-call ``unsafe_for_clinical_use`` key. See module docstring.
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
    # Ground truth: no per-call clinical-use disclaimer key ships today.
    assert "unsafe_for_clinical_use" not in result["_meta"]


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


def test_research_use_disclaimer_is_declared_once_in_capabilities() -> None:
    """The standard's clinical-safety intent is enforced, just at a different layer.

    hgnc-link does not repeat a clinical-use disclaimer on every call (see
    module docstring); it declares ``research_use_only`` /
    ``research_use_notice`` exactly once in ``get_server_capabilities`` and
    documents that tradeoff via ``provenance_policy`` / ``per_call_meta``.
    Lock that this disclaimer still exists so drift here is caught too.
    """
    caps = build_capabilities()

    assert caps["research_use_only"] is True
    assert caps["research_use_notice"]
    assert caps["per_call_meta"] == ["tool", "request_id", "next_commands"]
