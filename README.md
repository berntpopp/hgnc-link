# hgnc-link

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/berntpopp/hgnc-link/actions/workflows/ci.yml/badge.svg)](https://github.com/berntpopp/hgnc-link/actions/workflows/ci.yml)
[![Conformance](https://github.com/berntpopp/hgnc-link/actions/workflows/conformance.yml/badge.svg)](https://github.com/berntpopp/hgnc-link/actions/workflows/conformance.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An MCP (Model Context Protocol) server that grounds gene-nomenclature work in the HUGO
Gene Nomenclature Committee (HGNC) dataset from
[genenames.org](https://www.genenames.org/), served from a local index of HGNC's bulk
downloads over Streamable HTTP or stdio.

> [!IMPORTANT]
> Research use only. Not clinical decision support. Do not use for diagnosis,
> treatment, triage, or patient management.

## Why

Every downstream genetics tool needs the same thing from HGNC: turn *any* gene symbol —
current, outdated (previous), or alias — and *any* HGNC ID form into the canonical
`{hgnc_id, approved_symbol}`, then pull cross-references.

HGNC does publish a REST API, but it is **field-scoped** (`/fetch/{field}/{value}`): the
caller must already know whether a string is a current symbol, a previous symbol, an alias
or an ID, and query the matching field — a network round-trip per guess. It will not tell
you *how* a symbol matched, and it will not warn you that an alias belongs to several
genes.

`hgnc-link` collapses that into one local call against a SQLite index of the bulk dumps.
It runs the full cascade (HGNC ID → current → previous → alias → withdrawn redirect),
returns the **match provenance** in `match_type`, and surfaces ambiguity as an
`ambiguous_query` error with the candidate list rather than silently collapsing it to one
gene.

## Quick start

Hosted — no install:

```bash
claude mcp add --transport http hgnc https://hgnc-link.genefoundry.org/mcp
```

Local (Python 3.12+, [uv](https://github.com/astral-sh/uv)). **`make data` is
mandatory** — the server has no data until the HGNC dumps (~33 MB) are downloaded and the
local index is built:

```bash
make install          # uv sync --group dev
make data             # download the HGNC dumps, build the local SQLite index
make dev              # unified REST + MCP on http://127.0.0.1:8000/mcp
make mcp-serve        # ...or a stdio MCP server, for Claude Desktop
```

```bash
claude mcp add --transport http hgnc-link --scope user http://127.0.0.1:8000/mcp
```

For stdio see [`claude-desktop-config.json`](claude-desktop-config.json). Keep the index
fresh with `make data-refresh` from cron — it is conditional, so an unchanged dump costs
one `304` and no rebuild ([Deployment](docs/deployment.md)). Serving over HTTP behind a
proxy requires adding the public hostname to the exact Host allowlist — read
[Configuration](docs/configuration.md) first.

## Tools

| Tool | Purpose |
|------|---------|
| `resolve_symbol` | **Start here.** Any symbol/ID → `{hgnc_id, approved_symbol, match_type}` + candidates. |
| `resolve_symbols_batch` | Resolve many symbols/IDs at once; never fails the batch on a miss. |
| `get_gene` | Full HGNC record for one gene (alias- and previous-symbol aware). |
| `search_genes` | Full-text search over symbol, name, alias and previous symbols. |
| `get_gene_cross_references` | Gene → NCBI / Ensembl / UniProt / RefSeq / MANE / OMIM / … identifiers. |
| `resolve_gene_by_xref` | External ID → HGNC gene (the reverse mapping). |
| `get_gene_group` | Browse a gene family by group ID or name. |
| `get_server_capabilities` | Discovery surface: tools, signatures, workflows, vocabulary. |
| `get_hgnc_diagnostics` | Loaded release, record counts, freshness, data-source status. |

`serverInfo.name` is `hgnc-link`, and leaf tool names are intentionally **unprefixed** per
the GeneFoundry Tool-Naming Standard v1. The canonical gateway namespace token is `hgnc`:
behind [`genefoundry-router`](https://github.com/berntpopp/genefoundry-router) these
surface as `hgnc_<tool>` (e.g. `hgnc_resolve_symbol`).

Every response carries `_meta.next_commands` — a ready-to-call `{tool, arguments}` list, on
success **and** on error — and honours `response_mode ∈ {minimal, compact, standard, full}`
(default `compact`). See [Usage](docs/usage.md).

## Data & provenance

- **Source** — the HGNC bulk downloads (`hgnc_complete_set.json` + `withdrawn.txt`) from
  [genenames.org](https://www.genenames.org/), built into a local SQLite index. Queries are
  served from that index; there are no per-request REST round-trips.
- **Refresh** — HGNC publishes Tuesdays and Fridays. `hgnc-link-data refresh` is the cron
  entry point and is conditional (an unchanged dump returns `304`, so no rebuild); the
  in-app scheduler is off by default. See [Data](docs/data.md).
- **Licence** — HGNC data is released with **no usage restrictions** (effectively public
  domain / CC0). Attribution is requested but not required.
- **Citation** — Seal RL, Braschi B, Gray K, Jones TEM, Tweedie S, Haim-Vilmovsky L,
  Bruford EA. Genenames.org: the HGNC resources in 2023. *Nucleic Acids Res.*
  2023;51(D1):D1003-D1009. doi:10.1093/nar/gkac888. RRID:SCR_002827.

## Documentation

- [Usage](docs/usage.md) — canonical workflows, `response_mode`, chaining, ambiguity and withdrawn-ID semantics, the `hgnc://` resources.
- [Configuration](docs/configuration.md) — every `HGNC_LINK_*` variable, the transports, and the Host / Origin / CORS boundary.
- [Data](docs/data.md) — the bulk dumps, the index build, freshness, and the (unwired) live REST client.
- [Deployment](docs/deployment.md) — cron and systemd refresh, and the Docker path.
- [Architecture](docs/architecture.md) — the ingest → SQLite → service → MCP planes, and the schema.
- [Design spec](docs/superpowers/specs/2026-06-12-hgnc-link-design.md) — why it is shaped this way.

## Contributing

See [`AGENTS.md`](AGENTS.md) for engineering conventions — the error taxonomy, the
`next_commands` contract, and how to add a tool. `make ci-local` is the definition-of-done
gate: format, lint, line budget, README standard, mypy strict, and tests.

## License

[MIT](LICENSE) © hgnc-link contributors. HGNC **data** carries no usage restrictions
(effectively CC0); the attribution cited above is requested but not required.
