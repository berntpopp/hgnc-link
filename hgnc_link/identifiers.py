"""HGNC identifier helpers: normalize the ``HGNC:NNNN`` <-> ``NNNN`` forms.

Every studied consumer (sysndd, kidney-genetics) hand-rolls the ``HGNC:`` strip
and re-add; centralising it here means callers never parse identifiers
themselves.
"""

from __future__ import annotations

import re

_HGNC_ID_RE = re.compile(r"^HGNC:(\d+)$", re.IGNORECASE)
_BARE_ID_RE = re.compile(r"^\d+$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/-]{0,63}$")

# External-identifier shapes recognised so resolve_* can redirect to resolve_gene_by_xref.
# Only ids the reverse lookup can actually resolve are mapped (ENST transcripts,
# which the gene-id index cannot match, deliberately return None).
_ENSG_RE = re.compile(r"^ENSG\d{6,}", re.IGNORECASE)
_REFSEQ_RE = re.compile(r"^(NM_|NP_|NR_|XM_|XP_|NG_)\d+", re.IGNORECASE)
_UNIPROT_RE = re.compile(
    r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$"
)

# A trailing sequence-version suffix (``.NN``) as carried by Ensembl (ENSG/ENST),
# RefSeq (NM_/NP_/...) and CCDS/UCSC accessions. VEP, GENCODE and clinical reports
# emit the versioned form; HGNC's own indexes are a mix of versioned (mane_select,
# ucsc) and unversioned (ensembl_gene_id, refseq_accession), so the reverse lookup
# must match version-insensitively (see repository.lookup_by_xref).
_ACCESSION_VERSION_RE = re.compile(r"\.\d+$")

# MANE Select transcript shapes (Ensembl transcript ENST… or RefSeq mRNA NM_/NR_/XM_).
# Used to fall back to the mane_select index when a caller labels a MANE transcript
# 'refseq'/'ensembl' but it is not the gene's primary refseq_accession/ensembl id.
_TRANSCRIPT_RE = re.compile(r"^(ENST\d|NM_|NR_|XM_|XR_)", re.IGNORECASE)


def strip_accession_version(value: str) -> str:
    """Return ``value`` with a single trailing ``.<digits>`` version suffix removed.

    ``ENSG00000012048.23`` -> ``ENSG00000012048``; ``NM_000546.6`` -> ``NM_000546``;
    a value with no version suffix (``ENSG00000012048``, ``673``) is returned unchanged.
    """
    return _ACCESSION_VERSION_RE.sub("", (value or "").strip())


def looks_like_transcript(value: str) -> bool:
    """True for an Ensembl-transcript / RefSeq-mRNA accession (a MANE Select shape)."""
    return bool(_TRANSCRIPT_RE.match((value or "").strip()))


_HGNC_PREFIX_RE = re.compile(r"^HGNC:", re.IGNORECASE)


def looks_like_malformed_hgnc_id(value: str) -> bool:
    """True for a value that *attempts* the ``HGNC:`` form but is not a valid id.

    ``HGNC:abc`` / ``hgnc:1a`` -> ``True`` (a malformed identifier, not a symbol);
    ``HGNC:1100`` / ``BRCA1`` -> ``False``. Lets the resolver answer a botched id with
    ``invalid_input`` (naming the ``HGNC:<digits>`` format) instead of ``not_found``.
    """
    text = (value or "").strip()
    return bool(_HGNC_PREFIX_RE.match(text)) and normalize_hgnc_id(text) is None


def normalize_hgnc_id(value: str) -> str | None:
    """Return the canonical ``HGNC:NNNN`` form for an ID, or ``None`` if not one.

    Accepts ``HGNC:1100``, ``hgnc:1100``, and the bare numeric ``1100`` forms.
    """
    text = (value or "").strip()
    match = _HGNC_ID_RE.match(text)
    if match:
        return f"HGNC:{match.group(1)}"
    if _BARE_ID_RE.match(text):
        return f"HGNC:{text}"
    return None


def looks_like_hgnc_id(value: str) -> bool:
    """True when ``value`` is an HGNC ID in either accepted form."""
    return normalize_hgnc_id(value) is not None


def looks_like_symbol(value: str) -> bool:
    """True for a plausible gene-symbol shape (and not an HGNC ID)."""
    text = (value or "").strip()
    if not text or looks_like_hgnc_id(text):
        return False
    return bool(_SYMBOL_RE.match(text))


def infer_xref_source(value: str) -> str | None:
    """Map an external-id-shaped string to a ``resolve_gene_by_xref`` source, or ``None``.

    Lets a symbol-resolution miss redirect the caller to the reverse-mapping tool
    (e.g. an Ensembl gene id thrown at ``resolve_symbol`` -> ``resolve_gene_by_xref``).
    """
    text = (value or "").strip()
    if _ENSG_RE.match(text):
        return "ensembl_gene_id"
    if _REFSEQ_RE.match(text):
        return "refseq"
    if _UNIPROT_RE.match(text):
        return "uniprot"
    return None
