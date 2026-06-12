# AGENTS.md — engineering conventions for hgnc-link

Guidance for AI agents and contributors working in this repo. `hgnc-link` is a
sibling of `uniprot-link`, `gnomad-link`, `gencc-link`, `clingen-link`; keep it
consistent with those.

## Golden rules

1. **Run the gate before claiming done:** `make ci-local`
   (format-check → lint → line-budget → mypy strict → tests). All must pass.
2. **Per-file line budget: 500 lines** (`make lint-loc`). Split modules that grow.
3. **mypy is strict.** Fully type new code; no untyped defs.
4. **stdout is sacred on stdio.** Logs go to stderr; never `print` to stdout in
   server/library code (the CLI is the only place `print` is allowed).

## Architecture invariants (do not break)

- **Service returns plain dicts; the MCP layer owns the envelope.**
  `mcp/envelope.run_mcp_tool` injects `success`/`_meta` and converts exceptions
  into typed error dicts (returned, never raised). `mask_error_details=True`.
- **Every response carries `_meta.next_commands`** (`{tool, arguments}`) on
  success **and** error. Build chains in `mcp/next_commands.py`.
- **Error taxonomy:** `invalid_input`, `not_found`, `ambiguous_query`,
  `data_unavailable`, `rate_limited`, `upstream_unavailable`, `internal_error`.
  Add a new code in `envelope._classify` + `capabilities.error_codes` together.
- **`response_mode`** ∈ `minimal|compact|standard|full` (default `compact`);
  `standard`/`full` are identity in `services/shaping.py`.
- **Every typed tool declares `output_schema`** (`mcp/schemas.py`) and
  `annotations=READ_ONLY_OPEN_WORLD`. A test asserts this.
- **Tool description first sentence is the discovery summary;** end it with an
  explicit `Signature: tool(args...)`.
- **Argument aliases** live in `mcp/arg_help.py`; the middleware applies them and
  reshapes binding errors. Keep `capabilities.TOOLS` in sync with registered tools
  (a test asserts `tool_count == len(TOOLS)`).

## Data plane

- The local SQLite index is built from the HGNC bulk dumps by `ingest/`. The
  schema is `data/schema.sql`; bump `constants.SCHEMA_VERSION` on incompatible
  changes. Builds are atomic (`os.replace`) under a `fcntl` lock.
- Refresh is **cron-driven** (`hgnc-link-data refresh`); the in-app scheduler is
  off by default. See `docs/deployment.md`.
- Don't add per-request REST calls to the hot path — query the local index.

## Testing

- Unit tests are network-free and use a fixture index built from
  `tests/fixtures_genes.json` + `tests/fixtures_withdrawn.txt` (see `conftest.py`).
  Mock HTTP with `respx`. Coverage gate: 80%.
- Live tests are `@pytest.mark.integration` (opt-in: `make test-integration`).
- Call tools through the **real facade** and read `structured_content`.

## Adding a tool

1. Service method in `services/hgnc_service.py` (returns a plain dict).
2. `output_schema` in `mcp/schemas.py`; chain builder in `mcp/next_commands.py`.
3. Tool in `mcp/tools/<area>.py` (register fn), exported from `tools/__init__.py`,
   wired in `mcp/facade.py`.
4. Add to `capabilities.TOOLS`; add unit + e2e tests.
