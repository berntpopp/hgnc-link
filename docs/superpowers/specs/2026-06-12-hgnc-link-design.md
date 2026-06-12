# hgnc-link — Design Spec

**Date:** 2026-06-12
**Status:** Approved (autonomous build per `/goal`)
**Author:** Claude (Fable 5) for bernt.popp@charite.de

## 1. Purpose

`hgnc-link` is a Model Context Protocol (MCP) server that grounds gene-nomenclature
questions in the **HUGO Gene Nomenclature Committee (HGNC)** dataset served from
genenames.org. It is a sibling of `uniprot-link`, `gnomad-link`, `gencc-link`,
`clingen-link`, etc., and replicates their architecture, conventions, and agentic
ergonomics exactly.

The single most valuable capability — confirmed by studying how `sysndd` and
`kidney-genetics` consume HGNC — is **symbol resolution**: mapping any gene symbol
(current, previous/withdrawn, or alias) plus any HGNC ID form to the canonical
`{hgnc_id, approved_symbol}`, with the match provenance and ambiguity surfaced
rather than silently collapsed.

## 2. Data strategy (locked)

Per the user directive *"use the downloads with cron jobs to update the data for
speed"*: the server is backed by a **local SQLite index** built from HGNC's bulk
downloads, refreshed by a **cron-invoked CLI**. Tools query the local DB — no
per-request REST round-trips — so lookups are sub-millisecond.

- **Sources** (public GCS bucket, no auth, CC0/no-restriction license):
  - `hgnc_complete_set.json` — all 44,997 approved records, 54 fields.
  - `withdrawn.txt` — 5,290 withdrawn/merged entries with redirect targets.
- **Refresh**: a `hgnc-link-data` CLI (`refresh`, `build`, `status`) performs a
  conditional GET (ETag/Last-Modified), and on change rebuilds a fresh SQLite into
  a temp file then atomically `os.replace`s it. Designed to be invoked from cron
  (HGNC updates Tue/Fri; a daily 304-check is cheap). A sample crontab and systemd
  timer ship in `docs/` and `docker/`.
- **Optional live fallback**: a thin `httpx` client for `rest.genenames.org` is
  included only as (a) a fallback when the DB is not yet built and (b) the target
  of integration tests. The default and primary path is the local DB.

### SQLite schema

- `gene` — one row per HGNC record. `hgnc_id` TEXT PK (`HGNC:NNNN`), `symbol`,
  `name`, `status`, `locus_group`, `locus_type`, `location`, plus all cross-ref
  columns. Multi-value fields stored as JSON arrays.
- `symbol_lookup` — exploded resolution index: `(lookup_symbol UPPER, hgnc_id,
  symbol_type)` where `symbol_type ∈ {current, previous, alias}`. Makes the
  3-tier cascade a single indexed query carrying provenance. (Modeled on sysndd's
  `hgnc_symbol_lookup`.)
- `xref` — `(source, value_upper, value, hgnc_id)` for reverse lookups
  (entrez_id, ensembl_gene_id, uniprot_ids, omim_id, refseq_accession, ucsc_id,
  vega_id, ccds_id, mgd_id, rgd_id, ...).
- `gene_group` — `(gene_group_id, gene_group_name, hgnc_id)` for family browse.
- `withdrawn` — `(hgnc_id, status, withdrawn_symbol_upper, withdrawn_symbol,
  merged_into JSON)` for retired-ID redirects.
- `gene_fts` — FTS5 over `symbol, name, alias_symbol, prev_symbol` for free-text
  search with rank ordering and a `LIKE` fallback.
- `meta` — single row: `release` (HGNC last-modified date), `source_etag`,
  `source_last_modified`, `gene_count`, `withdrawn_count`, `build_utc`,
  `schema_version`.

## 3. Stack & layout (mirrors uniprot-link / gencc-link)

Python ≥3.12, `uv`, hatchling. Deps: `fastapi`, `uvicorn[standard]`, `pydantic`,
`pydantic-settings`, `httpx`, `structlog`, `orjson`, `rich`, `typer`, `mcp[cli]`,
`fastmcp`. Dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-mock`,
`pytest-xdist`, `respx`, `ruff`, `mypy`.

```
hgnc_link/
  __init__.py            __version__
  config.py              pydantic-settings, env prefix HGNC_LINK_
  exceptions.py          HgncError hierarchy → error taxonomy
  logging_config.py      structlog → stderr
  buildinfo.py           version/git_sha/built_at
  app.py                 FastAPI host (/health, /), lifespan bootstraps DB
  server_manager.py      unified / http / stdio transports
  api/client.py          thin httpx REST client (optional live fallback)
  ingest/
    downloader.py        conditional-GET streaming download + cache sidecar
    parser.py            HGNC JSON/TSV + withdrawn.txt parsing
    builder.py           build SQLite (tables + FTS5) + atomic swap
    lock.py              cross-process build lock (fcntl)
    cli.py               `hgnc-link-data` typer CLI (build/refresh/status)
  data/
    repository.py        read-only SQLite query layer (resolve/get/search/xref/group)
    schema.sql           DDL
  services/
    hgnc_service.py      orchestration over repository (+ optional live fallback)
    shaping.py           response_mode projection
  mcp/
    facade.py            create_hgnc_mcp()
    envelope.py          run_mcp_tool, error taxonomy
    next_commands.py     cmd() + chain builders
    capabilities.py      build_capabilities / project_capabilities
    resources.py         instructions + static strings + hgnc:// resources
    schemas.py           output_schema per typed tool
    annotations.py       READ_ONLY_OPEN_WORLD
    arg_help.py          aliases, did_you_mean, tool_signature
    middleware.py        ArgValidationMiddleware
    service_adapters.py  lazy singleton + test hook
    tools/
      discovery.py       get_server_capabilities, get_hgnc_diagnostics
      genes.py           get_gene, search_genes, get_gene_cross_references
      resolve.py         resolve_symbol, resolve_symbols_batch
      xref.py            lookup_by_xref
      groups.py          get_gene_group
server.py                unified entry (hgnc-link)
mcp_server.py            stdio entry (hgnc-link-mcp)
```

## 4. Tool surface (MCP)

1. **get_server_capabilities**(detail=summary|full) — discovery.
2. **get_hgnc_diagnostics**() — DB release date, build time, counts, freshness,
   data-source status (like clingen/gnomad diagnostics).
3. **resolve_symbol**(query, response_mode) — *the killer tool*. Accepts a symbol
   (case-insensitive), an HGNC ID (`HGNC:1100` or `1100`), or an alias/previous
   symbol. Returns `{query, hgnc_id, approved_symbol, match_type
   (hgnc_id|current|previous|alias|withdrawn), ambiguous, candidates[...]}`. A
   withdrawn/merged symbol returns the redirect target(s) and `next_commands`
   straight to the live gene. Never silently picks on ambiguity.
4. **resolve_symbols_batch**(queries[], response_mode) — batch resolution
   (sysndd/kidney use this constantly); returns one resolution per input.
5. **get_gene**(query, response_mode) — full record by HGNC ID or symbol.
6. **search_genes**(query, limit, response_mode) — FTS free-text / fielded search;
   returns ranked `{hgnc_id, symbol, name, locus_type, score}`.
7. **get_gene_cross_references**(query, databases?, response_mode) — hgnc_id/symbol
   → external IDs (entrez, ensembl, uniprot, omim, refseq, mane_select, ucsc,
   vega, ccds, mgd, rgd, ...). Forward identifier mapping.
8. **lookup_by_xref**(source, value, response_mode) — reverse mapping: external ID
   (e.g. `ensembl_gene_id=ENSG00000157764`, `entrez_id=673`) → gene.
9. **get_gene_group**(group, response_mode, limit) — gene family/group browse by
   `gene_group_id` or name → member genes.

All tools: `READ_ONLY_OPEN_WORLD`, `output_schema`, `response_mode ∈
{minimal,compact,standard,full}` (default compact), every response carries
`_meta.next_commands` (`{tool, arguments}`) on success **and** error.

Resources: `hgnc://capabilities`, `hgnc://tools`, `hgnc://usage`,
`hgnc://reference`, `hgnc://research-use`, `hgnc://citation`.

## 5. Error taxonomy

`invalid_input`, `not_found`, `ambiguous_query`, `data_unavailable` (DB not built),
`rate_limited` (live fallback only), `upstream_unavailable` (live fallback only),
`internal_error`. Errors are **returned** (not raised) by `run_mcp_tool`;
`mask_error_details=True`. `not_found` for a withdrawn symbol carries
`obsolete:true` + `replaced_by` + a redirect `next_commands`.

## 6. Testing

- **Unit** (no network): `parser`, `builder`/`repository` against a tiny fixture
  DB built from sample records, `shaping`, `arg_help`, `next_commands`,
  `capabilities`, `exceptions`, `envelope`, and **end-to-end tool calls through the
  real FastMCP facade** with a fixture-backed service (reading
  `structured_content`). `respx` for the REST client error mapping.
- **Integration** (`-m integration`, opt-in): hits the real GCS download + live
  REST API; asserts known truths (`BRAF` → `HGNC:1097`, prev `CPAMD9` → `A2ML1`).
- Coverage gate `fail_under=80`.

## 7. Cron / deployment

- `hgnc-link-data refresh` is the cron entry point. Ships:
  - `docs/deployment.md` with a crontab line (`17 3 * * * .../hgnc-link-data refresh`)
    and a systemd `.service` + `.timer` pair.
  - Docker: `docker-compose.yml` runs the server; a companion one-shot service /
    documented cron runs the refresh. `auto_bootstrap=true` builds the DB on first
    start if absent (non-fatal — tools report `data_unavailable` until ready).
- Optional in-process scheduler exists but defaults **off** (`HGNC_LINK_REFRESH_ENABLED=false`)
  since cron is the chosen mechanism.

## 8. Non-goals (YAGNI)

No write/curation endpoints, no VGNC ortholog tools (v1), no coordinate-range
queries (HGNC has only cytoband strings), no BioMart, no per-locus filtered-file
ingest (the complete set covers it). These can be added later.
