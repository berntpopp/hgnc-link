"""Guard: hgnc-link exposes no externally sourced free-text field (v1.1 no-untrusted-text).

hgnc-link is classified `no-untrusted-text` in the router's
`docs/conformance/untrusted-text-inventory.yml` (Task C of the fleet untrusted-content
fencing programme): every tool returns *curated nomenclature* -- HGNC-committee-assigned
symbols/names/enums and cross-reference IDs -- sourced from HGNC's own
``hgnc_complete_set.json`` bulk dump, never third-party free-text prose (no literature
abstracts, no scraped descriptions, no user-submitted notes). There is therefore nothing to
fence. This test is the regression guard: it fails loudly if a future change introduces an
upstream free-text surface without reclassifying the backend and adding a v1.1 fence.

Two layers, matching the depth of the JSON-schema surface:

1. **Declared MCP output schemas** (`hgnc_link/mcp/schemas.py`): every tool's declared
   ``properties`` must be disjoint from ``FORBIDDEN_FREETEXT_KEYS``.
2. **The full record field catalogue** (`hgnc_link/constants.py` ``SCALAR_FIELDS`` +
   ``LIST_FIELDS``): the gene-record schemas are deliberately *permissive*
   (``additionalProperties: True``) so ``response_mode=full`` can pass through fields not
   itemized in the declared schema (e.g. ``alias_name``, ``prev_name``, ``date_modified``).
   Checking only the declared schema would miss a prose field smuggled in through that
   permissiveness, so the true column catalogue that backs every gene record is checked too.

``name`` (HGNC "Approved Name"), ``alias_name`` (Alias Name), and ``prev_name`` (Previous
Name) are the one family of fields that could be mistaken for free-text: they are short
human-readable strings. They are NOT upstream prose -- they are HGNC-committee-curated
official/alternate/former gene names (the same controlled-vocabulary nomenclature as
``symbol``), sourced from the same curated bulk dump as every other field. The live-fixture
assertions below pin this down concretely against a real built record.
"""

from __future__ import annotations

from typing import Any

import pytest

from hgnc_link.constants import LIST_FIELDS, SCALAR_FIELDS
from hgnc_link.mcp.schemas import (
    CAPABILITIES_SCHEMA,
    CROSS_REFERENCES_SCHEMA,
    DIAGNOSTICS_SCHEMA,
    GENE_GROUP_SCHEMA,
    GENE_SCHEMA,
    RESOLVE_BATCH_SCHEMA,
    RESOLVE_SCHEMA,
    SEARCH_SCHEMA,
    XREF_LOOKUP_SCHEMA,
)
from hgnc_link.services.hgnc_service import HgncService

# Curated nomenclature only (approved symbols/names, IDs, enums, cross-refs, numeric
# scores) -- no upstream free-text prose surface anywhere in hgnc-link's output. Keys drawn
# from the fleet-wide untrusted-content-fencing vocabulary (definition/description/summary/
# abstract/notes/comment are the generic prose markers; involvement/match/phenotypes/
# evidence/criterion_description are surfaces named in sibling backends' inventory rows).
FORBIDDEN_FREETEXT_KEYS = {
    "definition",
    "description",
    "summary",
    "abstract",
    "notes",
    "comment",
    "involvement",
    "match",
    "phenotypes",
    "evidence",
    "criterion_description",
}

# Every MCP tool's declared output schema (name -> schema dict).
ALL_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_server_capabilities": CAPABILITIES_SCHEMA,
    "get_hgnc_diagnostics": DIAGNOSTICS_SCHEMA,
    "resolve_symbol": RESOLVE_SCHEMA,
    "resolve_symbols_batch": RESOLVE_BATCH_SCHEMA,
    "get_gene": GENE_SCHEMA,
    "search_genes": SEARCH_SCHEMA,
    "get_gene_cross_references": CROSS_REFERENCES_SCHEMA,
    "resolve_gene_by_xref": XREF_LOOKUP_SCHEMA,
    "get_gene_group": GENE_GROUP_SCHEMA,
}


@pytest.mark.parametrize("tool_name", sorted(ALL_TOOL_SCHEMAS))
def test_tool_output_schema_has_no_free_text_surface(tool_name: str) -> None:
    """Every declared MCP output schema is disjoint from the forbidden prose keys."""
    schema = ALL_TOOL_SCHEMAS[tool_name]
    props = set(schema["properties"])
    offending = props & FORBIDDEN_FREETEXT_KEYS
    assert not offending, f"{tool_name} introduced an unclassified free-text field: {offending}"


def test_gene_record_field_catalogue_has_no_free_text_surface() -> None:
    """The full gene-record column catalogue (the superset behind response_mode=full).

    ``GENE_SCHEMA`` declares ``additionalProperties: True`` so response_mode=full/standard
    can pass through columns not itemized in the declared schema. Check the *actual* SQLite
    column catalogue that backs every gene record (mirrors ``_GENE_COLUMNS`` in
    ``hgnc_link/ingest/builder.py``), not just the declared subset, so a prose column added
    to the source data cannot slip through the schema's permissiveness undetected.
    """
    full_catalogue = set(SCALAR_FIELDS) | set(LIST_FIELDS)
    offending = full_catalogue & FORBIDDEN_FREETEXT_KEYS
    assert not offending, f"hgnc gene record catalogue introduced free-text field(s): {offending}"


def test_name_fields_are_curated_nomenclature_not_upstream_prose(service: HgncService) -> None:
    """``name``/``alias_name``/``prev_name`` are curated HGNC names, not free prose.

    These are the only human-readable string fields in the gene record, so they are the
    field family most likely to be mistaken for (or quietly repurposed into) an upstream
    free-text surface. Pin them down against a real built record: HGNC "Approved Name",
    "Alias Name", and "Previous Name" are short, committee-curated noun phrases sourced from
    the same curated bulk dump as ``symbol`` -- never a scraped description or literature
    abstract.
    """
    record = service.get_gene("BRAF", mode="full")

    # Curated Approved Name: exact, short, noun-phrase nomenclature -- not a sentence of
    # scraped/free prose.
    assert record["name"] == "B-Raf proto-oncogene, serine/threonine kinase"
    assert record["symbol"] == "BRAF"

    # Curated Previous Name: same nomenclature family, one short noun phrase.
    assert record["prev_name"] == ["v-raf murine sarcoma viral oncogene homolog B"]

    # None of these curated name fields collide with the forbidden free-text vocabulary --
    # they are named for what they are (name/alias_name/prev_name), never
    # description/summary/abstract/notes.
    name_fields = {"name", "alias_name", "prev_name"}
    assert name_fields.isdisjoint(FORBIDDEN_FREETEXT_KEYS)


def test_ambiguous_query_candidates_carry_no_free_text(service: HgncService) -> None:
    """Ambiguity/error surfaces (candidates, other_matches) are curated briefs, not prose.

    ``_brief()`` (hgnc_link/services/hgnc_service.py) is the one place candidate/other-match
    summaries are built; confirm its real output keys stay curated-field-only so a future
    change cannot smuggle an upstream free-text field into an error payload.
    """
    from hgnc_link.exceptions import AmbiguousQueryError

    with pytest.raises(AmbiguousQueryError) as exc_info:
        service.resolve("DUPE")  # fixture: alias shared by AMBA + AMBB (within-tier ambiguity)

    for candidate in exc_info.value.candidates:
        offending = set(candidate) & FORBIDDEN_FREETEXT_KEYS
        assert not offending, f"ambiguous-query candidate introduced free-text field: {offending}"
