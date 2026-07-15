"""HGNC domain constants: field catalogues, cross-reference map, vocabularies.

Sourced from the live ``rest.genenames.org/info`` field lists and the
``hgnc_complete_set`` schema (verified 2026-06-12). The REST ``fetch`` records
and the bulk-JSON ``docs`` share identical field names and shapes, so one
catalogue serves both ingestion and the live fallback.
"""

from __future__ import annotations

#: Bumped when the SQLite schema or build logic changes incompatibly.
SCHEMA_VERSION = 1

#: Scalar (single-value) record fields kept as columns on the ``gene`` table.
SCALAR_FIELDS: tuple[str, ...] = (
    "hgnc_id",
    "symbol",
    "name",
    "status",
    "locus_group",
    "locus_type",
    "location",
    "location_sortable",
    "entrez_id",
    "ensembl_gene_id",
    "vega_id",
    "ucsc_id",
    "cosmic",
    "orphanet",
    "agr",
    "date_approved_reserved",
    "date_symbol_changed",
    "date_name_changed",
    "date_modified",
    "uuid",
)

#: Multi-value fields: pipe-delimited in the TSV, JSON arrays in the dump/REST.
#: Stored as JSON-encoded text columns on the ``gene`` table.
LIST_FIELDS: tuple[str, ...] = (
    "alias_symbol",
    "alias_name",
    "prev_symbol",
    "prev_name",
    "gene_group",
    "gene_group_id",
    "uniprot_ids",
    "refseq_accession",
    "ccds_id",
    "ena",
    "omim_id",
    "mgd_id",
    "rgd_id",
    "pubmed_id",
    "mane_select",
    "lsdb",
    "rna_central_id",
)

#: Ordered cross-reference fields surfaced by get_gene_cross_references, mapping
#: the HGNC field name to a human-readable database label.
XREF_FIELDS: tuple[tuple[str, str], ...] = (
    ("entrez_id", "NCBI Gene"),
    ("ensembl_gene_id", "Ensembl"),
    ("uniprot_ids", "UniProt"),
    ("refseq_accession", "RefSeq"),
    ("mane_select", "MANE Select"),
    ("omim_id", "OMIM"),
    ("ucsc_id", "UCSC"),
    ("vega_id", "VEGA"),
    ("ccds_id", "CCDS"),
    ("ena", "ENA"),
    ("mgd_id", "MGI"),
    ("rgd_id", "RGD"),
    ("orphanet", "Orphanet"),
    ("cosmic", "COSMIC"),
    ("pubmed_id", "PubMed"),
)

#: Reverse-lookup map for resolve_gene_by_xref: accepted ``source`` synonym -> the HGNC
#: field whose index is searched. Values are matched case-insensitively.
XREF_SOURCE_ALIASES: dict[str, str] = {
    "entrez_id": "entrez_id",
    "entrez": "entrez_id",
    "ncbi": "entrez_id",
    "ncbi_gene_id": "entrez_id",
    "ncbi_gene": "entrez_id",
    "gene_id": "entrez_id",
    "ensembl_gene_id": "ensembl_gene_id",
    "ensembl": "ensembl_gene_id",
    "ensg": "ensembl_gene_id",
    "uniprot_ids": "uniprot_ids",
    "uniprot": "uniprot_ids",
    "uniprot_id": "uniprot_ids",
    "refseq_accession": "refseq_accession",
    "refseq": "refseq_accession",
    "omim_id": "omim_id",
    "omim": "omim_id",
    "mim": "omim_id",
    "ucsc_id": "ucsc_id",
    "ucsc": "ucsc_id",
    "vega_id": "vega_id",
    "vega": "vega_id",
    "ccds_id": "ccds_id",
    "ccds": "ccds_id",
    "ena": "ena",
    "mgd_id": "mgd_id",
    "mgi": "mgd_id",
    "rgd_id": "rgd_id",
    "rgd": "rgd_id",
    # MANE Select transcript (Ensembl ENST + RefSeq NM_). Indexed by the builder
    # (mane_select is an XREF_FIELDS entry) but previously not an accepted source,
    # so the transcript the server itself emits could not be resolved back (issue #26).
    "mane_select": "mane_select",
    "mane": "mane_select",
}

#: The `source` schema enum for resolve_gene_by_xref. It is EXACTLY the set of
#: values the runtime accepts (every XREF_SOURCE_ALIASES key, canonical keys AND
#: synonyms), so the declared enum is never NARROWER than the runtime: a
#: schema-aware client is never told a runtime-valid source is invalid. Guarded
#: against drift by tests/unit/test_identifiers.py.
XREF_LOOKUP_SOURCE_ENUM: tuple[str, ...] = tuple(sorted(XREF_SOURCE_ALIASES))

#: Reverse-lookup source fields whose ids legitimately carry a trailing ``.<version>``
#: (Ensembl gene, RefSeq accession, MANE Select transcript). ONLY these are matched
#: version-insensitively; a numeric id (entrez_id/omim_id) never is, so entrez_id
#: '673.99' is malformed, not a match on '673' (issue #26 review).
VERSIONED_XREF_FIELDS: frozenset[str] = frozenset(
    {"ensembl_gene_id", "refseq_accession", "mane_select"}
)

#: Reverse-lookup source fields whose value must be a bare integer. A non-integer is
#: a malformed id (invalid_input), never a version-stripped false match: entrez_id
#: '673.99' is malformed, not a match on '673'.
NUMERIC_XREF_FIELDS: frozenset[str] = frozenset({"entrez_id"})

#: response_mode -> the cross-reference fields get_gene_cross_references emits when
#: no explicit ``databases=`` filter is given. ``minimal`` keeps the two anchor ids;
#: ``compact`` (default) keeps the high-value identifiers most callers want;
#: ``standard``/``full`` emit every populated field. An explicit ``databases=``
#: filter overrides the tier. Documented in get_server_capabilities.
XREF_TIER_MINIMAL: tuple[str, ...] = ("entrez_id", "ensembl_gene_id")
XREF_TIER_COMPACT: tuple[str, ...] = (
    "entrez_id",
    "ensembl_gene_id",
    "uniprot_ids",
    "refseq_accession",
    "mane_select",
    "omim_id",
    "ccds_id",
)

#: Forward-filter synonyms for get_gene_cross_references' ``databases`` argument:
#: friendly label / synonym -> the canonical XREF field key. Every XREF_FIELDS
#: field is filterable by its own key, its (lowercased) label, and curated aliases.
#: Matched case-insensitively. Unknown keys are rejected with invalid_input.
XREF_FILTER_ALIASES: dict[str, str] = {
    **{field: field for field, _ in XREF_FIELDS},
    **{label.lower(): field for field, label in XREF_FIELDS},
    "ncbi": "entrez_id",
    "ncbi_gene": "entrez_id",
    "ncbi_gene_id": "entrez_id",
    "entrez": "entrez_id",
    "gene_id": "entrez_id",
    "ensembl": "ensembl_gene_id",
    "ensg": "ensembl_gene_id",
    "uniprot": "uniprot_ids",
    "uniprot_id": "uniprot_ids",
    "refseq": "refseq_accession",
    "mane": "mane_select",
    "omim": "omim_id",
    "mim": "omim_id",
    "ucsc": "ucsc_id",
    "vega": "vega_id",
    "ccds": "ccds_id",
    "mgi": "mgd_id",
    "rgd": "rgd_id",
    "pubmed": "pubmed_id",
}

#: The `databases` item enum for get_gene_cross_references. EXACTLY the set the
#: runtime accepts (every XREF_FILTER_ALIASES key), so a schema-aware client sees the
#: full closed vocabulary and never rejects a runtime-valid label. Guarded against
#: drift by tests/unit/test_capabilities.py.
XREF_FILTER_ENUM: tuple[str, ...] = tuple(sorted(XREF_FILTER_ALIASES))

#: The four HGNC locus groups (with live record counts as of 2026-06).
LOCUS_GROUPS: tuple[str, ...] = (
    "protein-coding gene",
    "pseudogene",
    "non-coding RNA",
    "other",
)

#: The HGNC status values (Approved in the complete set; withdrawn forms live in
#: withdrawn.txt and surface via resolve_symbol redirects).
STATUS_VALUES: tuple[str, ...] = (
    "Approved",
    "Entry Withdrawn",
    "Merged/Split",
)

#: Match-type provenance returned by resolve_symbol.
MATCH_TYPES: tuple[str, ...] = (
    "hgnc_id",
    "current",
    "previous",
    "alias",
    "withdrawn",
)

RECOMMENDED_CITATION = (
    "Seal RL, Braschi B, Gray K, Jones TEM, Tweedie S, Haim-Vilmovsky L, "
    "Bruford EA. Genenames.org: the HGNC resources in 2023. Nucleic Acids Res. "
    "2023;51(D1):D1003-D1009. doi:10.1093/nar/gkac888. RRID:SCR_002827."
)

#: HGNC data is released with no usage restrictions (effectively CC0).
HGNC_LICENSE = (
    "HGNC data is released with no usage restrictions (effectively public "
    "domain / CC0). Attribution is requested but not required."
)
