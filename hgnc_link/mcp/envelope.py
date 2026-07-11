"""MCP envelope boundary: success/_meta injection and structured errors.

Tools return a plain dict; :func:`run_mcp_tool` injects ``success`` and ``_meta``
on success, and converts any exception into a structured error dict (returned,
never raised) so the LLM sees a typed failure rather than an opaque masked
message.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from hgnc_link.exceptions import (
    AmbiguousQueryError,
    DataUnavailableError,
    DownloadError,
    InvalidInputError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    WithdrawnEntryError,
)
from hgnc_link.mcp._sanitize import safe_field_name, sanitize_message
from hgnc_link.mcp.next_commands import cmd, default_error_next_commands, withdrawn_recovery

logger = logging.getLogger(__name__)

# Per-call _meta carries dynamic fields (tool, request_id, next_commands) plus
# the fleet-standard unsafe_for_clinical_use disclaimer, which per the
# GeneFoundry Response-Envelope Standard v1 (2026-07-03 fleet decision) must be
# stamped on EVERY tool response -- success and error, at all response_modes --
# not declared once via get_server_capabilities. Static provenance (citation,
# HGNC release, research_use_notice text) still lives only in
# get_server_capabilities to conserve tokens.
_RETRYABLE = {"rate_limited", "upstream_unavailable", "data_unavailable"}
_UNSAFE_FOR_CLINICAL_USE = True


@dataclass
class McpErrorContext:
    """Per-call context so envelopes can name the failing tool and recovery."""

    tool_name: str
    fallback: dict[str, Any] | None = field(default=None)
    arguments: dict[str, Any] = field(default_factory=dict)


class McpToolError(Exception):
    """Raised inside a tool body to emit a specific error code/message."""

    def __init__(self, *, error_code: str, message: str) -> None:
        """Store an error code and client-safe message."""
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


# Pydantic error ``type`` -> fixed, input-free reason. The raw pydantic ``msg``
# can echo the rejected input *value*, so it is never surfaced; only the bounded,
# server-defined error ``type`` keys a server-authored reason.
_PYDANTIC_REASON: dict[str, str] = {
    "missing": "a required value is missing",
    "string_type": "expected a string",
    "int_type": "expected an integer",
    "int_parsing": "expected an integer",
    "float_type": "expected a number",
    "bool_type": "expected a boolean",
    "list_type": "expected a list",
    "dict_type": "expected an object",
    "too_long": "too many items",
    "too_short": "too few items",
    "string_too_long": "value is too long",
    "string_too_short": "value is too short",
    "greater_than": "value is out of range",
    "greater_than_equal": "value is out of range",
    "less_than": "value is out of range",
    "less_than_equal": "value is out of range",
    "enum": "value is not one of the allowed options",
    "extra_forbidden": "unexpected argument",
    "unexpected_keyword_argument": "unexpected argument",
}


def _safe_message(exc: BaseException) -> str:
    # Server-authored classified messages: strip the fence's forbidden code
    # points defensively. Attacker-influenceable *prose* (upstream bodies, the
    # str(exc) of an API error) is severed to fixed strings at the source, so
    # this backstop only has to remove control/zero-width/bidi/NUL code points.
    return sanitize_message(str(exc) or exc.__class__.__name__)


def _classify(exc: BaseException) -> tuple[str, str]:
    """Return ``(error_code, client_safe_message)`` for an exception."""
    if isinstance(exc, McpToolError):
        return exc.error_code, exc.message
    if isinstance(exc, NotFoundError):  # WithdrawnEntryError subclasses this
        return "not_found", _safe_message(exc)
    if isinstance(exc, AmbiguousQueryError):
        return "ambiguous_query", _safe_message(exc)
    if isinstance(exc, InvalidInputError):
        return "invalid_input", _safe_message(exc)
    if isinstance(exc, DataUnavailableError):
        return "data_unavailable", _safe_message(exc)
    if isinstance(exc, RateLimitError):
        return "rate_limited", "HGNC REST rate limit hit. Retry shortly."
    if isinstance(exc, ServiceUnavailableError | DownloadError):
        return "upstream_unavailable", "The HGNC upstream is temporarily unavailable."
    if isinstance(exc, PydanticValidationError):
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ())) or "input"
        # Never echo the pydantic ``msg`` (it can reflect the rejected input);
        # key a fixed reason on the bounded error ``type`` and code-point-strip
        # the caller-controlled field name.
        reason = _PYDANTIC_REASON.get(str(first.get("type", "")), "value is invalid")
        return "invalid_input", f"Invalid input -- `{safe_field_name(loc)}`: {reason}."
    return "internal_error", "An internal error occurred. The request was not completed."


def _recovery_action(error_code: str) -> str:
    if error_code in _RETRYABLE:
        return "retry_backoff"
    if error_code in {"invalid_input", "not_found", "ambiguous_query"}:
        return "reformulate_input"
    return "switch_tool"


def _error_envelope(exc: BaseException, context: McpErrorContext) -> dict[str, Any]:
    error_code, message = _classify(exc)
    envelope: dict[str, Any] = {
        "success": False,
        "error_code": error_code,
        # Defensive: no forbidden code points reach the caller, whatever the path
        # (McpToolError / fixed classified strings included).
        "message": sanitize_message(message),
        "retryable": error_code in _RETRYABLE,
        "recovery_action": _recovery_action(error_code),
        "_meta": {
            "tool": context.tool_name,
            "request_id": _request_id(),
            "unsafe_for_clinical_use": _UNSAFE_FOR_CLINICAL_USE,
        },
    }
    if isinstance(exc, InvalidInputError):
        if exc.field is not None:
            envelope["field"] = exc.field
        if exc.allowed is not None:
            envelope["allowed_values"] = exc.allowed
        if exc.hint is not None:
            envelope["hint"] = exc.hint
    if isinstance(exc, AmbiguousQueryError) and exc.candidates:
        envelope["candidates"] = exc.candidates
        envelope["_meta"]["next_commands"] = [
            cmd("get_gene", query=c["hgnc_id"]) for c in exc.candidates[:3] if c.get("hgnc_id")
        ] or [cmd("get_server_capabilities")]
        return envelope
    if isinstance(exc, WithdrawnEntryError):
        envelope["obsolete"] = True
        envelope["withdrawn_status"] = exc.withdrawn_status
        envelope["replaced_by"] = exc.replaced_by
        envelope["_meta"]["next_commands"] = withdrawn_recovery(exc.replaced_by)
        return envelope
    if context.fallback is not None:
        envelope["_meta"]["next_commands"] = [context.fallback]
    else:
        envelope["_meta"]["next_commands"] = default_error_next_commands(
            context.tool_name, error_code, context.arguments
        )
    return envelope


def build_arg_error_envelope(
    *,
    tool_name: str,
    loc: str,
    error_type: str,
    valid_params: list[str],
    signature: str,
    suggestion: str | None,
    constraints: tuple[list[str], str] | None = None,
) -> dict[str, Any]:
    """Standard invalid-input envelope for an argument-binding failure.

    When ``constraints`` is supplied the failure is an invalid *value* on a known
    argument, so ``allowed_values`` carries the valid range/enum (not the list of
    argument *names*) and the message states the constraint.
    """
    # ``loc`` is the caller-supplied argument NAME (attacker-influenceable for an
    # unexpected/unknown key), so strip its forbidden code points before it is
    # echoed into either the message or the ``field`` key. ``suggestion`` and
    # ``signature`` are server-derived from the tool's real parameter set.
    safe_loc = safe_field_name(loc)
    if constraints is not None:
        allowed, human = constraints
        message = f"Invalid value for argument `{safe_loc}` of {tool_name}: {human}."
        return {
            "success": False,
            "error_code": "invalid_input",
            "message": sanitize_message(message),
            "retryable": False,
            "recovery_action": "reformulate_input",
            "field": safe_loc,
            "allowed_values": allowed,
            "hint": signature,
            "_meta": {
                "tool": tool_name,
                "request_id": _request_id(),
                "next_commands": [cmd("get_server_capabilities")],
                "unsafe_for_clinical_use": _UNSAFE_FOR_CLINICAL_USE,
            },
        }
    if error_type == "missing_argument":
        head = f"Missing required argument `{safe_loc}` for {tool_name}."
    elif error_type == "unexpected_keyword_argument":
        head = f"Unknown argument `{safe_loc}` for {tool_name}."
    else:
        head = f"Invalid value for argument `{safe_loc}` of {tool_name}."
    dym = f" Did you mean `{suggestion}`?" if suggestion else ""
    message = f"{head}{dym} Valid argument names are listed in allowed_values."
    return {
        "success": False,
        "error_code": "invalid_input",
        "message": sanitize_message(message),
        "retryable": False,
        "recovery_action": "reformulate_input",
        "field": safe_loc,
        "allowed_values": valid_params,
        "hint": signature,
        "_meta": {
            "tool": tool_name,
            "request_id": _request_id(),
            "next_commands": [cmd("get_server_capabilities")],
            "unsafe_for_clinical_use": _UNSAFE_FOR_CLINICAL_USE,
        },
    }


async def run_mcp_tool(
    tool_name: str,
    call: Callable[[], Awaitable[dict[str, Any]]],
    *,
    context: McpErrorContext | None = None,
) -> dict[str, Any]:
    """Execute a tool body, returning the result dict or a structured error dict."""
    ctx = context or McpErrorContext(tool_name=tool_name)
    try:
        result = await call()
        if isinstance(result, dict):
            result.setdefault("success", True)
            existing_meta: dict[str, Any] = result.get("_meta") or {}
            result["_meta"] = {
                **existing_meta,
                "tool": tool_name,
                "request_id": _request_id(),
                "unsafe_for_clinical_use": _UNSAFE_FOR_CLINICAL_USE,
            }
        return result
    except Exception as exc:  # broad catch is the error-boundary contract
        envelope = _error_envelope(exc, ctx)
        logger.warning(
            "mcp_tool_error tool=%s code=%s exc=%s",
            tool_name,
            envelope["error_code"],
            exc.__class__.__name__,
        )
        return envelope
