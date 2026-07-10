# hgnc-link

An MCP (Model Context Protocol) + HTTP server that grounds **gene-nomenclature**
work in the **HUGO Gene Nomenclature Committee (HGNC)** dataset from
[genenames.org](https://www.genenames.org/).

It is a sibling of `uniprot-link`, `gnomad-link`, `gencc-link`, `clingen-link`,
etc., and shares their architecture: a FastAPI + FastMCP unified server, a typed
error envelope, `{tool, arguments}` chaining via `_meta.next_commands`, and
capabilities-as-resource discovery.

## Why

Every downstream genetics tool needs the same thing from HGNC: turn *any* gene
symbol — current, outdated (previous), or alias — and *any* HGNC ID form into the
canonical `{hgnc_id, approved_symbol}`, then pull cross-references. `hgnc-link`
makes that a single fast call, with the match provenance and any ambiguity made
explicit instead of silently collapsed.

## Speed: local index, refreshed by cron

For speed and reliability the server is backed by a **local SQLite index** built
from HGNC's **bulk downloads** (`hgnc_complete_set.json` + `withdrawn.txt`) and
refreshed by a **cron-invoked CLI** — no per-request REST round-trips. The live
`rest.genenames.org` API is used only as an optional fallback before the first
build completes.

```bash
# Build the index once (downloads ~33 MB, builds in seconds):
uv run hgnc-link-data build

# Cron entry point — conditional refresh (304-cheap; rebuilds only on change):
uv run hgnc-link-data refresh

# Inspect the loaded release:
uv run hgnc-link-data status
```

See [`docs/deployment.md`](docs/deployment.md) for a crontab line and a systemd
timer.

## Tools

| Tool | Purpose |
|------|---------|
| `get_server_capabilities` | Discovery surface (tools, signatures, workflows, vocab). |
| `get_hgnc_diagnostics` | Loaded release, counts, freshness, data-source status. |
| `resolve_symbol` | Any symbol/ID → `{hgnc_id, approved_symbol, match_type}` + candidates. |
| `resolve_symbols_batch` | Resolve many symbols/IDs at once (never fails on a miss). |
| `get_gene` | Full HGNC record (alias/previous aware). |
| `search_genes` | FTS over symbol/name/alias/previous symbols. |
| `get_gene_cross_references` | Gene → NCBI/Ensembl/UniProt/RefSeq/MANE/OMIM/… |
| `resolve_gene_by_xref` | External ID → HGNC gene (reverse mapping). |
| `get_gene_group` | Browse a gene family by group ID or name. |

Every response carries `_meta.next_commands` (a ready-to-call `{tool, arguments}`
list) on success **and** error. Response verbosity is controlled by
`response_mode ∈ {minimal, compact, standard, full}` (default `compact`).

**Federation:** the `serverInfo.name` is `hgnc-link`, and leaf tool names are
intentionally unprefixed per the GeneFoundry Tool-Naming Standard v1. The
canonical gateway **namespace token** is `hgnc`; when federated behind
`genefoundry-router`, tools surface as `hgnc_<tool>` (e.g. `hgnc_resolve_symbol`,
`hgnc_resolve_gene_by_xref`).

## Quick start

```bash
make install          # uv sync --group dev
make data             # build the local HGNC index
make dev              # unified REST + MCP server on http://127.0.0.1:8000/mcp
make mcp-serve        # stdio MCP server (Claude Desktop)
make test             # unit tests
```

HTTP deployments enforce exact Host and Origin allowlists. Configure
`HGNC_LINK_ALLOWED_HOSTS` as a JSON list containing the public reverse-proxy
hostname in addition to loopback defaults; `HGNC_LINK_ALLOWED_ORIGINS` defaults
to `[]`, which permits requests without an `Origin` header. Browser deployments
must list an origin in both `HGNC_LINK_ALLOWED_ORIGINS` and
`HGNC_LINK_CORS_ORIGINS`: request validation and CORS response headers are
separate policies and neither one widens the other.

Register with Claude Code (HTTP):

```bash
claude mcp add --transport http hgnc-link --scope user http://127.0.0.1:8000/mcp
```

Or stdio (Claude Desktop) — see [`claude-desktop-config.json`](claude-desktop-config.json).

## Data & license

HGNC data is released with **no usage restrictions** (effectively CC0).
Attribution is requested: *Seal RL, et al. Genenames.org: the HGNC resources in
2023. Nucleic Acids Res.* RRID:SCR_002827.

**Research use only; not for clinical decision support.**

## Development

```bash
make check        # format + lint
make typecheck    # mypy --strict
make ci-local     # format-check + lint + lint-loc + typecheck + tests
make test-integration   # live HGNC download + REST asserts (opt-in)
```

Architecture details: [`docs/architecture.md`](docs/architecture.md).
Design spec: [`docs/superpowers/specs/2026-06-12-hgnc-link-design.md`](docs/superpowers/specs/2026-06-12-hgnc-link-design.md).
