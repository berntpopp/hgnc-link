# Usage

## Tools at a glance

| Tool | When to use |
|------|-------------|
| `get_server_capabilities` | Cold-start discovery — tools, signatures, workflows, vocab. |
| `get_hgnc_diagnostics` | Confirm the loaded HGNC release and that data is built. |
| `resolve_symbol` | **Start here.** Any symbol/ID → canonical `{hgnc_id, approved_symbol, match_type}`. |
| `resolve_symbols_batch` | Resolve many symbols/IDs at once. |
| `get_gene` | Full record for one gene (alias/previous aware). |
| `search_genes` | Free-text / partial search. |
| `get_gene_cross_references` | Gene → external DB IDs (NCBI/Ensembl/UniProt/RefSeq/MANE/OMIM/…). |
| `lookup_by_xref` | External ID → HGNC gene (reverse). |
| `get_gene_group` | Browse a gene family by group ID or name. |

## Canonical workflows

**Normalize a messy symbol list**
```
resolve_symbols_batch(queries=["MLL2","CPAMD9","TP53","BRCA1"])
→ KMT2D (previous), A2ML1 (previous), TP53 (current), BRCA1 (current)
```

**Outdated symbol → current**
```
resolve_symbol(query="MLL2")  → {hgnc_id: HGNC:7133, approved_symbol: KMT2D, match_type: previous}
```
`match_type` tells you whether the input was the current symbol, a *previous*
(renamed) symbol, an *alias*, or an HGNC ID.

**Gene → cross-references → another resource**
```
resolve_symbol(query="BRAF") → get_gene(query="HGNC:1097")
get_gene_cross_references(query="HGNC:1097")
→ entrez_id 673, ensembl ENSG00000157764, uniprot P15056, mane_select [ENST…, NM_…]
```

**External ID → gene**
```
lookup_by_xref(source="ensembl_gene_id", value="ENSG00000157764") → BRAF
lookup_by_xref(source="entrez_id", value="7157") → TP53
```

**Gene family**
```
get_gene_group(group="RAF family")  # or group="1157"
→ ARAF, BRAF, KSR1, KSR2, RAF1
```

## Response modes

Every tool accepts `response_mode ∈ {minimal, compact, standard, full}` (default
`compact`). `compact` drops dates/provenance and empty fields; `minimal` keeps
identity + anchor IDs; `standard`/`full` return the complete record.

## Identifiers & ambiguity

- HGNC IDs are accepted and returned in both `HGNC:1100` and `1100` forms.
- Symbols match case-insensitively.
- A withdrawn/merged symbol returns a `not_found` error with `obsolete: true`,
  `replaced_by`, and a `next_command` to the successor record.
- An alias shared by several genes returns `ambiguous_query` with the candidate
  list — it is never silently collapsed to one gene.

## Chaining

Every response carries `_meta.next_commands` — a ready-to-call
`{tool, arguments}` list (on success **and** error). Follow the first entry to
advance without guessing the next tool.

## Resources

`hgnc://capabilities`, `hgnc://tools`, `hgnc://usage`, `hgnc://reference`,
`hgnc://research-use`, `hgnc://citation`.
