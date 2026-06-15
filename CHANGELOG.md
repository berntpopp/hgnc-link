# Changelog

All notable changes to hgnc-link are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-06-15

### Breaking — GeneFoundry Tool-Naming Standard v1

Adopted the GeneFoundry Tool-Naming & Normalization Standard v1 so this server
composes cleanly behind `genefoundry-router` (see berntpopp/hgnc-link#1). Leaf
tool names stay **unprefixed**; the canonical gateway **namespace token** is
`hgnc` (tools surface as `hgnc_<tool>` once federated).

- **Renamed tool `lookup_by_xref` → `resolve_gene_by_xref`.** `lookup` is a
  non-canonical verb under Standard v1 (rule 2: `lookup → get`/`resolve`); the
  canonical verb set is `get | search | list | resolve | find | compare |
  compute`. This is a reverse identifier resolution (external id → HGNC gene),
  so `resolve_*` fits. **No deprecation alias is provided** (rule 7).

  **Migration:** replace any call to `lookup_by_xref(source=, value=,
  response_mode=)` with `resolve_gene_by_xref(source=, value=, response_mode=)`.
  Arguments and behaviour are unchanged.

The other eight tools were already compliant (unprefixed, `verb_noun`,
canonical verb, ≤ 50 chars, domain-tagged, fleet-canon `response_mode`/`limit`/
`offset` args), so no further renames were needed.

### Added (Tool-Naming Standard v1)
- CI guard `tests/unit/test_tool_names.py` asserting every registered tool name
  matches `^[a-z0-9_]{1,50}$`, starts with a canonical verb, and does not
  self-prefix the `hgnc` namespace token.
- README documents the `serverInfo.name` (`hgnc-link`) and the canonical gateway
  namespace token (`hgnc`).

### Changed (excellence pass v2 — live-assessment residual gaps)
- **`get_gene_cross_references` `response_mode` tiers are now meaningful.** The
  tool previously returned every populated xref in every mode (so `response_mode`
  was inert). Now `minimal` = NCBI + Ensembl ids; `compact` (default) = the
  high-value set (NCBI, Ensembl, UniProt, RefSeq, MANE Select, OMIM, CCDS) — which
  **includes** the MANE/UniProt/OMIM fields a prior report found missing;
  `standard`/`full` = every populated field. An explicit `databases=` filter still
  overrides the tier. The chosen tier is echoed as `response_mode`.
- **`get_gene_group` paginates.** Members are now globally symbol-ordered (resolved
  in SQL) and sliced by `limit` + a new `offset`; the response carries `offset`,
  `limit`, `truncated`, and `next_offset`, and — when truncated — a `next_commands`
  entry that fetches the next page. Pagination partitions the membership with no
  overlaps or skips.

### Added (excellence pass v2)
- **`resolve_symbols_batch.queries` is schema-capped at `maxItems:200`** for
  client-side parity with `search_genes.limit` / `get_gene_group.limit`; the
  server-side cap remains as a backstop and array-length violations now report
  "must have between 0 and 200 items".
- **Capabilities document three contracts that were previously implicit:**
  `cross_reference_tiers` (the per-mode field sets), `argument_alias_policy`
  (aliases are server-side synonyms; schema-strict clients use the canonical
  parameter; unknown names get a did-you-mean), and `search_semantics`
  (`search_genes` is nomenclature-only — no disease/phenotype matching). The last
  two are surfaced in the light capabilities summary.
- Regression tests locking the ambiguous-`resolve_symbol` → `ambiguous_query`
  contract, withdrawn/merged redirects through `resolve_symbol` (symbol and id
  forms), the `databases=` synonym/reject behavior, and build-provenance
  propagation into the capabilities surface — closing the live re-run's coverage
  gaps so they cannot silently regress.

### Fixed
- **`resolve_symbol` no longer breaks on ambiguity.** An alias shared by several
  genes now returns a structured `ambiguous_query` error with the candidate list
  and `next_commands` to each candidate — identical to `get_gene` /
  `get_gene_cross_references` — instead of emitting a success payload with a null
  `hgnc_id` that strict MCP clients reject as an output-validation error. Schema
  identity fields are nullable as defense-in-depth.
- **`get_gene_cross_references` `databases` filter is forgiving and loud.** It
  accepts friendly labels/synonyms (`mane`, `ncbi`, `mim`, …) as well as field
  keys, and rejects an unknown key with `invalid_input` + did-you-mean instead of
  the silent `database_count:0, success:true` that looked like missing data.
- **Invalid argument *values* report the valid range/enum.** `search_genes`
  `limit` out of range and `get_gene` `response_mode` typos now say
  "must be between 1 and 200" / "must be one of: minimal, compact, standard, full"
  with the constraint in `allowed_values`, rather than listing argument names.

### Changed
- **`resolve_symbol` honors `response_mode`** (minimal/compact/standard/full now
  differ) and drops the self-duplicating `candidates` array on success (~40%
  lighter); cross-tier alternatives surface as a lean `other_matches` list.
- **`resolve_symbols_batch`** returns each ambiguous query inline
  (`ambiguous:true` + candidates) so one ambiguity never blocks the batch.
- Capabilities document the single-tool-vs-batch `ambiguity_contract` and the
  `cross_reference_filter_synonyms`.

### Added
- Cross-tool hints: an external id (ENSG / UniProt / RefSeq) thrown at
  `resolve_symbol` / `resolve_symbols_batch` now suggests `resolve_gene_by_xref`.
- Build provenance (`git_sha`, `built_at`) resolves from `.git` in a checkout and
  from Docker build args in production, so a running server can report its build.

## [0.1.0] - 2026-06-12

Initial release.

### Added
- MCP + HTTP server (`unified` / `http` / `stdio` transports) backed by a local
  SQLite index built from the HGNC bulk dumps (`hgnc_complete_set.json` +
  `withdrawn.txt`).
- `hgnc-link-data` CLI (`build` / `refresh` / `status`) — the cron entry point —
  with conditional (ETag/Last-Modified) download and atomic rebuild.
- Tools: `get_server_capabilities`, `get_hgnc_diagnostics`, `resolve_symbol`,
  `resolve_symbols_batch`, `get_gene`, `search_genes`,
  `get_gene_cross_references`, `lookup_by_xref`, `get_gene_group`.
- Resolution cascade (HGNC ID → current → previous → alias → withdrawn redirect)
  with `match_type` provenance, ambiguity surfacing, and `HGNC:NNNN`⇄`NNNN`
  normalization.
- Typed error envelope, `{tool, arguments}` chaining via `_meta.next_commands`,
  argument-alias middleware, response-mode shaping, and `hgnc://` discovery
  resources.
- Optional live `rest.genenames.org` fallback (`api/client.py`).
- Docker image + compose, crontab / systemd timer deployment docs, full unit
  test suite (network-free, fixture-backed) and opt-in live integration tests.
