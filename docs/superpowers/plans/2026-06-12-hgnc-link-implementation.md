# hgnc-link — Implementation Plan

Build order (each step committed atomically). Conventions mirror uniprot-link
(MCP layer) + gencc-link (bulk pipeline) + clingen-link (HGNC parsing).

## P0 — Project scaffold
- `pyproject.toml` (hatchling, deps, 3 scripts: `hgnc-link`, `hgnc-link-mcp`,
  `hgnc-link-data`), `__init__.py` (`__version__="0.1.0"`), `.gitignore`,
  `.env.example`, `Makefile`, `scripts/check_file_size.py`, `LICENSE`.

## P1 — Core
- `config.py` — `HgncDataConfig` (data_dir, db_filename, urls, timeouts,
  auto_bootstrap, refresh_enabled=False, cache) + `HgncApiConfig` (rest base_url,
  contact_email, timeout, rate limit, retries) + `ServerSettings` (env prefix
  `HGNC_LINK_`).
- `exceptions.py` — `HgncError` base; `NotFoundError`, `WithdrawnEntryError`
  (carries replaced_by), `InvalidInputError(field,allowed,hint)`,
  `AmbiguousQueryError(candidates)`, `DataUnavailableError`, `RateLimitError`,
  `ServiceUnavailableError`.
- `logging_config.py`, `buildinfo.py` — copy uniprot patterns (rename).
- `constants.py` — bulk URLs, REST searchable/stored fields, xref database map,
  locus_group/type vocab, recommended citation, HGNC release note.

## P2 — Ingest pipeline
- `ingest/parser.py` — parse `hgnc_complete_set.json` (docs[]) and `withdrawn.txt`;
  normalize multi-value fields to lists; build exploded symbol-lookup + xref +
  gene-group rows.
- `ingest/downloader.py` — conditional GET (ETag/Last-Modified) streaming both
  files + cache sidecar (adapt gencc; drop quota logic).
- `ingest/lock.py` — fcntl build lock (copy gencc).
- `data/schema.sql` — gene, symbol_lookup, xref, gene_group, withdrawn, gene_fts,
  meta.
- `ingest/builder.py` — build tmp SQLite, load tables + FTS5, write meta,
  `os.replace` swap; `ensure_database`, `rebuild`.
- `ingest/cli.py` — typer `build`/`refresh`/`status`.

## P3 — Data + services
- `data/repository.py` — read-only SQLite: `get_meta`, `resolve(query)` (id/symbol/
  prev/alias cascade → candidates+match_type), `get_gene`, `search(q,limit)` FTS,
  `get_xrefs`, `lookup_by_xref(source,value)`, `get_group(group)`, `get_withdrawn`.
- `services/shaping.py` — `RESPONSE_MODES`, `apply_response_mode(payload,mode,kind)`.
- `services/hgnc_service.py` — orchestration; returns plain dicts; optional live
  REST fallback when DB unavailable.
- `api/client.py` — thin httpx REST client (fetch/search/info) for live fallback +
  integration tests; error mapping.

## P4 — MCP layer (copy uniprot patterns, retarget)
- `mcp/annotations.py`, `arg_help.py`, `next_commands.py`, `envelope.py`,
  `schemas.py`, `resources.py`, `capabilities.py`, `middleware.py`,
  `service_adapters.py`, `facade.py`.
- `mcp/tools/`: `discovery.py` (get_server_capabilities, get_hgnc_diagnostics),
  `resolve.py` (resolve_symbol, resolve_symbols_batch), `genes.py` (get_gene,
  search_genes, get_gene_cross_references), `xref.py` (lookup_by_xref),
  `groups.py` (get_gene_group).

## P5 — Server entry
- `server.py`, `mcp_server.py`, `server_manager.py`, `app.py` (lifespan bootstraps
  DB via `ensure_database` in a thread; non-fatal).

## P6 — Tests (pytest, fail_under=80)
- conftest: build a tiny fixture SQLite from `tests/fixtures_genes.json` +
  `fixtures_withdrawn.txt`; `service_factory`; fake REST client.
- unit: parser, builder/repository, shaping, resolve cascade, arg_help,
  next_commands, capabilities, envelope, exceptions, end-to-end tool calls through
  the real facade (structured_content), structured-output, arg-middleware,
  REST client error mapping (respx).
- integration (`-m integration`): live GCS download build + live REST asserts.

## P7 — Ops + docs
- `docker/` (Dockerfile, compose, README), `docs/` (architecture, usage,
  deployment with crontab + systemd timer), `README.md`, `AGENTS.md`, `CLAUDE.md`,
  `CHANGELOG.md`, claude-desktop config sample.

## P8 — Verify
- `make ci-local` (format, lint, typecheck, tests). Build real DB via
  `hgnc-link-data build`. Live MCP smoke test of every tool. MCP-TEST-REPORT.md.
