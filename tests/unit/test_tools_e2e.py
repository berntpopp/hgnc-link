"""End-to-end tool calls through the real FastMCP facade (fixture-backed)."""

from __future__ import annotations

from typing import Any


async def test_capabilities_tool(facade: Any, structured: Any) -> None:
    res = await facade.call_tool("get_server_capabilities", {})
    payload = structured(res)
    assert payload["success"] is True
    assert payload["tool_count"] == 9


async def test_diagnostics_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_hgnc_diagnostics", {}))
    assert payload["data_available"] is True
    assert payload["gene_count"] == 9
    assert payload["_meta"]["next_commands"][0]["tool"] == "resolve_symbol"


async def test_resolve_tool_success(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "BRAF"}))
    assert payload["hgnc_id"] == "HGNC:1097"
    assert payload["match_type"] == "current"
    assert payload["_meta"]["next_commands"][0]["tool"] == "get_gene"


async def test_resolve_alias_via_arg_alias(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"symbol": "BRAF1"}))
    assert payload["match_type"] == "alias"
    assert payload["_meta"]["argument_aliases_applied"] == [["symbol", "query"]]


async def test_unknown_argument_did_you_mean(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"querie": "BRAF"}))
    assert payload["success"] is False
    assert payload["error_code"] == "invalid_input"
    assert "query" in payload["allowed_values"]


async def test_get_gene_modes(facade: Any, structured: Any) -> None:
    full = structured(
        await facade.call_tool("get_gene", {"query": "BRAF", "response_mode": "full"})
    )
    assert "date_modified" in full
    compact = structured(await facade.call_tool("get_gene", {"query": "BRAF"}))
    assert "date_modified" not in compact


async def test_withdrawn_redirect(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "A1S9T"}))
    assert payload["success"] is False
    assert payload["error_code"] == "not_found"
    assert payload["obsolete"] is True
    assert payload["_meta"]["next_commands"][0]["arguments"]["query"] == "HGNC:12469"


async def test_not_found(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene", {"query": "ZZZZZ"}))
    assert payload["error_code"] == "not_found"
    assert payload["recovery_action"] == "reformulate_input"


async def test_search_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("search_genes", {"query": "tumor"}))
    assert any(h["symbol"] == "TP53" for h in payload["results"])


async def test_cross_references_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene_cross_references", {"query": "TP53"}))
    assert "ensembl_gene_id" in payload["cross_references"]


async def test_cross_references_compact_includes_high_value(facade: Any, structured: Any) -> None:
    # The finding-#4 fields (MANE/UniProt/OMIM) must be present in the default tier.
    payload = structured(await facade.call_tool("get_gene_cross_references", {"query": "BRAF"}))
    assert {"mane_select", "uniprot_ids", "omim_id"} <= set(payload["cross_references"])
    assert payload["response_mode"] == "compact"
    full = structured(
        await facade.call_tool(
            "get_gene_cross_references", {"query": "BRAF", "response_mode": "full"}
        )
    )
    assert payload["database_count"] < full["database_count"]


async def test_cross_references_unknown_db_envelope(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool(
            "get_gene_cross_references", {"query": "BRAF", "databases": ["mane", "bogus_db"]}
        )
    )
    assert payload["success"] is False
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "databases"


async def test_cross_references_friendly_filter_resolves(facade: Any, structured: Any) -> None:
    # Finding #2 lock: a friendly token ('mane') resolves to the field, not silent-empty.
    payload = structured(
        await facade.call_tool(
            "get_gene_cross_references", {"query": "BRAF", "databases": ["mane"]}
        )
    )
    assert payload["success"] is True
    assert "mane_select" in payload["cross_references"]
    assert payload["database_count"] == 1


async def test_withdrawn_redirect_by_id_form(facade: Any, structured: Any) -> None:
    # Blocker-class lock: a withdrawn entry via HGNC id must not trip a null-field crash.
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "HGNC:6"}))
    assert payload["success"] is False
    assert payload["error_code"] == "not_found"
    assert payload["obsolete"] is True
    assert payload["replaced_by"][0]["symbol"] == "UBA1"


async def test_resolve_gene_by_xref_tool(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool(
            "resolve_gene_by_xref", {"source": "ensembl_gene_id", "value": "ENSG00000157764"}
        )
    )
    assert payload["results"][0]["symbol"] == "BRAF"
    # Contract truth (D1): the description lead names hgnc_id, symbol, name.
    assert {"hgnc_id", "symbol", "name"} <= payload["results"][0].keys()


async def test_resolve_gene_by_xref_unknown_source(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("resolve_gene_by_xref", {"source": "bogus", "value": "x"})
    )
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "source"
    assert payload["allowed_values"]


async def test_limit_out_of_range_envelope(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("search_genes", {"query": "x", "limit": 250}))
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "limit"
    assert "200" in payload["message"]
    assert payload["allowed_values"] == ["1..200"]


async def test_bad_response_mode_envelope(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("get_gene", {"query": "BRAF", "response_mode": "verbose"})
    )
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "response_mode"
    assert set(payload["allowed_values"]) == {"minimal", "compact", "standard", "full"}


async def test_gene_group_tool(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene_group", {"group": "1157"}))
    assert payload["group_name"] == "RAF family"
    assert any(m["symbol"] == "BRAF" for m in payload["members"])


async def test_gene_group_pagination_next_command(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene_group", {"group": "9990", "limit": 1}))
    assert payload["truncated"] is True
    assert payload["next_offset"] == 1
    nxt = [
        c
        for c in payload["_meta"]["next_commands"]
        if c["tool"] == "get_gene_group" and c["arguments"].get("offset") == 1
    ]
    assert nxt and nxt[0]["arguments"]["limit"] == 1


async def test_batch_tool(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool("resolve_symbols_batch", {"queries": ["BRAF", "A1S9T", "NOSUCH"]})
    )
    assert payload["resolved_count"] == 1
    assert payload["unresolved_count"] == 2


async def test_resolve_symbol_accepts_ensembl_gene_id(facade: Any, structured: Any) -> None:
    """#133: an Ensembl gene id resolves through the xref index; match_type names the id type."""
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "ENSG00000157764"}))
    assert payload["success"] is True
    assert payload["approved_symbol"] == "BRAF"
    assert payload["match_type"] == "ensembl_gene_id"
    assert payload["query"] == "ENSG00000157764"


async def test_resolve_description_points_to_batch_right_after_lead(facade: Any) -> None:
    tool = next(t for t in await facade.list_tools() if t.name == "resolve_symbol")
    second = (tool.description or "").split(". ")[1]
    assert second.startswith("For 2 or more genes, call resolve_symbols_batch once")
    batch = next(t for t in await facade.list_tools() if t.name == "resolve_symbols_batch")
    for word in ("Ensembl gene ids", "ENSG00000157764", "RefSeq", "UniProt"):
        assert word in (batch.description or "")


async def test_bare_number_says_it_was_read_as_hgnc_id(facade: Any, structured: Any) -> None:
    """A bare number is an HGNC id; the result says so and offers the NCBI Gene reading."""
    for mode in ("minimal", "compact", "full"):
        payload = structured(
            await facade.call_tool("resolve_symbol", {"query": "1097", "response_mode": mode})
        )
        assert payload["match_type"] == "hgnc_id"
        assert "HGNC id, NOT an NCBI Gene id" in payload["note"]
        assert payload["_meta"]["next_commands"][-1] == {
            "tool": "resolve_gene_by_xref",
            "arguments": {"source": "entrez_id", "value": "1097"},
        }
    for query in ("HGNC:1097", "BRAF"):  # unambiguous forms carry neither
        payload = structured(await facade.call_tool("resolve_symbol", {"query": query}))
        assert "note" not in payload
        assert len(payload["_meta"]["next_commands"]) == 2
    batch = structured(await facade.call_tool("resolve_symbols_batch", {"queries": ["1097"]}))
    assert "note" in batch["results"][0]


async def test_unknown_ensembl_id_is_not_found_without_xref_hint(
    facade: Any, structured: Any
) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "ENSG00000999999"}))
    assert payload["error_code"] == "not_found"
    tools = [c["tool"] for c in payload["_meta"]["next_commands"]]
    assert "resolve_gene_by_xref" not in tools  # already tried; get_gene still hints it
    payload = structured(await facade.call_tool("get_gene", {"query": "ENSG00000999999"}))
    assert "resolve_gene_by_xref" in [c["tool"] for c in payload["_meta"]["next_commands"]]


async def test_batch_translates_ensembl_ids_and_lists_unmatched(
    facade: Any, structured: Any
) -> None:
    """#133: a list of ids is one call, one row per input, misses listed (not a failed call)."""
    ids = ["ENSG00000157764", "ENSG99999999999", "ENSG00000141510.17", "TP53"]
    payload = structured(await facade.call_tool("resolve_symbols_batch", {"queries": ids}))
    assert payload["success"] is True
    assert [r["query"] for r in payload["results"]] == ids
    assert [r.get("approved_symbol") for r in payload["results"]] == ["BRAF", None, "TP53", "TP53"]
    assert payload["unresolved_queries"] == ["ENSG99999999999"]
    assert (payload["resolved_count"], payload["unresolved_count"]) == (3, 1)


async def test_resolve_ambiguous_is_structured_error(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "DUPE"}))
    assert payload["success"] is False
    assert payload["error_code"] == "ambiguous_query"
    assert len(payload["candidates"]) == 2
    assert payload["recovery_action"] == "reformulate_input"
    assert payload["_meta"]["next_commands"][0]["tool"] == "get_gene"


async def test_resolve_description_names_only_returned_fields(facade: Any, structured: Any) -> None:
    """Contract truth (#128): every field the description's Returns {...} names is returned."""
    import re

    tool = next(t for t in await facade.list_tools() if t.name == "resolve_symbol")
    returns = re.search(r"Returns \{([^}]*)\}", tool.description or "")
    assert returns is not None
    named = re.findall(r"(?:^|,)\s*([a-z_]+)", returns.group(1))
    assert {"location", "name", "locus_type"} <= set(named)
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "BRAF"}))
    assert set(named) <= payload.keys()
