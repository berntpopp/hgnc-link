# CLAUDE.md

This file guides Claude Code when working in this repository.

**Read [`AGENTS.md`](AGENTS.md) first** — it holds the engineering conventions,
architecture invariants, and the definition of done. They apply in full here.

## TL;DR

- Run `make ci-local` before claiming anything is done (format, lint, line
  budget, mypy strict, tests — all must pass).
- The server is backed by a **local SQLite index** built from the HGNC bulk
  dumps and refreshed by **cron** (`hgnc-link-data refresh`). Query the index,
  not the live REST API, on the hot path.
- Service layer returns plain dicts; the MCP layer (`mcp/envelope.py`) owns the
  `success`/`_meta` envelope and the error taxonomy. Errors are returned, not
  raised. Every response carries `_meta.next_commands`.
- Keep `mcp/capabilities.TOOLS` in sync with the registered tools.
- Files stay under 500 lines; logs go to stderr (never `print` to stdout in
  server/library code).

## Common commands

```bash
make install          # uv sync --group dev
make data             # build the local HGNC index
make dev              # unified REST + MCP server (127.0.0.1:8000/mcp)
make test             # unit tests
make ci-local         # full local gate
make test-integration # live HGNC tests (opt-in)
```

## Layout

`hgnc_link/{config,exceptions,logging_config,buildinfo,constants,identifiers}.py`
· `ingest/` (download→build SQLite) · `data/` (schema + read-only repo) ·
`services/` (resolution cascade + shaping) · `api/` (live REST fallback) ·
`mcp/` (envelope, next_commands, capabilities, middleware, tools, facade) ·
`server.py` / `mcp_server.py` (entry points).
