# HGNC-Link MCP — Excellence Pass Design (target ≥ 9.5/10)

> Historical record

> Driven by `MCP-ASSESSMENT.md` (external black-box LLM-consumer evaluation,
> 2026-06-12). That assessment scored the server **8/10 (UX)** / **7.5 (tester)**,
> gated by one critical bug and one high-severity silent-failure trap. This design
> closes every finding (critical → polish) without redesigning the architecture,
> and tightens the contract so the server is self-consistent across all 9 tools.

## Goals & non-goals

**Goal:** raise the server to genuinely excellent (≥ 9.5/10) by fixing all six
findings, while preserving the architecture invariants in `AGENTS.md` (service
returns plain dicts; MCP layer owns the envelope; errors returned not raised;
every response carries `_meta.next_commands`; files < 500 lines; mypy strict).

**Non-goals:** no schema-version bump, no new tools, no live-API hot path, no
refactor unrelated to the findings. The local SQLite + cron architecture stays.

## Findings → fixes (traceability)

| # | Sev | Tool | Fix (this design) |
|---|-----|------|-------------------|
| 1 | Critical | `resolve_symbol` | Ambiguity flows through `AmbiguousQueryError` → structured `ambiguous_query` error (D1) |
| 2 | High | `get_gene_cross_references` | `databases` filter normalizes friendly labels and rejects unknown keys loudly (D2) |
| 3 | Medium | `search_genes`, `get_gene` | Invalid-**value** errors surface valid range/enum, not arg names (D3) |
| 4 | Medium | docs vs impl | One documented ambiguity contract; single-tool=error, batch=inline, both documented (D1+D8) |
| 5 | Low–Med | `resolve_symbol` | `response_mode` honored; redundant `candidates` removed on success (D4) |
| 6 | Low | `resolve_symbol` | Cross-tier alternatives surfaced as lean `other_matches` (D5) |
| P1 | Polish | observability | Build provenance non-empty (git sha + built_at) in dev and prod (D7) |
| P2 | Polish | `resolve_*` | Cross-tool hint: external id → `lookup_by_xref` suggestion (D6) |

## Design decisions

### D1 — Ambiguity is a structured `ambiguous_query` error on single-result tools

**Root cause of the crash:** `resolve()` returned a *success* dict with
`hgnc_id: null` on ambiguity, but `RESOLVE_SCHEMA` types `hgnc_id` as a
non-nullable `string`. FastMCP's structured-output validator rejected the whole
response → `Output validation error: None is not of type 'string'`. The service
layer was correct; the MCP boundary was not.

**Decision (assessment option B):** `resolve()` raises `AmbiguousQueryError`
(candidates attached) on true within-tier ambiguity — exactly like
`_resolve_to_gene` already does for `get_gene`/`get_gene_cross_references`. The
existing envelope path then emits `success:false, error_code:"ambiguous_query",
candidates:[…], recovery_action:"reformulate_input"` with `next_commands` =
`get_gene` per candidate.

**Why B over "just make the schema nullable" (option A):**
- All three single-result tools (`resolve_symbol`, `get_gene`,
  `get_gene_cross_references`) become identical on ambiguity. Today only
  `resolve_symbol` is the outlier — the other two already raise. Unifying them is
  the decisive consistency win.
- Matches the **documented** contract (`capabilities.not_found_contract` +
  taxonomy already say ambiguity → `ambiguous_query`). This resolves finding #4.
- Reuses tested machinery (`AmbiguousQueryError` already carries candidates and
  builds candidate `next_commands`).

**Defense-in-depth:** we *also* make `RESOLVE_SCHEMA`'s gene-identity fields
nullable (`["string","null"]`). After D1 no success payload carries a null
`hgnc_id`, but a nullable schema permanently forecloses this class of bug.

**Batch keeps inline ambiguity (D8):** `resolve_symbols_batch` must not fail the
whole call on one ambiguous item, so it catches `AmbiguousQueryError` and appends
a rich inline entry `{query, hgnc_id:null, ambiguous:true, match_type,
candidate_count, candidates, note}`. This preserves the behavior the assessment
praised ("handles the ambiguous case the single tool cannot"). The single-vs-batch
distinction is **intentional and documented**, not an inconsistency.

### D2 — Forgiving-and-loud `databases` filter

`get_gene_cross_references(query, databases=["mane"])` returned
`database_count:0, success:true` — a silent wrong-looking empty, because the
filter only matched exact internal field keys (`mane_select`), not the friendly
label `"mane"`, and never rejected nonsense like `"bogus_db"`.

**Decision:** add `XREF_FILTER_ALIASES` to `constants.py` — a friendly
label/synonym → canonical field-key map covering **every** `XREF_FIELDS` entry
(e.g. `mane`/`mane select` → `mane_select`, `ncbi`/`gene_id` → `entrez_id`,
`mim` → `omim_id`). The service normalizes each requested database through it:
- recognized → resolved to its field key;
- unrecognized → raise `InvalidInputError(field="databases",
  allowed=<canonical field keys>, hint=<did-you-mean + examples>)`.

A recognized-but-absent database (the gene genuinely lacks it) still returns a
legitimate `database_count:0, success:true` — that is a true empty, not a trap.

### D3 — Invalid-**value** errors surface the valid range/enum

`search_genes(limit=250)` and `get_gene(response_mode="verbose")` reused the
invalid-argument-**name** template, listing parameter *names* in `allowed_values`.

**Decision:** keep pydantic validation (do **not** silently clamp — a clear,
actionable error beats hidden coercion for an LLM consumer). Make the middleware
value-aware: when the failing `loc` is a real parameter (a *value* error, not a
*name* error), read that field's JSON-schema constraints and surface them:
- enum field (`response_mode`) → `allowed_values=[minimal,compact,standard,full]`,
  message "must be one of …";
- bounded int (`limit`) → message "must be between 1 and 200",
  `allowed_values=["1..200"]`.

Name errors (unknown argument) keep listing valid parameter names + did-you-mean.
A new pure helper `describe_constraints(field_schema)` in `arg_help.py` extracts
`enum` / `minimum` / `maximum` (digging through `anyOf`/`allOf`).

### D4 — `response_mode` honored on `resolve_symbol`; redundant candidates removed

On an *unambiguous* resolution the payload carried a `candidates` array whose sole
entry duplicated the top-level identity (~40% waste), and `minimal`/`compact`/
`full` were byte-identical.

**Decision:** add `shape_resolution(record, mode)` to `services/shaping.py`.
`resolve()` builds one canonical success dict
`{query, hgnc_id, approved_symbol, name, status, locus_type, location,
match_type, ambiguous:false, [other_matches]}` — **no** `candidates`/
`candidate_count` (the gene *is* the answer; there is nothing to disambiguate).
Projection:
- `minimal` → `{query, hgnc_id, approved_symbol, match_type}`;
- `compact` → adds name/status/locus_type/location/ambiguous (+ other_matches if
  present), dropping null/empty;
- `standard`/`full` → the full dict (identity is small; no point trimming).

### D5 — Cross-tier alternatives surfaced (`other_matches`)

A symbol matched in the top tier with a single hit (e.g. a *previous* symbol for
an obscure gene) silently hid that the same token is an *alias* of a different,
likely-intended gene (the `TRP1` case).

**Decision:** when the winning tier has exactly one member **and** lower-tier
rows point at *other* genes, attach a lean `other_matches` list — brief entries
`{hgnc_id, symbol, symbol_type}`, deduped, excluding the resolved gene. Present
only when non-empty; excluded from `minimal`. This costs nothing in the common
case (most symbols have no cross-tier alternative) and gives the LLM the signal it
needs in the rare one.

### D6 — Cross-tool xref hint (`resolve_*` → `lookup_by_xref`)

An Ensembl/UniProt/RefSeq id thrown at `resolve_symbol`/`resolve_symbols_batch`
returned a bare `not_found`/`unresolved`, though `lookup_by_xref` resolves it
instantly.

**Decision:** add `infer_xref_source(value)` to `identifiers.py`
(`ENSG…`→`ensembl_gene_id`, `ENST…`→`ensembl`, UniProt accession→`uniprot`,
`NM_/NP_/NR_/XM_…`→`refseq`). Wire it in:
- `next_commands.default_error_next_commands` for `resolve_symbol`/`get_gene`
  not-found → prepend `cmd("lookup_by_xref", source=…, value=…)`;
- `resolve_batch` unresolved entries → add a `hint` string.

### D7 — Build provenance non-empty (observability)

`git_sha:"unknown"`, `built_at:null` because the env vars are only injected in the
Docker image. **Decision:** make `build_info()` resilient:
- `git_sha`: env `HGNC_LINK_GIT_SHA` → else a dependency-free `.git/HEAD`
  resolver (loose ref → packed-refs → detached sha), truncated to 12 → else
  `"unknown"`;
- `built_at`: env `HGNC_LINK_BUILT_AT` → else ISO mtime of the package
  `__init__.py` → else `null`.

Also wire Docker build args so production images stamp real values
(`HGNC_LINK_GIT_SHA`, `HGNC_LINK_BUILT_AT`). No stdout writes; no new deps.

## Components touched

- `hgnc_link/constants.py` — `XREF_FILTER_ALIASES`.
- `hgnc_link/identifiers.py` — `infer_xref_source`.
- `hgnc_link/services/shaping.py` — `shape_resolution`.
- `hgnc_link/services/hgnc_service.py` — `resolve()` raises on ambiguity + builds
  canonical dict + `other_matches`; `resolve_batch()` inline-ambiguity + hint;
  `get_cross_references()` normalizes/validates `databases`.
- `hgnc_link/mcp/schemas.py` — nullable identity fields on `RESOLVE_SCHEMA`.
- `hgnc_link/mcp/arg_help.py` — `describe_constraints`.
- `hgnc_link/mcp/envelope.py` + `mcp/middleware.py` — value-aware arg-error envelope.
- `hgnc_link/mcp/next_commands.py` — xref hint in error next_commands.
- `hgnc_link/buildinfo.py` — robust provenance.
- `hgnc_link/mcp/capabilities.py` — documented ambiguity contract + (optional)
  `cross_reference_filter_aliases` discovery.
- `docker/Dockerfile` — build-arg provenance injection.
- Docs: `MCP-TEST-REPORT.md` / `CHANGELOG.md` note.

## Testing strategy (TDD, per finding)

Network-free unit + e2e through the **real facade** (per AGENTS.md). Fixtures get
three added genes to create the missing scenarios:
- a shared alias across two genes → **ambiguity** (drives the critical
  MCP-layer regression: `resolve_symbol(<ambig>)` must return
  `success:false, error_code:"ambiguous_query"`, never crash);
- a token that is a *previous* symbol of one gene and an *alias* of another →
  **cross-tier** `other_matches`.
Count-dependent assertions (`gene_count == 5` in 4 tests) updated to the new total.

New/updated tests cover: ambiguous single-tool error + batch inline + schema
validates (no crash); friendly-label xref filter works + unknown key errors;
limit/response_mode value errors show range/enum; resolve response_mode trims +
no candidates on success; other_matches surfaced; infer_xref_source + hint;
build_info fallback. Gate: `make ci-local` (format, lint, line-budget, mypy
strict, tests, ≥ 80% cov).

## Risks

- **Contract change:** `resolve_symbol` now returns an *error* on ambiguity
  (was a crash). Existing service-level test `test_ambiguous_alias` is updated to
  expect the exception — intentional. No external consumer depended on the crash.
- **Schema rendering for `describe_constraints`:** pydantic/FastMCP may wrap the
  `Literal` enum under `anyOf`/`allOf`; the helper digs through both and is unit
  tested against the live tool schema.
