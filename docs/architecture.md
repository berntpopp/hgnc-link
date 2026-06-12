# Architecture

`hgnc-link` follows the shared `*-link` MCP-server architecture (FastAPI +
FastMCP unified server, typed error envelope, `{tool, arguments}` chaining,
capabilities-as-resource), with a **bulk-ingest data plane** for HGNC.

## Layers

```
                      ┌──────────────────────────────────────────────┐
   cron / CLI ──────► │ ingest/  download (cond. GET) → build SQLite  │
                      │          (atomic os.replace swap)             │
                      └───────────────┬──────────────────────────────┘
                                      │  data/hgnc.sqlite
                      ┌───────────────▼──────────────────────────────┐
                      │ data/repository.py  (read-only SQLite)        │
                      └───────────────┬──────────────────────────────┘
                      ┌───────────────▼──────────────────────────────┐
   live REST  ──────► │ services/hgnc_service.py  (resolution cascade,│
   (fallback)         │          xref, search, groups) → plain dicts  │
                      └───────────────┬──────────────────────────────┘
                      ┌───────────────▼──────────────────────────────┐
                      │ mcp/  envelope · next_commands · capabilities │
                      │       middleware · tools → FastMCP facade     │
                      └───────────────┬──────────────────────────────┘
   server.py ─────────────────────────┴── FastAPI (/health) + MCP (/mcp)
```

## Data plane (ingest → SQLite)

- **`ingest/downloader.py`** — conditional GET (ETag/Last-Modified) of
  `hgnc_complete_set.json` + `withdrawn.txt`; a `304` skips the rebuild.
- **`ingest/parser.py`** — normalizes records (multi-value fields → lists) and
  derives the exploded index rows.
- **`ingest/builder.py`** — builds a temp SQLite (`data/schema.sql`), loads the
  tables + FTS5, writes `meta`, then atomically `os.replace`s it. A `fcntl`
  build lock (`ingest/lock.py`) serializes concurrent builds.
- **`ingest/cli.py`** — the `hgnc-link-data` CLI (`build`/`refresh`/`status`),
  the cron entry point.

### Schema

| table | purpose |
|-------|---------|
| `gene` | one row per approved record; list fields as JSON text |
| `symbol_lookup` | exploded `(lookup_symbol, hgnc_id, symbol_type)` — the resolver index |
| `xref` | `(source, value_upper, value, hgnc_id)` for reverse mapping |
| `gene_group` | `(group_id, group_name, hgnc_id)` for family browse |
| `withdrawn` | retired-ID → successor redirects |
| `gene_fts` | FTS5 over symbol/name/alias/previous |
| `meta` | single-row build provenance (release, etag, counts) |

## Query plane

- **`data/repository.py`** — read-only `sqlite3` (mode=ro); resolution, search
  (FTS with `LIKE` fallback), xref, group queries.
- **`services/hgnc_service.py`** — the resolution cascade
  (`HGNC id → current → previous → alias → withdrawn redirect`), cross-reference
  mapping, search, and group browse. Returns plain dicts; surfaces ambiguity and
  withdrawals rather than collapsing them. Optional `api/client.py` REST fallback
  when the index is not yet built.

## MCP plane

Identical to the sibling servers: `envelope.run_mcp_tool` injects
`success`/`_meta` on success and returns a typed error dict on failure
(`mask_error_details=True`); `next_commands.cmd()` builds `{tool, arguments}`
chains present on success **and** error; `middleware.ArgValidationMiddleware`
turns bad argument names/types into the `invalid_input` envelope and applies
argument aliases; `capabilities` projects a summary/full discovery surface and
registers the `hgnc://` resources.

## Server plane

`server.py` (unified/http/stdio) and `mcp_server.py` (stdio) mirror the sibling
entry points. The FastAPI lifespan (`app.py`) bootstraps the index in a worker
thread on startup (non-fatal) and optionally starts the in-process refresh loop
(off by default — cron is preferred).
