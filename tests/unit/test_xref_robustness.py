"""Regression tests for issue #26 — reverse cross-reference robustness.

These are written against the CORRECT behaviour and were watched to FAIL against the
pre-fix code (TDD): a versioned Ensembl/RefSeq accession must resolve to the same gene
(never a bare not_found), the server's own MANE Select transcript must round-trip back
to its gene, and a syntactically malformed HGNC id must be invalid_input, not not_found.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hgnc_link.config import HgncDataConfig
from hgnc_link.data.repository import HgncRepository
from hgnc_link.exceptions import AmbiguousQueryError, InvalidInputError, NotFoundError
from hgnc_link.ingest.builder import build_database
from hgnc_link.services.hgnc_service import HgncService

# --------------------------------------------------------------------------- D1 (HIGH)
# Versioned accessions — the form VEP / GENCODE / every clinical report emit.


def test_versioned_ensembl_gene_id_resolves(service: HgncService) -> None:
    """ENSG…​.<version> resolves to the SAME gene as the unversioned form (not not_found)."""
    versioned = service.lookup_by_xref("ensembl_gene_id", "ENSG00000157764.15")
    assert versioned["count"] == 1
    assert versioned["results"][0]["symbol"] == "BRAF"
    # Parity with the unversioned form the audit showed resolving.
    unversioned = service.lookup_by_xref("ensembl_gene_id", "ENSG00000157764")
    assert unversioned["results"][0]["symbol"] == "BRAF"


def test_versioned_refseq_accession_resolves(service: HgncService) -> None:
    """NM_000546.6 (versioned) resolves to TP53, like NM_000546."""
    res = service.lookup_by_xref("refseq", "NM_000546.6")
    assert res["results"][0]["symbol"] == "TP53"


def test_versioned_accession_is_never_bare_not_found_for_real_gene(service: HgncService) -> None:
    """A real gene addressed by a versioned id must not read as 'gene does not exist'."""
    res = service.lookup_by_xref("ensembl_gene_id", "ENSG00000141510.17")
    assert res["count"] >= 1
    assert res["results"][0]["symbol"] == "TP53"


# --------------------------------------------------------------------------- D2 (MEDIUM)
# The MANE Select transcript the server itself returns must resolve back to its gene.


def test_mane_select_source_is_accepted(service: HgncService) -> None:
    """source='mane_select' is a valid source (was rejected outright as invalid_input)."""
    res = service.lookup_by_xref("mane_select", "NM_024426.6")
    assert res["results"][0]["symbol"] == "WT1"


def test_mane_transcript_roundtrips_unversioned(service: HgncService) -> None:
    """The MANE RefSeq transcript resolves even unversioned and even via source='refseq'.

    WT1's MANE Select NM_024426.* is NOT in its refseq_accession (NM_000378); an agent
    holding the modern clinical transcript must still get back to the gene.
    """
    assert service.lookup_by_xref("mane_select", "NM_024426")["results"][0]["symbol"] == "WT1"
    assert service.lookup_by_xref("refseq", "NM_024426")["results"][0]["symbol"] == "WT1"
    assert service.lookup_by_xref("mane_select", "ENST00000452863")["results"][0]["symbol"] == "WT1"


# --------------------------------------------------------------------------- D5 (LOW)
# A syntactically malformed HGNC id is invalid_input, not not_found.


def test_malformed_hgnc_id_is_invalid_input_not_not_found(service: HgncService) -> None:
    """get_gene('HGNC:abc') is a bad identifier (invalid_input), not a missing gene."""
    with pytest.raises(InvalidInputError) as exc_info:
        service.get_gene("HGNC:abc")
    assert exc_info.value.field == "query"


def test_malformed_hgnc_id_via_resolve(service: HgncService) -> None:
    with pytest.raises(InvalidInputError):
        service.resolve("hgnc:xyz")


def test_real_missing_gene_is_still_not_found(service: HgncService) -> None:
    """A well-formed but nonexistent HGNC id stays not_found (no over-broad invalid_input)."""
    with pytest.raises(NotFoundError):
        service.get_gene("HGNC:99999999")


# --------------------------------------------------------------------------- tool-surface D1
# End-to-end through the FastMCP facade: the headline repro.


async def test_versioned_accession_tool_resolves(facade: Any, structured: Any) -> None:
    payload = structured(
        await facade.call_tool(
            "resolve_gene_by_xref",
            {"source": "ensembl_gene_id", "value": "ENSG00000157764.15"},
        )
    )
    assert payload["success"] is True
    assert payload["results"][0]["symbol"] == "BRAF"


# ------------------------------------------------------- rework: no false version matches
# Version stripping must be scoped: a numeric id is never version-stripped, and the MANE
# fallback never overrides the source the caller named.


def test_numeric_id_with_a_dot_is_invalid_not_a_stripped_match(service: HgncService) -> None:
    """entrez_id=673.99 is malformed (invalid_input), NOT a version-stripped match on 673."""
    with pytest.raises(InvalidInputError) as exc_info:
        service.lookup_by_xref("entrez_id", "673.99")
    assert exc_info.value.field == "value"
    # sanity: the bare integer still resolves
    assert service.lookup_by_xref("entrez_id", "673")["results"][0]["symbol"] == "BRAF"


def test_mane_fallback_never_overrides_the_named_source(service: HgncService) -> None:
    """source='omim_id' must NOT silently cross-resolve a MANE transcript to WT1."""
    with pytest.raises(NotFoundError):
        service.lookup_by_xref("omim_id", "NM_024426")
    # a non-transcript, non-numeric source is equally not cross-resolved
    with pytest.raises(NotFoundError):
        service.lookup_by_xref("uniprot", "NM_024426")


# ------------------------------------------------------- rework: cross-gene collision guard


@pytest.fixture
def collision_service(tmp_path: Path) -> HgncService:
    """A 2-gene index where two DISTINCT genes share a MANE base with different versions."""
    docs = {
        "response": {
            "docs": [
                {"hgnc_id": "HGNC:900201", "symbol": "COLA", "mane_select": ["NM_9999999.1"]},
                {"hgnc_id": "HGNC:900202", "symbol": "COLB", "mane_select": ["NM_9999999.2"]},
            ]
        }
    }
    src = tmp_path / "docs.json"
    src.write_text(json.dumps(docs), encoding="utf-8")
    cfg = HgncDataConfig(data_dir=tmp_path, db_filename="collide.sqlite")
    build_database(cfg, complete_set_path=src, withdrawn_path=None, etag=None, last_modified=None)
    return HgncService(HgncRepository(cfg.db_path))


def test_version_collision_across_genes_is_ambiguous_not_merged(
    collision_service: HgncService,
) -> None:
    """An unversioned base that matches two DIFFERENT genes is ambiguous, never merged."""
    with pytest.raises(AmbiguousQueryError) as exc_info:
        collision_service.lookup_by_xref("mane_select", "NM_9999999")
    assert len(exc_info.value.candidates) == 2


def test_exact_versioned_id_picks_the_one_gene(collision_service: HgncService) -> None:
    """An EXACT versioned id resolves to its single gene (no version collapse)."""
    res = collision_service.lookup_by_xref("mane_select", "NM_9999999.1")
    assert res["count"] == 1
    assert res["results"][0]["symbol"] == "COLA"


def test_versioned_like_does_not_match_a_non_digit_suffix(collision_service: HgncService) -> None:
    """`NM_9999999.BAD` must not match `NM_9999999.1/.2` (version must be `.<digits>`)."""
    with pytest.raises(NotFoundError):
        collision_service.lookup_by_xref("mane_select", "NM_9999999.BAD")
