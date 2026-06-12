-- hgnc-link local index schema (built from the HGNC bulk dumps).
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = OFF;

-- One row per approved HGNC record. List fields are stored as JSON text.
CREATE TABLE gene (
    hgnc_id                 TEXT PRIMARY KEY,
    symbol                  TEXT NOT NULL,
    symbol_upper            TEXT NOT NULL,
    name                    TEXT,
    status                  TEXT,
    locus_group             TEXT,
    locus_type              TEXT,
    location                TEXT,
    location_sortable       TEXT,
    entrez_id               TEXT,
    ensembl_gene_id         TEXT,
    vega_id                 TEXT,
    ucsc_id                 TEXT,
    cosmic                  TEXT,
    orphanet                TEXT,
    agr                     TEXT,
    date_approved_reserved  TEXT,
    date_symbol_changed     TEXT,
    date_name_changed       TEXT,
    date_modified           TEXT,
    uuid                    TEXT,
    alias_symbol            TEXT,
    alias_name              TEXT,
    prev_symbol             TEXT,
    prev_name               TEXT,
    gene_group              TEXT,
    gene_group_id           TEXT,
    uniprot_ids             TEXT,
    refseq_accession        TEXT,
    ccds_id                 TEXT,
    ena                     TEXT,
    omim_id                 TEXT,
    mgd_id                  TEXT,
    rgd_id                  TEXT,
    pubmed_id               TEXT,
    mane_select             TEXT,
    lsdb                    TEXT,
    rna_central_id          TEXT
);
CREATE INDEX idx_gene_symbol_upper ON gene (symbol_upper);

-- Exploded resolution index: one row per symbol form, with provenance.
CREATE TABLE symbol_lookup (
    lookup_symbol  TEXT NOT NULL,   -- uppercased
    hgnc_id        TEXT NOT NULL,
    symbol_type    TEXT NOT NULL    -- current | previous | alias
);
CREATE INDEX idx_symbol_lookup ON symbol_lookup (lookup_symbol);

-- Reverse cross-reference index: external id -> hgnc_id.
CREATE TABLE xref (
    source       TEXT NOT NULL,     -- HGNC field name (entrez_id, ensembl_gene_id, ...)
    value_upper  TEXT NOT NULL,
    value        TEXT NOT NULL,
    hgnc_id      TEXT NOT NULL
);
CREATE INDEX idx_xref ON xref (source, value_upper);

-- Gene group/family membership.
CREATE TABLE gene_group (
    group_id    TEXT,
    group_name  TEXT,
    hgnc_id     TEXT NOT NULL
);
CREATE INDEX idx_group_id ON gene_group (group_id);
CREATE INDEX idx_group_name ON gene_group (group_name);

-- Withdrawn / merged entries -> successor redirects.
CREATE TABLE withdrawn (
    hgnc_id                 TEXT PRIMARY KEY,
    status                  TEXT,
    withdrawn_symbol        TEXT,
    withdrawn_symbol_upper  TEXT,
    replaced_by             TEXT   -- JSON array of {hgnc_id, symbol, status}
);
CREATE INDEX idx_withdrawn_symbol ON withdrawn (withdrawn_symbol_upper);

-- Free-text search over the searchable name fields.
CREATE VIRTUAL TABLE gene_fts USING fts5 (
    hgnc_id UNINDEXED,
    symbol,
    name,
    alias_symbol,
    prev_symbol,
    tokenize = 'unicode61'
);

-- Single-row build provenance.
CREATE TABLE meta (
    id                       INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version           INTEGER,
    release                  TEXT,
    source_complete_set_url  TEXT,
    source_withdrawn_url     TEXT,
    source_etag              TEXT,
    source_last_modified     TEXT,
    gene_count               INTEGER,
    withdrawn_count          INTEGER,
    symbol_lookup_count      INTEGER,
    build_utc                TEXT,
    build_duration_s         REAL
);
