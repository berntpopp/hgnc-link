# HGNC-Link MCP — Assessment

> **Scope:** External, black-box evaluation of the `hgnc-link` MCP server as consumed by an LLM client.
> **Server:** `hgnc-link` v0.1.0 · HGNC release `Fri, 12 Jun 2026` · local SQLite index (44,997 genes, 5,290 withdrawn).
> **Date:** 2026-06-12
> **Method:** ~45 live tool calls across all 9 tools plus both MCP resources, exercising happy paths, boundaries, the full error taxonomy, and every documented contract. Two test fixtures (`A2MR`/`HGNC:9` for the merged-redirect path; `P40`/`CAP`/`MT1` for true ambiguity) were pulled from the local index because common-symbol guessing does not reliably reach those branches.

This document contains two assessments:

1. **Part 1 — LLM-consumer UX evaluation** (dimension ratings, 1–10).
2. **Part 2 — Senior-tester report** (coverage matrix, severity-ranked findings, repros, fixes).

---

## Part 1 — LLM-Consumer UX Evaluation

### Overall: 8/10

A genuinely well-built "link" server. The discovery surface, identifier-aliasing, and next-command chaining are better than most MCPs. Held back from a 9 by one real bug (a filter that silently returns nothing) and one piece of advertised-but-inert machinery (`response_mode` on `resolve_symbol`).

| Dimension | Score | Basis |
|---|---|---|
| Discoverability | 9 | `get_server_capabilities` + `hgnc://capabilities` + `hgnc://tools`, full signatures, workflows, error taxonomy |
| Token efficiency | 6 | Smart "provenance declared once" design and compact default — undercut by an inert `response_mode` and a duplicative `candidates` array |
| Speed | 9 | Local SQLite index; every call returned immediately, batch included |
| Observability | 8 | `request_id` on every call, `next_commands` on success *and* error, rich diagnostics — but build provenance is empty (`git_sha:"unknown"`, `built_at:null`) |
| Error handling | 8 | Clean structured `not_found`, graceful batch degradation — but see the silent-filter bug |
| Ergonomics / chaining | 9 | `query` accepts 11 aliases; HGNC ids with/without prefix; ready-to-call `next_commands` |

### Issues (priority order)

1. **The `databases` filter on `get_gene_cross_references` fails silently — highest impact.** Asking for MANE with `databases=["mane"]` returns `database_count:0, success:true` — an empty result that *looks* like "this gene has no MANE transcript," when the data is present under the field key `mane_select`. The filter only matches exact internal field keys, not the friendly label "mane"/"MANE Select." Confirmed: `["mane","bogus_db"]` → empty + silent; `["mane_select"]` → works. **Fix:** normalize friendly labels/synonyms to field keys, and return `invalid_input` + did-you-mean for unrecognized keys — never a silent empty success.
2. **`response_mode` is a no-op on `resolve_symbol`.** `minimal`, `compact`, and `full` returned byte-identical payloads. For the hottest tool, four advertised verbosity levels collapse to one. **Fix:** make `minimal` actually minimal — drop the `candidates` array and `name`, leaving `{hgnc_id, approved_symbol, match_type}`.
3. **The `candidates` array is redundant when there's no ambiguity.** For an unambiguous gene it repeats `name`/`locus_type`/`status`/`symbol` already present at the top level — ~40% duplication. **Fix:** include `candidates` only when `ambiguous:true` (or gate behind `standard`+).
4. **Build provenance is empty.** `git_sha:"unknown"`, `built_at:null` in capabilities and `_meta` — can't tell which build answered.
5. **Minor: no cross-tool did-you-mean.** An Ensembl id thrown at `resolve_symbols_batch` returns `unresolved` with no hint, yet `lookup_by_xref` resolves it instantly.

The architecture choice is right and it shows: the local cron-refreshed SQLite index makes everything fast and offline, the static-provenance-once policy keeps payloads lean, and `next_commands` make the server self-navigating.

---

## Part 2 — Senior-Tester Report

**Verdict:** Solid, well-architected server with an excellent discovery/error surface and correct data semantics — but its **flagship feature (ambiguity surfacing) is broken at the MCP boundary on its primary tool**, and the cross-reference filter has a silent-failure trap. Both are fixable without redesign. Overall quality **B+ / 7.5**, gated by one critical bug.

### Coverage

All 9 tools tested: identity/normalization, case-folding, previous-symbol redirects, withdrawn & merged redirects, the ambiguity contract, FTS search, gene groups (by id and name), forward + reverse xref mapping, batch, every `response_mode`, invalid enums, out-of-range limits, empty/missing inputs, and bad sources.

### Findings by severity

| # | Severity | Tool | Issue |
|---|----------|------|-------|
| 1 | **Critical** | `resolve_symbol` | Throws an opaque `Output validation error: None is not of type 'string'` on **every ambiguous query** — the feature it's built to provide |
| 2 | High | `get_gene_cross_references` | `databases` filter returns `success:true` + empty for friendly labels (`"mane"`) or unknown keys (`"bogus_db"`) — silent wrong-looking answer |
| 3 | Medium | `search_genes`, `get_gene` | Out-of-range / invalid-enum values return a **misleading** error that lists argument *names* instead of valid *values/range* |
| 4 | Medium | docs vs impl | Three-way inconsistency on how ambiguity is returned (capabilities says `error_code: ambiguous_query`; batch returns `success:true, ambiguous:true`; single tool crashes) |
| 5 | Low–Med | `resolve_symbol` | `response_mode` is a no-op (minimal == full); `candidates` always present and duplicates top-level fields → token waste on the hottest tool |
| 6 | Low | `resolve_symbol` | Precedence can hide intent: `TRP1` → an obscure tRNA gene via previous-symbol match, `candidate_count:1`, alternatives suppressed |

### Finding #1 (Critical) — `resolve_symbol` crashes on ambiguity

`resolve_symbol(query="P40")`, `="CAP"`, `="MT1"` — three independent ambiguous symbols — **all** returned:

```
Output validation error: None is not of type 'string'
```

No `error_code`, no `next_commands`, no candidate list — it reads like a server crash. The service layer is **correct**: the same input through `resolve_symbols_batch(["P40"])` returns a perfect payload — `ambiguous:true`, `candidate_count:10`, the full candidate list, and `note: "'P40' is a alias symbol for 10 genes; pick one and call get_gene."`

**Root cause:** `resolve_symbol`'s registered MCP `outputSchema` types `hgnc_id`/`approved_symbol` as non-nullable `string`. On ambiguity the server correctly emits `hgnc_id: null`, so the client's structured-output validator rejects the whole response. This is why ambiguity never appeared in earlier tests — every symbol that *passed* had a non-null id; the first genuinely ambiguous input broke the tool.

**Fix (pick one):**
- Make `hgnc_id`, `approved_symbol`, and the other gene fields `type: ["string","null"]` in the outputSchema (smallest change), **or**
- Return ambiguity as a structured **error** envelope — `success:false, error_code:"ambiguous_query", candidates:[…]` — which also resolves finding #4 by matching the documented contract.

Add a regression test driving `resolve_symbol("P40")` through the **MCP layer** (the service layer already passes; the gap is schema validation).

### Finding #2 (High) — silent cross-reference filter

`get_gene_cross_references(query="PKD1", databases=["mane","bogus_db"])` → `database_count:0, success:true`. The filter matches only exact internal field keys (`mane_select`), not the friendly label `"mane"` and not obvious typos. A clearly-invalid key like `bogus_db` should never yield `success:true`. **Fix:** normalize labels/synonyms → field keys, and emit `invalid_input` + did-you-mean for unrecognized keys (reuse the excellent `lookup_by_xref` source-validation path).

### Finding #3 (Medium) — misleading error envelopes

- `search_genes(limit=250)` → `"Invalid value for argument limit… Valid argument names are listed in allowed_values"`, `allowed_values:["query","limit","response_mode"]`. The real problem is `250 > max_search_limit (200)`, but it lists argument *names* and implies `limit` isn't recognized. Either clamp to 200 or say `limit must be 1–200`.
- `get_gene(response_mode="verbose")` → same template; `allowed_values:["query","response_mode"]` instead of `["minimal","compact","standard","full"]`.

These reuse the invalid-argument-*name* template for invalid-*value* errors. Surface the valid range/enum in `allowed_values`.

### What works well (verified, not assumed)

- **Withdrawn/merged contract — fully honored.** `A12M1` → `not_found, obsolete:true, withdrawn_status:"Entry Withdrawn", replaced_by:[]`; `HGNC:9` → `Merged/Split, replaced_by:[LRP1]` **with a next_command to the successor**. Exactly as documented.
- **Resolution semantics are correct.** Case-insensitive (`pkd1`), ID normalization (`1100` == `HGNC:1100`), and previous-symbol redirects (`MLL→KMT2A`, `SEPT9→SEPTIN9`, `PARK2→PRKN`, `C10orf2→TWNK`) all resolve with accurate `match_type`.
- **`resolve_symbols_batch` is the robust workhorse** — graceful per-item misses, inline obsolescence, correct `resolved/unresolved` counts, and it even handles the ambiguous case the single tool cannot. Empty list correctly rejected.
- **`get_gene` honors `response_mode`** (minimal genuinely trimmed vs standard/full) — proving #5 is a `resolve_symbol`-specific defect, not a global design choice.
- **`lookup_by_xref` and `get_gene_group`** are clean: reverse mapping from UniProt/OMIM/Ensembl works, groups resolve by both numeric id and name, `member_count` vs `returned` is clear, and bad source/id produce exemplary errors.
- Discovery surface (capabilities + `hgnc://capabilities` + `hgnc://tools`), `request_id` on every call, and `next_commands` everywhere remain best-in-class.

### Prioritized recommendations

1. **Fix `resolve_symbol`'s outputSchema for the ambiguous/null case** (critical) — and add an MCP-layer regression test with `P40`. Reconcile the ambiguity envelope across docs/batch/single tool.
2. **Make the `databases` filter forgiving and loud** — accept labels/synonyms, reject unknown keys with did-you-mean instead of an empty success.
3. **Repair invalid-value error envelopes** — report valid ranges/enums, not argument names.
4. **Make `resolve_symbol` honor `response_mode`** — `minimal` should drop the `candidates` array (or only include it when `ambiguous:true`), trimming ~40% off the default payload of the most-used tool.
5. *(polish)* Add a cross-tool hint when an external id is thrown at `resolve_*` ("looks like an Ensembl id → `lookup_by_xref`"), and consider surfacing cross-tier alternatives so a previous-symbol match on an obscure gene doesn't silently hide the meaning a user likely intended.

Fix #1 and #2 and this server moves from "very good with a sharp edge" to genuinely excellent.

---

### Appendix — representative evidence

| Probe | Result |
|---|---|
| `resolve_symbol("P40")` | ✗ `Output validation error: None is not of type 'string'` |
| `resolve_symbols_batch(["P40"])` | ✓ `ambiguous:true, candidate_count:10` + candidate list + note |
| `get_gene_cross_references("PKD1", databases=["mane"])` | ✗ `database_count:0, success:true` (silent) |
| `get_gene_cross_references("PKD1", databases=["mane_select"])` | ✓ MANE Select: `ENST00000262304.9` / `NM_001009944.3` |
| `search_genes(limit=250)` | ✗ misleading `invalid_input` (lists arg names, not range) |
| `get_gene("PKD1", response_mode="verbose")` | ✗ misleading `invalid_input` (lists arg names, not enum) |
| `resolve_symbol("A12M1")` | ✓ `not_found, obsolete:true, Entry Withdrawn, replaced_by:[]` |
| `resolve_symbol("HGNC:9")` | ✓ `Merged/Split, replaced_by:[LRP1]` + successor next_command |
| `resolve_symbol("1100")` / `("HGNC:1100")` | ✓ both → BRCA1, `match_type:hgnc_id` |
| `resolve_symbol("MLL")` | ✓ → KMT2A, `match_type:previous` |
| `lookup_by_xref("uniprot_ids","P98161")` | ✓ → PKD1 |
| `lookup_by_xref("not_a_source","x")` | ✓ exemplary `invalid_input` + 11 valid sources + hint |
| `get_gene_group("C-type lectin domain containing")` | ✓ resolves by name, `member_count:86` |
