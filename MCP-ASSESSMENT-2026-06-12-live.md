# HGNC-Link MCP — Live Assessment (re-run)

> **Scope:** External, black-box evaluation of the `hgnc-link` MCP server as consumed by an LLM client (Claude Code), through the FastMCP facade.
> **Server:** `hgnc-link` v0.1.0 · HGNC release `Fri, 12 Jun 2026 13:01:53 GMT` · local SQLite index (44,997 genes · 5,290 withdrawn · 105,607 symbol-lookup rows).
> **Date:** 2026-06-12
> **Method:** ~60 live tool calls across all 9 tools plus both MCP resources — happy paths, all four `response_mode` tiers, boundaries, abuse inputs (empty / injection / empty-batch / unknown-filter / zero-hit), and every documented contract (ID normalization, case-insensitivity, current→previous→alias cascade, ambiguity, batch fault-tolerance, gene-group browsing, reverse xref).
> **Relationship to other reports:** This is an **independent live re-run**. It contradicts the prior committed `MCP-ASSESSMENT.md` on one material point — see [Discrepancy vs. prior report](#discrepancy-vs-prior-report).

This document contains two assessments:

1. **Part 1 — LLM-consumer UX evaluation** (dimension ratings, 1–10).
2. **Part 2 — Senior-tester report** (the blocker, severity-ranked findings, repros, fixes).

---

## Part 1 — LLM-Consumer UX Evaluation

### Overall: 8.5 / 10

A genuinely well-engineered "link" server — among the better MCPs in circulation. It nails the things that usually go wrong: discovery is rich and self-describing, the error envelope is textbook, provenance is declared once instead of repeated per-call, and the local index makes it fast and offline. Held back by one clear correctness defect (a filter that silently returns nothing) plus two smaller polish items.

| Dimension | Score | Basis (from observed behavior) |
|---|---|---|
| Discoverability | 9 | `get_server_capabilities` returns the tool list **with signatures**, argument aliases, response modes, recommended workflows, error taxonomy, limits, citation, and license; mirrored in `hgnc://capabilities` / `hgnc://tools`. Every response carries `_meta.next_commands`. |
| Token efficiency | 8 | Four `response_mode` tiers (default compact); static provenance declared once via `provenance_policy`; lean per-call `_meta`. Dinged because compact `get_gene_cross_references` omits MANE/UniProt/OMIM, forcing a `full` re-fetch, and the silent-filter bug wastes calls. |
| Speed | 9 | Local SQLite index; every call (including batch) returned promptly; no live API on the hot path. |
| Observability | 8 | `request_id` on **every** response incl. errors; `get_hgnc_diagnostics` reports availability, release, counts, schema version, build time. Dinged because capabilities reports `git_sha:"unknown"`, `built_at:null`. |
| Error handling | 9 | `invalid_input` returns `field` + `allowed_values` + `hint` + `recovery_action` + `retryable` + `next_commands`; clear `not_found`; documented `ambiguous_query` and withdrawn→successor contract. Lone exception: the filter bug. |
| Consistency | 8 | Uniform envelope everywhere — except the `databases=` filter and compact-field policy. |

### Smaller improvements (Part 1)

- **Reconsider compact cross-references.** Compact `get_gene_cross_references` returns only `ensembl` + `refseq` and drops MANE/UniProt/OMIM — high-value, low-token fields users commonly want. Either include them or document which fields compact emits.
- **Populate build provenance.** `git_sha`/`built_at` are empty in the running instance even though the data-build timestamp is populated.

---

## Part 2 — Senior-Tester Report

### Verdict & overall: 7 / 10

Solid architecture (best-in-class discovery, disciplined error taxonomy, `next_commands` chaining, fast offline index), but testing surfaced **one blocker**: the primary tool, `resolve_symbol`, **crashes on ambiguous queries** — exactly the flagship feature it advertises. Fixing that single localized defect would take this to ~9/10.

### Test coverage

| Area | Exercised |
|---|---|
| Tools | all 9 |
| Resources | `hgnc://capabilities`, `hgnc://tools` |
| Response modes | minimal / compact / standard / full |
| ID normalization | `HGNC:1097`, `1097`, `hgnc:1097` → all `match_type:hgnc_id` ✅ |
| Case-insensitivity | `braf` → current ✅ |
| Cascade | current / previous (`MLL2`,`SEPT2`,`MARC1`,…) / alias (`GIG`,`GH`,`CT`) ✅ |
| Ambiguity | tie-at-top-tier detection (`p65`,`ACSM2`,`PP1`,`HCG`) — **crashes in `resolve_symbol`**, clean elsewhere |
| Batch fault-tolerance | mixed valid/miss/ambiguous; never fails whole batch ✅ |
| Reverse xref | `ensembl_gene_id`, `uniprot`(→`uniprot_ids`), `ncbi`(→`entrez_id`), `omim_id` ✅ |
| Gene groups | by id (`1157`,`654`), by name (`RAF family`), ambiguous name (`kinase`→143 candidates) ✅ |
| Abuse | empty query, SQL-ish injection, empty batch, unknown filter, zero-hit search ✅ |
| **Not reached** | a genuine `status:"Entry Withdrawn"/"Merged/Split"` record (`match_type:"withdrawn"`, `obsolete:true`, `replaced_by`) — every renamed symbol resolved via `previous` |

### 🔴 BLOCKER — `resolve_symbol` violates its own output schema on ambiguous input

**Reproduction** (all four fail identically):

```
resolve_symbol(query="p65")    → Output validation error: None is not of type 'string'
resolve_symbol(query="ACSM2")  → Output validation error: None is not of type 'string'
resolve_symbol(query="PP1")    → Output validation error: None is not of type 'string'
resolve_symbol(query="HCG")    → Output validation error: None is not of type 'string'
```

The harness discards the **entire** payload — no `error_code`, no `candidates`, no `next_commands`. The consumer gets nothing and cannot recover.

**Root cause (localized):** on an ambiguous match the handler sets top-level `hgnc_id`/`approved_symbol` to `null` (the same shape the batch tool returns), but `resolve_symbol`'s declared `outputSchema` types those fields as non-nullable strings, so structured-output validation rejects the response. The crash correlates **exactly** with `ambiguous: true` — `candidate_count > 1` alone is fine (`PAP`→8 candidates, `PSP`→6, `MLL2`→2 all succeed because one tier wins and `ambiguous:false`); it breaks only when there's a tie at the top match tier and the IDs go null.

**Sibling tools handle the identical input correctly:**

| Tool | `…("p65")` |
|---|---|
| `resolve_symbol` | 💥 schema crash (payload discarded) |
| `get_gene` | ✅ `ambiguous_query` envelope + 3 candidates (GORASP1 / RELA / SYT1) + `next_commands` to each HGNC id |
| `get_gene_cross_references` | ✅ `ambiguous_query` envelope + candidates |
| `resolve_symbols_batch` | ✅ entry with `hgnc_id:null`, `ambiguous:true`, `candidates[…]`, explanatory `note` |

**Why it matters:** `resolve_symbol` is the documented first step ("resolve first"), and "surfaces ambiguity instead of silently picking" is a headline feature. The one tool meant to express ambiguity is the one that can't. A consumer following the recommended workflow hits a dead end with an opaque error.

**Fix:** make the success-schema fields nullable for the ambiguous branch (mirror the batch entry schema), **or** return ambiguity as an `ambiguous_query` error envelope exactly like `get_gene` does. Add a regression test on an ambiguous symbol — `p65` (alias of GORASP1/RELA/SYT1) is a clean fixture. Error envelopes already validate fine (`invalid_input`/`not_found` were observed passing), so this is isolated to the ambiguous-**success** path.

### 🟠 `get_gene_cross_references(databases=…)` silently ignores unknown filter tokens

`databases=["mane"]` and `databases=["bogus_db_name"]` both return `database_count:0`, `cross_references:{}`, **`success:true`**. The correct key is `mane_select`; `["mane_select"]` works. There is no validation and no synonym mapping on this filter — a natural guess returns a confidently-empty answer (this is what made the first PKD1 MANE lookup come back empty). Inconsistent with `lookup_by_xref`, whose bad `source` correctly returns `invalid_input` + `allowed_values` + hint.

**Fix:** validate `databases` against the known field set; map obvious synonyms (`mane`/`MANE Select`→`mane_select`, `uniprot`→`uniprot_ids`, `mgi`→`mgd_id`) and emit `invalid_input` or a `warnings:[…]` entry for genuinely unknown tokens.

### 🟡 Advertised `argument_aliases` are unreachable through a strict client

Capabilities advertises rich **parameter-name** aliases (`query` accepts `gene`/`symbol`/`id`/`q`/…), but every tool's published `inputSchema` sets `additionalProperties:false` and lists only canonical names, so a schema-validating MCP client rejects an aliased argument before it reaches the server. (Distinct from **value-level** synonyms, which *do* work and are excellent: `lookup_by_xref(source="uniprot")`→`uniprot_ids`, `source="ncbi"`→`entrez_id`.)

**Fix:** add the alias names into each `inputSchema`, or stop advertising them as a usable contract / document them as server-only.

### 🟡 Inconsistent `compact` policy between the two record tools

`get_gene("TP53")` compact returns ~12 xref fields including `mane_select`/`uniprot_ids`/`omim_id`/`ccds_id`. But `get_gene_cross_references` — whose entire job is cross-references — in compact returned only `ensembl_gene_id` + `refseq_accession` (`database_count:2`) and **omitted MANE/UniProt/OMIM**. The dedicated xref tool is stingier than the general one, which is backwards and forces a `full` re-fetch.

**Fix:** include high-value xrefs in the cross-ref tool's compact mode, or document exactly which fields each mode emits.

### 🟢 Lower-severity findings

- **Build provenance unpopulated:** `git_sha:"unknown"`, `built_at:null` in capabilities, though `get_hgnc_diagnostics` populates `built_utc`. Wire the code-build values through.
- **`resolve_symbols_batch.queries` lacks schema `maxItems`** — the documented 200-cap is server-only, while `search_genes.limit` (≤200) and `get_gene_group.limit` (≤1000) *are* schema-capped. Add `maxItems:200` for client-side parity.
- **Gene-group truncation is implicit:** `get_gene_group(654, limit=3)` returns `member_count:24, returned:3` but no `truncated` flag or offset/pagination.
- **Search is nomenclature-only:** `search_genes("polycystin kidney")` ranked KAAG1 and the *PKD1-like* paralogs above and **did not surface PKD1/PKD2** (their names lack "kidney"). Expected for keyword FTS; worth documenting (no disease/phenotype semantics).

### Coverage gap (not a defect)

A genuinely **withdrawn/merged** record was never reached — every candidate tried (SEPT2, MARCH1, FOLR4, FAM21A, DUX2, C2orf48, NCRNA00181, MARC1, GAGE2, …) was a *rename* resolving cleanly via `match_type:"previous"`. The withdrawn-redirect contract is therefore **unverified end-to-end**, and given the ambiguous-null crash, a withdrawn symbol should be regression-tested through `resolve_symbol` to confirm it doesn't share the same null-field violation.

### What's genuinely strong (keep it)

- **Error taxonomy:** `invalid_input`/`not_found`/`ambiguous_query` envelopes with `field`, `allowed_values`, `hint`, `recovery_action`, `retryable`, `next_commands`.
- **Resolution cascade:** ID normalization, case-insensitivity, sensible current > previous > alias precedence with full candidate list.
- **Batch fault-tolerance:** misses/ambiguities never fail the batch; notably handles ambiguity correctly where `resolve_symbol` crashes.
- **Injection-safe:** `BRAF'; DROP TABLE gene;--` → clean `not_found`.
- **Discovery & chaining:** capabilities (summary/full) + resources + signatures + workflows + `next_commands` on success *and* error.
- **Ambiguous-group browsing:** `get_gene_group("kinase")` → `ambiguous:true`, 143 candidate groups with `next_commands`.
- **Token discipline:** provenance once, lean `_meta`, four verbosity tiers, `request_id` everywhere.

### Recommended changes, prioritized

1. **Fix `resolve_symbol` ambiguous-path schema crash** (nullable success fields *or* `ambiguous_query` error envelope) + regression test on `p65`. — *blocker*
2. **Validate/normalize the `databases=` filter** (synonyms + reject-or-warn on unknown), matching `lookup_by_xref`'s `source` behavior.
3. **Reconcile `argument_aliases` with `inputSchema`** — add them to the schemas or stop advertising them as usable.
4. **Align compact field policy** so the cross-reference tool isn't stingier than `get_gene`.
5. Populate `git_sha`/`built_at`; add `maxItems:200` to `queries`; add an explicit group-truncation flag; document search as nomenclature-only; regression-test a true withdrawn/merged symbol through `resolve_symbol`.

---

## Discrepancy vs. prior report

The committed `MCP-ASSESSMENT.md` (same date) describes the `resolve_symbol` issue as an **inert `response_mode`** and states that true-ambiguity fixtures (`P40`/`CAP`/`MT1`) were tested. This live re-run found something more severe: `resolve_symbol` **hard-crashes its output schema** (`None is not of type 'string'`) on ambiguous queries (`p65`, `ACSM2`, `PP1`, `HCG`), while `get_gene` / `get_gene_cross_references` / `resolve_symbols_batch` handle the same inputs cleanly. Either the bug was introduced after the prior pass, or the prior pass verified ambiguity via a different tool than `resolve_symbol`. **Recommend reconciling the two reports and treating the ambiguous-path crash as the current top priority.**

---

## Resolution (2026-06-12, excellence pass v2)

**Root cause of the discrepancy: the live re-run hit a *stale running server*, not the committed code.** The instance under test predates commit `0fb40ad` ("fix(resolve): ambiguity returns structured `ambiguous_query` error") — its own `resolve_symbol` description still reads "is flagged ambiguous" (the pre-fix contract). Reproduced live, then checked against the source:

| Probe | Stale server (this report) | Committed code |
|---|---|---|
| `resolve_symbol("p65")` | 💥 schema crash | raises `AmbiguousQueryError` → clean `ambiguous_query` envelope (`services/hgnc_service.py`); `RESOLVE_SCHEMA` fields are nullable too |
| `databases=["mane"]` | silent `database_count:0` | maps `mane`→`mane_select`; unknown tokens → `invalid_input` + did-you-mean |
| build provenance | `git_sha:"unknown"`, `built_at:null` | resolved from `.git` / env and surfaced in `capabilities.build` |

So the **blocker and findings #2/#4/provenance were already code-complete** before this re-run; the live failure was a deployment-freshness problem. The v2 pass therefore (1) added regression tests that lock the blocker, the withdrawn-redirect path, and the `databases=` behavior so they cannot silently regress; and (2) closed the genuine *residual* gaps that remained even in the fixed code:

- **Finding #3 (argument aliases):** `inputSchema` stays strict (`additionalProperties:false`, per 2026 MCP guidance); capabilities now state honestly that aliases are server-side synonyms and that schema-strict clients should pass the canonical name. (`argument_alias_policy`)
- **Finding #4 (compact xrefs):** `response_mode` now drives meaningful tiers, with `compact` explicitly including MANE/UniProt/OMIM. (`cross_reference_tiers`)
- **Batch `maxItems:200`**, **gene-group `truncated`/`offset`/`next_offset` pagination**, and **search-is-nomenclature-only** documentation all landed.

**Operational note:** the running MCP server must be restarted (the client relaunches it from this source tree; `make install` refreshes the entry point) for the live behavior to match the committed fix. The stale instance is the entire reason this re-run reproduced the blocker.

See `docs/superpowers/specs/2026-06-12-mcp-excellence-pass-v2-design.md` and the `CHANGELOG.md` "excellence pass v2" entries.
