# HGNC-Link MCP — Excellence Pass v2 (design)

**Date:** 2026-06-12

> Historical record

**Author:** MCP engineering (autonomous, goal-driven)
**Driver:** `MCP-ASSESSMENT-2026-06-12-live.md` (independent live re-run, scored 8.5 UX / 7 tester)
**Target:** > 9.5 / 10 on a re-run, grounded in 2026 MCP best practices.

---

## 0. Ground truth (investigation result — read this first)

The live assessment was run against a **stale running server**, not the committed
code. Reproduced live during this pass:

| Probe | Live (stale server) | Committed code (read + tests) |
|---|---|---|
| `resolve_symbol("p65")` | 💥 `Output validation error: None is not of type 'string'` | Raises `AmbiguousQueryError` → clean `ambiguous_query` envelope (`services/hgnc_service.py:127`). `RESOLVE_SCHEMA` fields are already `_STR_NULL`. |
| `get_gene_cross_references("PKD1", databases=["mane"])` | `database_count:0, success:true` (silent) | `_resolve_xref_filter` maps `mane`→`mane_select`; unknown tokens raise `invalid_input` + did‑you‑mean (`hgnc_service.py:394`). |
| `build` provenance | `git_sha:"unknown"`, `built_at:null` | `buildinfo.build_info()` resolves sha from `.git` + `built_at` from mtime. |

The running server's own `resolve_symbol` **description** still reads "is flagged
ambiguous" (the pre-fix contract), confirming it predates commit `0fb40ad`
("fix(resolve): ambiguity returns structured ambiguous_query error"). The prior
"MCP excellence pass" (commits `0fb40ad`…`a371375`) already closed the original
findings #1–#6.

**Conclusion:** the blocker and findings #2/#4/provenance are **code-complete**.
This pass (a) **locks them with regression tests** so they can never silently
regress, (b) closes the **residual polish gaps** that remain even in the fixed
code, (c) **reconciles** the two assessment reports, and (d) ensures the
**deployed** server picks up the fix.

---

## 1. Goals & non-goals

**Goals**
- Make every claim in the assessment provably handled by a test (regression lock).
- Close the residual gaps that keep dimensions below 9.5: argument-alias honesty,
  cross-reference verbosity tiers, batch `maxItems`, gene-group pagination,
  search-semantics documentation, build-provenance verification.
- Reconcile `MCP-ASSESSMENT.md` ↔ `MCP-ASSESSMENT-2026-06-12-live.md`.
- Ship green `make ci-local` (format, lint, 500-line budget, mypy strict, tests, ≥80% cov).

**Non-goals**
- No new tools, no schema redesign, no live-API hot-path changes.
- No disease/phenotype search semantics (documented as out of scope, not built).
- No relaxing of `additionalProperties:false` — 2026 MCP guidance keeps input
  schemas strict; we resolve the alias finding by honesty, not by loosening.

---

## 2. Design decisions (grounded)

### D1 — Blocker & sibling correctness: lock, don't re-fix
The ambiguous-success path already returns an `ambiguous_query` error envelope
(not null identity fields). 2026 structured-output guidance: *every result must
conform to `outputSchema`*; an error envelope is the cleanest conformant shape for
"no single answer." **Action:** add regression tests through `resolve_symbol`
itself (not a sibling) on an ambiguous fixture symbol, asserting `success:false`,
`error_code:"ambiguous_query"`, a `candidates` list, and `next_commands` to each
candidate — and that **no** output-validation error is raised.

### D2 — Withdrawn/merged through `resolve_symbol` (coverage gap)
The assessment never reached a true `Entry Withdrawn`/`Merged/Split` record, so the
withdrawn-redirect contract is unverified end-to-end and shares the null-identity
risk class. **Action:** add a withdrawn fixture and assert `resolve_symbol` returns
a `not_found`-class envelope with `obsolete:true` + `replaced_by` + a `next_command`
to the successor — with no schema crash. Mirror through `resolve_symbols_batch`
(inline `obsolete:true` entry, batch never fails).

### D3 — `databases=` filter: lock the reject/synonym behavior
Already validates. **Action:** regression tests that `["mane"]`→`mane_select`
(non-empty), `["MANE Select"]` (label) works, and `["bogus_db"]`→`invalid_input`
with `allowed_values` + a did-you-mean hint. Parity with `lookup_by_xref(source=)`.

### D4 — Cross-reference verbosity tiers (finding #4, done properly)
Today `get_cross_references` ignores `response_mode` and returns *all* populated
xrefs in every tier — which fixes the original "compact too stingy" complaint but
makes `response_mode` **inert** for this tool (a new small inconsistency a sharp
reviewer will catch) and forfeits token control. **Action:** make the tiers
meaningful and never stingy:
- `minimal` → anchor ids only: `entrez_id`, `ensembl_gene_id`.
- `compact` (default) → high-value set: `entrez_id`, `ensembl_gene_id`,
  `uniprot_ids`, `refseq_accession`, `mane_select`, `omim_id`, `ccds_id`
  (explicitly **includes** MANE/UniProt/OMIM — the finding-#4 fields).
- `standard` / `full` → all populated xref fields.
A `databases=` filter overrides the tier (explicit request wins). Document the
per-tier field set in the tool description and `hgnc://capabilities`.

### D5 — `resolve_symbols_batch.queries` → schema `maxItems:200`
The 200-cap is server-only today; `search_genes.limit`/`get_gene_group.limit` are
schema-capped. **Action:** add `max_length=200` to the `queries` Field so FastMCP
emits `maxItems:200`; keep the server-side check as the backstop (and as the
friendly `invalid_input` for non-strict clients).

### D6 — Gene-group pagination (truncation made explicit)
`get_gene_group(654, limit=3)` returns `member_count:24, returned:3` with no
truncation signal. 2026 pagination guidance: caps + a continuation token + an
explicit "more" signal. **Action:** add an `offset` parameter (default 0,
`maxItems`-style `ge=0`), and return `truncated: bool`, `offset`, and `next_offset`
(null when exhausted). When `truncated`, append a `next_commands` entry that
re-calls `get_gene_group` with the next `offset`. Update `GENE_GROUP_SCHEMA`.

### D7 — Argument aliases: honest contract (finding #3)
2026 best practice keeps `inputSchema` strict (`additionalProperties:false`)
precisely so unexpected params are rejected — and the assessment *praised* the
server's did-you-mean on bad names. We therefore **do not** bloat schemas with
alias properties. Instead we make the advertisement truthful: in capabilities,
present `argument_aliases` with an explicit note that they are **server-side
synonyms** accepted *in addition to* the canonical parameter, that
schema-strict clients should pass the canonical name shown in `tool_signatures`,
and that unknown names return `invalid_input` + did-you-mean. Server-side alias
resolution (middleware) stays — it is genuinely useful and disclosed via
`_meta.argument_aliases_applied`.

### D8 — Search is nomenclature-only (documentation)
`search_genes` is FTS over symbol/name/alias/previous — no disease/phenotype
semantics (e.g. "polycystin kidney" won't surface PKD1). **Action:** state this in
the tool description and add a `search_semantics` note to capabilities.

### D9 — Build provenance verification
`build_info()` is already wired; the stale server showed `unknown/null`. **Action:**
add a unit test asserting `build_info()` returns a non-empty `version` and a
`git_sha`/`built_at` that are populated when `.git` (or env override) is present,
and that `build_capabilities()["build"]` carries them through. Confirm the Docker
build args flow (already added in `a371375`).

### D10 — Reconcile the two reports & refresh the deployed server
Add a short reconciliation note (committed `MCP-ASSESSMENT.md` "inert response_mode"
vs live "schema crash" = stale build), and document the operational step: the
running MCP server is launched from this source tree, so a **client restart**
picks up the fix; reinstall (`make install`) to be safe. Update `CHANGELOG.md`.

---

## 3. Components touched

| File | Change |
|---|---|
| `services/hgnc_service.py` | D4 xref tier projection (helper); D6 group `offset`/`truncated`. Watch 500-line budget — extract a `_project_xrefs` helper if needed. |
| `mcp/schemas.py` | D6 `GENE_GROUP_SCHEMA`: add `truncated`, `offset`, `next_offset`. |
| `mcp/tools/resolve.py` | D5 `queries` `max_length=200`. |
| `mcp/tools/groups.py` | D6 `offset` param + description. |
| `mcp/tools/genes.py` | D4 cross-ref description (per-tier fields); D8 search note. |
| `mcp/next_commands.py` | D6 `after_group` appends next-page command when truncated. |
| `mcp/capabilities.py` | D4 xref tiers, D7 alias note, D8 search semantics. |
| `tests/` | D1–D9 regression tests; withdrawn fixture (D2). |
| `MCP-ASSESSMENT.md`, `CHANGELOG.md`, assessment-live doc | D10 reconciliation. |

## 4. Error handling
Unchanged taxonomy. All new branches return the standard envelope via
`run_mcp_tool`. New invalid inputs (e.g. negative `offset`) surface through the
existing `ArgValidationMiddleware` did-you-mean/constraint path.

## 5. Testing strategy
TDD per change: write the failing assertion against the **real facade**
(`structured_content`), then implement. Add an ambiguous + a withdrawn fixture to
`tests/fixtures_genes.json` / `tests/fixtures_withdrawn.txt`. Keep coverage ≥80%.
Final gate: `make ci-local`.

## 6. Rollout
1. Land code + tests (green `ci-local`).
2. `make install` to refresh the installed entrypoint.
3. Note in CHANGELOG that a Claude Code / MCP client restart is required for the
   live server to reflect the fix (the stale instance is why the live re-run failed).
4. Re-probe the four assessment scenarios through the live tools to confirm.
