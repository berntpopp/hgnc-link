"""Response-Envelope Standard v1.2: provenance on every success, checked against the schema.

The schema is vendored from berntpopp/genefoundry-envelope, tag v1.2.0. Every data tool
runs in-process against the fixture index.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from hgnc_link.mcp.capabilities import TOOLS

CONFORMANCE = Path(__file__).parents[1] / "conformance"
SCHEMA = Draft202012Validator(json.loads((CONFORMANCE / "envelope-v1.2.schema.json").read_text()))
#: One successful call per data tool, answered by the fixture index.
DATA_CALLS: dict[str, dict[str, Any]] = {
    "resolve_symbol": {"query": "BRAF"},
    "resolve_symbols_batch": {"queries": ["BRAF", "NOT_A_GENE"]},
    "get_gene": {"query": "BRAF"},
    "search_genes": {"query": "BRAF"},
    "get_gene_cross_references": {"query": "BRAF"},
    "resolve_gene_by_xref": {"source": "entrez_id", "value": "673"},
    "get_gene_group": {"group": "1157"},
}
OPS_TOOLS = {"get_server_capabilities", "get_hgnc_diagnostics"}  # outside the v1.2 rule


def _errors(envelope: Any) -> list[str]:
    return [f"{e.json_path}: {e.message}" for e in SCHEMA.iter_errors(envelope)]


def test_vendored_schema_is_the_v1_2_0_release() -> None:
    digest = hashlib.sha256((CONFORMANCE / "envelope-v1.2.schema.json").read_bytes()).hexdigest()
    assert digest == (CONFORMANCE / "envelope-v1.2.schema.sha256").read_text().strip()
    assert digest == "c3c47e20d7dd189aac2568fc963b5514d7a5ac2c3e5f21d126f42c96d1ad1ae3"


def test_every_data_tool_has_a_call() -> None:
    assert set(DATA_CALLS) == set(TOOLS) - OPS_TOOLS


@pytest.mark.parametrize("tool", DATA_CALLS)
async def test_data_tool_success_is_a_v1_2_envelope(
    tool: str, facade: Any, structured: Any, repo: Any
) -> None:
    envelope = structured(await facade.call_tool(tool, DATA_CALLS[tool]))

    assert envelope["success"] is True, envelope
    assert _errors(envelope) == []
    index = repo.get_meta()
    meta = envelope["_meta"]
    assert meta["source"] == "hgnc"
    # The release and the build time of the index that answered, not of this call.
    assert meta["data_version"] == (index["release"] or index["source_last_modified"])
    assert meta["retrieved_at"] == index["build_utc"][:19] + "Z"
    assert all(meta[key] for key in ("source", "data_version", "retrieved_at"))


async def test_error_is_a_valid_envelope_without_provenance(facade: Any, structured: Any) -> None:
    for arguments in ({"query": "ZZZZZ"}, {"querie": "BRAF"}):  # not found, bad argument
        envelope = structured(await facade.call_tool("get_gene", arguments))
        assert envelope["success"] is False
        assert _errors(envelope) == []
        assert "retrieved_at" not in envelope["_meta"]
