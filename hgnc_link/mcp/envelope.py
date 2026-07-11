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
from hgnc_link.mcp._sanitize import safe_field_name, sanitize_envelope, sanitize_message
from hgnc_link.mcp.next_commands import cmd, default_error_next_commands, withdrawn_recovery
from hgnc_link.safe_fields import (
    safe_allowed_values,
    safe_candidates,
    safe_replaced_by,
    safe_withdrawn_status,
)

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


# FIXED, error-code-specific public messages. The message NEVER interpolates the
# caller's query/identifier or an upstream value: those carry injection prose that
# survives code-point stripping (the deepest fleet-review lesson). The actionable
# detail travels in structured, server-authored fields (field / allowed_values /
# hint / candidates / next_commands); the raw exception text stays server-side.
_PUBLIC_MESSAGE: dict[str, str] = {
    "not_found": "The requested HGNC record was not found.",
    "ambiguous_query": "The request matched several HGNC records; see candidates.",
    "invalid_input": "The request was invalid. See field / allowed_values / hint.",
    "data_unavailable": "The local HGNC database is unavailable.",
    "rate_limited": "HGNC REST rate limit hit. Retry shortly.",
    "upstream_unavailable": "The HGNC upstream is temporarily unavailable.",
    "internal_error": "An internal error occurred. The request was not completed.",
}

# Fixed, server-authored recovery hint for invalid_input. The exception's own
# ``hint`` is NOT surfaced (it could carry copied prose); ``field`` +
# ``allowed_values`` already carry the validated, actionable detail.
_INVALID_INPUT_HINT = "Correct the offending argument (see field and allowed_values), then retry."


def _classify(exc: BaseException) -> tuple[str, str]:
    """Return ``(error_code, fixed_public_message)`` for an exception.

    Only ``McpToolError`` supplies its own message (server-authored, raised inside
    a tool body); every other class maps to a FIXED public message so no caller
    input or upstream value is ever echoed into a caller-visible string.
    """
    if isinstance(exc, McpToolError):
        return exc.error_code, exc.message
    if isinstance(exc, NotFoundError):  # WithdrawnEntryError subclasses this
        code = "not_found"
    elif isinstance(exc, AmbiguousQueryError):
        code = "ambiguous_query"
    elif isinstance(exc, InvalidInputError | PydanticValidationError):
        code = "invalid_input"
    elif isinstance(exc, DataUnavailableError):
        code = "data_unavailable"
    elif isinstance(exc, RateLimitError):
        code = "rate_limited"
    elif isinstance(exc, ServiceUnavailableError | DownloadError):
        code = "upstream_unavailable"
    else:
        code = "internal_error"
    return code, _PUBLIC_MESSAGE[code]


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
    # DEFINITIVE RULE: never copy an exception attribute verbatim into a caller-
    # visible field. Each is rebuilt from a validated identifier, a closed enum, or
    # a fixed server string; non-conforming values are dropped. sanitize_envelope()
    # is only the final code-point backstop ON TOP of this.
    if isinstance(exc, InvalidInputError):
        if exc.field is not None:
            envelope["field"] = safe_field_name(exc.field)  # identifier or <redacted>
        if exc.allowed is not None:
            envelope["allowed_values"] = safe_allowed_values(exc.allowed)  # drop prose
        if exc.hint is not None:
            envelope["hint"] = _INVALID_INPUT_HINT  # fixed server string, not exc.hint
    if isinstance(exc, AmbiguousQueryError) and exc.candidates:
        safe_cands = safe_candidates(exc.candidates)  # validated ids only; name dropped
        envelope["candidates"] = safe_cands
        chain = [cmd("get_gene", query=c["hgnc_id"]) for c in safe_cands[:3]]
        envelope["_meta"]["next_commands"] = chain or [cmd("get_server_capabilities")]
    elif isinstance(exc, WithdrawnEntryError):
        replaced = safe_replaced_by(exc.replaced_by)  # validated successor ids only
        envelope["obsolete"] = True
        envelope["withdrawn_status"] = safe_withdrawn_status(exc.withdrawn_status)  # enum
        envelope["replaced_by"] = replaced
        envelope["_meta"]["next_commands"] = withdrawn_recovery(replaced)
    elif context.fallback is not None:
        envelope["_meta"]["next_commands"] = [context.fallback]
    else:
        envelope["_meta"]["next_commands"] = default_error_next_commands(
            context.tool_name, error_code, context.arguments
        )
    # Final code-point backstop over EVERY string leaf (message, field,
    # allowed_values, hint, candidates, withdrawn_status, replaced_by, and
    # _meta.next_commands[*].arguments.*), whichever branch built them.
    return sanitize_envelope(envelope)


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
    # unexpected/unknown key). It is NEVER interpolated into the message -- it is
    # validated-or-redacted into the structured ``field`` key only. The message is
    # built solely from server-derived values: ``tool_name``, the server-computed
    # ``suggestion`` (always a real parameter name), ``signature``, and the
    # schema-derived constraint ``human`` phrase.
    safe_loc = safe_field_name(loc)
    dym = f" Did you mean `{suggestion}`?" if suggestion else ""
    if constraints is not None:
        allowed, human = constraints
        message = f"Invalid argument value for {tool_name}: {human}. See 'field'."
        allowed_values = allowed
    else:
        if error_type == "missing_argument":
            head = f"A required argument is missing for {tool_name}."
        elif error_type == "unexpected_keyword_argument":
            head = f"An unknown argument was supplied to {tool_name}."
        else:
            head = f"An argument value was invalid for {tool_name}."
        message = f"{head}{dym} See 'field'; valid names are in allowed_values."
        allowed_values = valid_params
    return sanitize_envelope(
        {
            "success": False,
            "error_code": "invalid_input",
            "message": sanitize_message(message),
            "retryable": False,
            "recovery_action": "reformulate_input",
            "field": safe_loc,
            "allowed_values": safe_allowed_values(allowed_values),
            "hint": signature,
            "_meta": {
                "tool": tool_name,
                "request_id": _request_id(),
                "next_commands": [cmd("get_server_capabilities")],
                "unsafe_for_clinical_use": _UNSAFE_FOR_CLINICAL_USE,
            },
        }
    )


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
            # Code-point backstop over the WHOLE success payload too (curated data
            # is clean, so this is a no-op there; it strips any forbidden code point
            # from a caller-echoed correlation key such as a batch row's `query`).
            result = sanitize_envelope(result)
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
