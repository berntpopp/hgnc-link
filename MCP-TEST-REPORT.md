# MCP Test Report — hgnc-link v0.1.0

Date: 2026-06-12 · HGNC release: 2026-06-12 (Last-Modified `Fri, 12 Jun 2026 13:01:53 GMT`)
Index: 44,997 genes · 5,290 withdrawn · 105,607 symbol-lookup rows · 73 MB · build 3.5 s

## Automated suite

| Suite | Result |
|-------|--------|
| Unit tests (`-m "not integration"`) | **142 passed** |
| Coverage | **87%** (gate 80%) |
| Live integration (`-m integration`) | **4 passed** (REST fetch, prev-symbol, `/info`, full bulk build) |
| `ruff format --check` | clean |
| `ruff check` | All checks passed |
| `mypy --strict` (43 files) | Success, no issues |
| Line-budget (≤500) | OK |

## Live tool validation (real ~45k-gene index, through the FastMCP facade)

| Tool | Call | Result |
|------|------|--------|
| `get_server_capabilities` | — | server=hgnc-link, tool_count=9, release present |
| `get_hgnc_diagnostics` | — | data_available=true, gene_count=44997, withdrawn=5290 |
| `resolve_symbol` | `tp53` | HGNC:11998 / TP53 / **current** |
| `resolve_symbol` | `MLL2` | HGNC:7133 / KMT2D / **previous** |
| `resolve_symbol` | `CPAMD9` | HGNC:23336 / A2ML1 / **previous** |
| `resolve_symbol` | `1100` | HGNC:1100 / BRCA1 / **hgnc_id** |
| `resolve_symbol` | `P53` | TP53 / **alias** |
| `resolve_symbol` | `A1S9T` | UBA1 / **previous** (live prev_symbol redirect) |
| `resolve_symbol` | `HGNC:1` | **not_found**, obsolete=true (Entry Withdrawn) |
| `resolve_symbol` | `HGNC:9` | **not_found**, replaced_by=[LRP1], next→get_gene(HGNC:6692) |
| `get_gene` | `BRCA1` | locus_type, ensembl ENSG00000012048, mane_select [ENST…, NM_…] |
| `get_gene` (modes) | `BRAF` full vs compact | full keeps dates; compact drops them |
| `search_genes` | `raf kinase` | RAF1, ARAF, BRAF, MAP4K1, MAP4K2 (FTS-ranked) |
| `get_gene_cross_references` | `BRAF` | ensembl ENSG00000157764, uniprot P15056, … |
| `lookup_by_xref` | `ensembl_gene_id=ENSG00000012048` | BRCA1 |
| `lookup_by_xref` | `entrez_id=7157` | TP53 |
| `lookup_by_xref` | `source=bogus` | **invalid_input**, field=source, allowed_values listed |
| `get_gene_group` | `1157` | RAF family → ARAF, BRAF, KSR1, KSR2, RAF1 |
| `get_gene_group` | `RAF family` (by name) | same 5 members |
| `resolve_symbols_batch` | 6 mixed | 5 resolved, 1 unresolved (graceful) |

## Contract checks (verified)

- Every response carries `_meta.next_commands` (`{tool, arguments}`) on success and error.
- Argument aliases applied (`symbol`→`query`) and disclosed under `_meta.argument_aliases_applied`.
- Wrong argument name → `invalid_input` envelope with `field`, `allowed_values`, `hint` (signature).
- Withdrawn/merged → `not_found` + `obsolete:true` + `replaced_by` + redirect next-command.
- All 9 tools declare `output_schema`; structured_content + TextContent JSON both returned.
- 6 `hgnc://` resources registered.

## Assessment remediation (see `MCP-ASSESSMENT.md`)

Every finding from the external LLM-consumer assessment is closed and regression-tested:

| # | Finding | Resolution | Regression test |
|---|---------|------------|-----------------|
| 1 | `resolve_symbol` crashed on ambiguity | Returns structured `ambiguous_query` error (candidates + next_commands) | `test_resolve_ambiguous_is_structured_error` |
| 2 | Silent `databases` filter | Friendly labels normalized; unknown keys → `invalid_input` + did-you-mean | `test_cross_references_friendly_label`, `test_cross_references_unknown_db_envelope` |
| 3 | Misleading invalid-value errors | Range/enum surfaced (`1..200`, mode enum), not arg names | `test_limit_out_of_range_envelope`, `test_bad_response_mode_envelope` |
| 4 | Ambiguity contract inconsistency | Single-tool error vs batch-inline; documented in `ambiguity_contract` | `test_resolve_batch_ambiguous_inline`, `test_capabilities_documents_ambiguity_contract` |
| 5 | `response_mode` inert; redundant candidates | `shape_resolution` honors modes; candidates dropped on success | `test_resolve_no_candidates_and_modes`, `test_shape_resolution_modes` |
| 6 | Precedence hid cross-tier intent | Lean `other_matches` surfaced | `test_resolve_other_matches_cross_tier` |
| P1 | Empty build provenance | `git_sha`/`built_at` resolved from `.git` + Docker build args | `test_build_info_falls_back_to_git` |
| P2 | No cross-tool xref hint | `lookup_by_xref` suggested for external ids | `test_ensembl_id_to_resolve_hints_xref`, `test_infer_xref_source` |

## Conclusion

All nine tools function correctly against the live HGNC dataset and the live REST
API. Resolution provenance (current/previous/alias/hgnc_id), withdrawn redirects,
cross-reference mapping (both directions), FTS search, and gene-group browse are
verified end-to-end.
