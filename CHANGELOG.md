# Changelog

All notable changes to hgnc-link are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

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
