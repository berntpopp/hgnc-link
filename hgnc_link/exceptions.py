"""Custom exceptions for hgnc-link.

Two error families flow into the MCP envelope:

- **Data-store errors** raised by the local SQLite repository / services
  (``NotFoundError``, ``WithdrawnEntryError``, ``AmbiguousQueryError``,
  ``DataUnavailableError``).
- **Live-fallback errors** raised by the optional REST client when the local DB
  is unavailable (``RateLimitError``, ``ServiceUnavailableError``).

``run_mcp_tool`` classifies each into a stable ``error_code`` (see
``hgnc_link.mcp.envelope``).
"""

from __future__ import annotations


class HgncError(Exception):
    """Base exception for all hgnc-link data/client errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Store a human-readable message and optional HTTP status code."""
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        """Return the message (with status code when present)."""
        if self.status_code is not None:
            return f"[{self.status_code}] {self.message}"
        return self.message


class InvalidInputError(HgncError):
    """A tool/service argument failed validation before any lookup ran."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        *,
        allowed: list[str] | None = None,
        hint: str | None = None,
        did_you_mean: list[str] | None = None,
    ) -> None:
        """Initialise with the offending field and optional recovery data.

        ``allowed`` and ``hint`` are surfaced as structured top-level keys on the
        error envelope (``allowed_values``/``hint``) so a consumer never has to
        parse them out of a (length-capped) message. ``did_you_mean`` carries a
        best-guess correction drawn from a CLOSED server vocabulary (never caller
        input), surfaced as the ``did_you_mean`` envelope field.
        """
        super().__init__(message)
        self.field = field
        self.allowed = allowed
        self.hint = hint
        self.did_you_mean = did_you_mean


class NotFoundError(HgncError):
    """A lookup returned no rows for an otherwise valid identifier."""

    def __init__(self, message: str = "No matching HGNC record found.") -> None:
        """Initialise with a 404 status code."""
        super().__init__(message, status_code=404)


class WithdrawnEntryError(NotFoundError):
    """The symbol/ID exists in HGNC but has been withdrawn or merged.

    Subclasses :class:`NotFoundError` so it classifies as ``not_found`` in the
    error envelope, but carries the withdrawn symbol/ID, the withdrawal status
    (``Entry Withdrawn`` / ``Merged/Split``), and any replacement records so the
    envelope can flag ``obsolete: true`` and chain to the live successor(s).
    """

    def __init__(
        self,
        withdrawn: str,
        *,
        status: str,
        replaced_by: list[dict[str, str]] | None = None,
        message: str | None = None,
    ) -> None:
        """Store the withdrawn symbol/ID, its status, and replacement record(s)."""
        self.withdrawn = withdrawn
        self.withdrawn_status = status
        self.replaced_by = replaced_by or []
        if message is None:
            if self.replaced_by:
                targets = ", ".join(
                    f"{r.get('symbol', '?')} ({r.get('hgnc_id', '?')})" for r in self.replaced_by
                )
                message = f"{withdrawn} was withdrawn from HGNC ({status}). Merged into: {targets}."
            else:
                message = (
                    f"{withdrawn} was withdrawn from HGNC ({status}) and has no replacement record."
                )
        super().__init__(message)


class AmbiguousQueryError(HgncError):
    """A query matched several records and cannot be resolved unambiguously."""

    def __init__(self, message: str, *, candidates: list[dict[str, str]] | None = None) -> None:
        """Store the ambiguous candidates so the envelope can surface them."""
        super().__init__(message)
        self.candidates = candidates or []


class DataUnavailableError(HgncError):
    """The local HGNC SQLite index is missing, unbuilt, or unreadable."""

    def __init__(self, message: str = "The local HGNC database is not available.") -> None:
        """Initialise with a 503 status code."""
        super().__init__(message, status_code=503)


class RateLimitError(HgncError):
    """The live REST endpoint signalled rate limiting (HTTP 429 / 403)."""

    def __init__(self, message: str = "HGNC REST API rate limit hit.") -> None:
        """Initialise with a 429 status code."""
        super().__init__(message, status_code=429)


class ServiceUnavailableError(HgncError):
    """The live REST endpoint is temporarily unavailable (5xx / network error)."""

    def __init__(self, message: str = "HGNC REST API is temporarily unavailable.") -> None:
        """Initialise with a 503 status code."""
        super().__init__(message, status_code=503)


class DownloadError(HgncError):
    """A bulk-download attempt failed (network/HTTP error)."""
