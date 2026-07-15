"""MCP contract-hardening v1 regression guards (issue #26 + fleet-four).

Locks the four fleet-wide contract fixes at the FastMCP-facade boundary:

* every error envelope carries the protocol ``isError: true`` flag (not just
  ``success: false``), so a client branching on ``isError`` sees the failure;
* ``error_code`` stays inside the closed six-value enum;
* a mistyped argument names the TYPE, not a phantom range (D5);
* the promised did-you-mean is surfaced for an unknown ``databases`` key (D4).
"""

from __future__ import annotations

from typing import Any

import pytest

# The exact six-value error_code enum (Response-Envelope Standard v1).
ERROR_CODES = {
    "invalid_input",
    "not_found",
    "ambiguous_query",
    "upstream_unavailable",
    "rate_limited",
    "internal",
}


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_gene", {"query": "ZZZZZ"}),  # not_found
        ("get_gene", {"query": "HGNC:abc"}),  # invalid_input (malformed id, D5)
        ("resolve_symbol", {"query": "DUPE"}),  # ambiguous_query
        ("get_gene", {"nope": "x"}),  # invalid_input (unknown arg)
        ("search_genes", {"query": "x", "limit": "ten"}),  # invalid_input (bad type)
        ("resolve_gene_by_xref", {"source": "bogus", "value": "x"}),  # invalid_input
    ],
)
async def test_every_error_sets_is_error_and_a_canon_code(
    facade: Any, structured: Any, tool: str, args: dict[str, Any]
) -> None:
    result = await facade.call_tool(tool, args)
    payload = structured(result)
    assert payload["success"] is False
    # THE fleet fix: a returned error envelope MUST set the protocol isError flag.
    assert result.is_error is True, f"{tool} error envelope did not set isError:true"
    assert payload["error_code"] in ERROR_CODES


async def test_success_call_is_not_flagged_as_error(facade: Any, structured: Any) -> None:
    result = await facade.call_tool("resolve_symbol", {"query": "BRAF"})
    assert result.is_error is False
    assert structured(result)["success"] is True


async def test_mistyped_limit_names_the_type_not_a_range(facade: Any, structured: Any) -> None:
    """D5: limit='ten' is a TYPE error ('must be an integer'), not a range violation."""
    payload = structured(await facade.call_tool("search_genes", {"query": "BRAF", "limit": "ten"}))
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "limit"
    assert "integer" in payload["message"]
    assert "between" not in payload["message"]


async def test_unknown_database_returns_did_you_mean(facade: Any, structured: Any) -> None:
    """D4: a one-char typo of a database key surfaces the promised did_you_mean field."""
    payload = structured(
        await facade.call_tool(
            "get_gene_cross_references", {"query": "BRAF", "databases": ["ensmbl"]}
        )
    )
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "databases"
    assert payload["did_you_mean"] == ["ensembl_gene_id"]


async def test_malformed_hgnc_id_tool_is_invalid_input(facade: Any, structured: Any) -> None:
    """D5: get_gene('HGNC:abc') is invalid_input naming the expected format, not not_found."""
    payload = structured(await facade.call_tool("get_gene", {"query": "HGNC:abc"}))
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "query"
    assert "HGNC:1100" in payload["allowed_values"]


async def test_get_gene_full_adds_internal_fields_over_standard(
    facade: Any, structured: Any
) -> None:
    """D3: standard and full are no longer byte-identical for get_gene."""
    standard = structured(
        await facade.call_tool("get_gene", {"query": "BRAF", "response_mode": "standard"})
    )
    full = structured(
        await facade.call_tool("get_gene", {"query": "BRAF", "response_mode": "full"})
    )
    assert "uuid" in full
    assert "uuid" not in standard
    assert set(full) > set(standard)
