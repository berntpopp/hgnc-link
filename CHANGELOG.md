# Changelog

All notable changes to hgnc-link are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
  `resolve_symbol` / `resolve_symbols_batch` now suggests `lookup_by_xref`.
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
