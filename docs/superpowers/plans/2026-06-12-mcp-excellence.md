# HGNC-Link MCP Excellence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every `MCP-ASSESSMENT.md` finding (critical → polish) to take the server from 8/10 to ≥ 9.5/10, preserving all `AGENTS.md` invariants.

**Architecture:** Service returns plain dicts; MCP layer owns the envelope. Ambiguity becomes a structured `ambiguous_query` error on single-result tools (reusing the existing `AmbiguousQueryError` path) and stays inline per-item on the batch tool. The `databases` filter gains a synonym map; arg-binding errors become value-aware; `resolve_symbol` honors `response_mode` and surfaces cross-tier alternatives; build provenance and cross-tool hints are added.

**Tech Stack:** Python 3.12, FastMCP, pydantic v2, SQLite/FTS5, pytest (async), uv, ruff, mypy strict.

**Gate after every task group:** `make test`; final `make ci-local`.

---

### Task 1: Fixtures for ambiguity + cross-tier; fix count assertions

**Files:**
- Modify: `tests/fixtures_genes.json` (add 3 genes)
- Modify: `tests/unit/test_service.py:128`, `tests/unit/test_repository.py:13`, `tests/unit/test_builder.py:35`, `tests/unit/test_tools_e2e.py:18` (gene_count 5 → 8)

- [ ] **Step 1: Add three fixture genes** to the `response.docs` array (synthetic, purpose-built for disambiguation tests):
  - `HGNC:90001` symbol `AMBA`, `alias_symbol:["DUPE","CROSS"]`, `status:"Approved"`, `locus_group:"protein-coding gene"`, `locus_type:"gene with protein product"`, `location:"1p11"`, `entrez_id:"900011"`, `ensembl_gene_id:"ENSG09000000011"`, `name:"ambiguity test gene A"`.
  - `HGNC:90002` symbol `AMBB`, `alias_symbol:["DUPE"]`, same scalars, `location:"2q22"`, `entrez_id:"900012"`, `name:"ambiguity test gene B"`.
  - `HGNC:90003` symbol `XTIER`, `prev_symbol:["CROSS"]`, same scalars, `location:"3p21"`, `entrez_id:"900013"`, `name:"cross-tier test gene"`.
  - Result: `DUPE` → alias of AMBA+AMBB (within-tier ambiguity). `CROSS` → previous of XTIER (tier 1) + alias of AMBA (tier 2) → cross-tier.

- [ ] **Step 2: Run tests, observe count failures**

Run: `make test`
Expected: failures in the 4 `gene_count == 5` / `meta.gene_count == 5` assertions.

- [ ] **Step 3: Update the 4 assertions to `== 8`.**

- [ ] **Step 4: Run tests**

Run: `make test`
Expected: PASS (no behavior change yet beyond counts).

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add ambiguity + cross-tier fixtures; bump gene_count to 8"
```

---

### Task 2 (Finding #1, Critical): ambiguity → `ambiguous_query` error on `resolve_symbol`

**Files:**
- Modify: `hgnc_link/services/hgnc_service.py` (`resolve`, `_resolve_symbol_pairs`, add `_ambiguity_error`)
- Modify: `hgnc_link/mcp/schemas.py` (`RESOLVE_SCHEMA` nullable identity)
- Modify: `tests/unit/test_service.py` (`test_ambiguous_alias`)
- Add tests: `tests/unit/test_tools_e2e.py` (MCP-layer ambiguity regression)

- [ ] **Step 1: Write the failing MCP-layer regression test** in `test_tools_e2e.py`:

```python
async def test_resolve_ambiguous_is_structured_error(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "DUPE"}))
    assert payload["success"] is False
    assert payload["error_code"] == "ambiguous_query"
    assert len(payload["candidates"]) == 2
    assert payload["recovery_action"] == "reformulate_input"
    assert payload["_meta"]["next_commands"][0]["tool"] == "get_gene"
```

- [ ] **Step 2: Run it — expect the crash/old behavior**

Run: `uv run pytest tests/unit/test_tools_e2e.py::test_resolve_ambiguous_is_structured_error -v`
Expected: FAIL (today resolve returns success/ambiguous and/or schema-validation error).

- [ ] **Step 3: Make `resolve()` raise on within-tier ambiguity.** In `hgnc_service.py`, add a shared helper and use it in `_resolve_symbol_pairs`:

```python
def _ambiguity_error(self, raw: str, best_type: str, best: list[tuple[str, str]]) -> AmbiguousQueryError:
    candidates = [
        _brief(self.repo.get_gene(hid) or {"hgnc_id": hid}, stype) for hid, stype in best
    ]
    return AmbiguousQueryError(
        f"'{raw}' is a {best_type} symbol for {len(best)} genes; pick one and call get_gene.",
        candidates=candidates,
    )
```

Replace the `if len(best) > 1:` block in `_resolve_symbol_pairs` so it raises `self._ambiguity_error(raw, best_type, best)` instead of returning the inline ambiguous dict.

- [ ] **Step 4: Make `RESOLVE_SCHEMA` identity fields nullable** (defense-in-depth). In `schemas.py` add `_STR_NULL = {"type": ["string", "null"]}` and use it for `hgnc_id`, `approved_symbol`, `name`, `status`, `locus_type`, `location`, `match_type` in `RESOLVE_SCHEMA`.

- [ ] **Step 5: Update `test_ambiguous_alias`** in `test_service.py` to expect the exception:

```python
def test_ambiguous_alias(service: HgncService) -> None:
    with pytest.raises(AmbiguousQueryError) as exc:
        service.resolve("DUPE")
    assert len(exc.value.candidates) == 2
    with pytest.raises(AmbiguousQueryError):
        service.get_gene("DUPE")
```

(Remove the monkeypatch version; the fixture now provides real ambiguity.)

- [ ] **Step 6: Run the targeted tests**

Run: `uv run pytest tests/unit/test_tools_e2e.py::test_resolve_ambiguous_is_structured_error tests/unit/test_service.py::test_ambiguous_alias -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "fix(resolve): ambiguity returns structured ambiguous_query error (finding #1)"
```

---

### Task 3 (Finding #5/#6, D4/D5): response_mode honored; drop redundant candidates; surface other_matches

**Files:**
- Modify: `hgnc_link/services/shaping.py` (add `shape_resolution`)
- Modify: `hgnc_link/services/hgnc_service.py` (`_resolution`, `_resolve_symbol_pairs` to compute `other_matches`)
- Add tests: `tests/unit/test_shaping.py`, `tests/unit/test_service.py`, `tests/unit/test_tools_e2e.py`

- [ ] **Step 1: Write failing shaping + service tests.**

`test_shaping.py`:
```python
from hgnc_link.services.shaping import shape_resolution

def test_shape_resolution_modes() -> None:
    rec = {
        "query": "x", "hgnc_id": "HGNC:1", "approved_symbol": "S", "name": "n",
        "status": "Approved", "locus_type": "t", "location": "1p", "match_type": "current",
        "ambiguous": False,
    }
    assert set(shape_resolution(rec, "minimal")) == {"query", "hgnc_id", "approved_symbol", "match_type"}
    assert "name" in shape_resolution(rec, "compact")
    assert shape_resolution(rec, "full") == rec
    assert "candidates" not in shape_resolution(rec, "compact")
```

`test_service.py`:
```python
def test_resolve_no_candidates_and_modes(service: HgncService) -> None:
    r = service.resolve("BRAF", "compact")
    assert "candidates" not in r and "candidate_count" not in r
    m = service.resolve("BRAF", "minimal")
    assert set(m) == {"query", "hgnc_id", "approved_symbol", "match_type"}

def test_resolve_other_matches_cross_tier(service: HgncService) -> None:
    r = service.resolve("CROSS")               # previous of XTIER, alias of AMBA
    assert r["approved_symbol"] == "XTIER"
    assert r["match_type"] == "previous"
    others = {o["symbol"] for o in r.get("other_matches", [])}
    assert "AMBA" in others
```

- [ ] **Step 2: Run — expect failures** (`shape_resolution` missing; candidates still present).

Run: `uv run pytest tests/unit/test_shaping.py::test_shape_resolution_modes tests/unit/test_service.py::test_resolve_no_candidates_and_modes tests/unit/test_service.py::test_resolve_other_matches_cross_tier -v`
Expected: FAIL.

- [ ] **Step 3: Add `shape_resolution` to `shaping.py`:**

```python
_RESOLUTION_MINIMAL: frozenset[str] = frozenset({"query", "hgnc_id", "approved_symbol", "match_type"})

def shape_resolution(record: dict[str, Any], mode: str) -> dict[str, Any]:
    """Project a resolve_symbol success payload to the requested verbosity."""
    if mode == "minimal":
        return {k: v for k, v in record.items() if k in _RESOLUTION_MINIMAL}
    if mode in ("standard", "full"):
        return record
    return {k: v for k, v in record.items() if v is not None and v != [] and v != ""}
```

- [ ] **Step 4: Rework `_resolution` / `_resolve_symbol_pairs`** in `hgnc_service.py` so the success dict carries no `candidates`/`candidate_count`, adds `ambiguous: False`, optional `other_matches`, and is shaped:

```python
def _resolve_symbol_pairs(self, raw: str, pairs: list[tuple[str, str]], mode: str) -> dict[str, Any]:
    best_type = pairs[0][1]
    best = [p for p in pairs if p[1] == best_type]
    if len(best) > 1:
        raise self._ambiguity_error(raw, best_type, best)
    gene = self.repo.get_gene(best[0][0])
    if gene is None:  # pragma: no cover - index integrity
        raise NotFoundError(f"No HGNC record for {best[0][0]}.")
    others = [
        _brief(self.repo.get_gene(hid) or {"hgnc_id": hid}, stype)
        for hid, stype in pairs
        if hid != gene.get("hgnc_id")
    ]
    return self._resolution(raw, gene, best_type, other_matches=others, mode=mode)

def _resolution(self, raw, gene, match_type, *, other_matches=None, mode="compact"):
    record: dict[str, Any] = {
        "query": raw,
        "hgnc_id": gene.get("hgnc_id"),
        "approved_symbol": gene.get("symbol"),
        "name": gene.get("name"),
        "status": gene.get("status"),
        "locus_type": gene.get("locus_type"),
        "location": gene.get("location"),
        "match_type": match_type,
        "ambiguous": False,
    }
    if other_matches:
        record["other_matches"] = [
            {"hgnc_id": o["hgnc_id"], "symbol": o.get("symbol"), "symbol_type": o.get("symbol_type")}
            for o in other_matches
        ]
    return shape_resolution(record, mode)
```

Update `_resolve_id` to call `_resolution(raw, gene, "hgnc_id", mode=mode)` (no candidates). Thread `mode` into `_resolve_id`/`resolve` calls. Import `shape_resolution`.

- [ ] **Step 5: Add `RESOLVE_SCHEMA` field `other_matches=_ARR`** in `schemas.py` (keep permissive).

- [ ] **Step 6: Run targeted tests; then full suite.**

Run: `uv run pytest tests/unit/test_shaping.py tests/unit/test_service.py -v` then `make test`
Expected: PASS. (Note: `test_resolve_current_symbol` still asserts `ambiguous is False` — preserved.)

- [ ] **Step 7: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "feat(resolve): honor response_mode, drop redundant candidates, surface other_matches (findings #5,#6)"
```

---

### Task 4 (Finding #1 batch, D8): batch preserves inline ambiguity

**Files:**
- Modify: `hgnc_link/services/hgnc_service.py` (`resolve_batch`)
- Add test: `tests/unit/test_service.py`

- [ ] **Step 1: Failing test** in `test_service.py`:

```python
def test_resolve_batch_ambiguous_inline(service: HgncService) -> None:
    out = service.resolve_batch(["BRAF", "DUPE"])
    entry = {r["query"]: r for r in out["results"]}["DUPE"]
    assert entry["ambiguous"] is True
    assert entry["candidate_count"] == 2
    assert entry["hgnc_id"] is None
    assert out["resolved_count"] == 1
```

- [ ] **Step 2: Run — expect FAIL** (currently the `AmbiguousQueryError` is caught as generic `unresolved`).

- [ ] **Step 3: Add an `except AmbiguousQueryError` branch** before the generic catch in `resolve_batch`:

```python
except AmbiguousQueryError as exc:
    results.append({
        "query": query,
        "hgnc_id": None,
        "ambiguous": True,
        "candidate_count": len(exc.candidates),
        "candidates": [shape_summary(c, mode) for c in exc.candidates],
        "note": str(exc),
    })
```

(Keep the generic `except (NotFoundError, InvalidInputError)` after it.)

- [ ] **Step 4: Run test; full suite.**

Run: `uv run pytest tests/unit/test_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "fix(batch): preserve rich inline ambiguity per item (finding #4)"
```

---

### Task 5 (Finding #2, High): forgiving-and-loud `databases` filter

**Files:**
- Modify: `hgnc_link/constants.py` (add `XREF_FILTER_ALIASES`)
- Modify: `hgnc_link/services/hgnc_service.py` (`get_cross_references`)
- Add tests: `tests/unit/test_service.py`, `tests/unit/test_tools_e2e.py`

- [ ] **Step 1: Failing tests.**

`test_service.py`:
```python
def test_cross_references_friendly_label(service: HgncService) -> None:
    only = service.get_cross_references("BRAF", databases=["mane"])
    assert "mane_select" in only["cross_references"]

def test_cross_references_unknown_db_errors(service: HgncService) -> None:
    with pytest.raises(InvalidInputError) as exc:
        service.get_cross_references("BRAF", databases=["bogus_db"])
    assert exc.value.field == "databases"
    assert exc.value.allowed
```

`test_tools_e2e.py`:
```python
async def test_cross_references_unknown_db_envelope(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool(
        "get_gene_cross_references", {"query": "BRAF", "databases": ["mane", "bogus_db"]}))
    assert payload["success"] is False
    assert payload["error_code"] == "invalid_input"
    assert payload["field"] == "databases"
```

- [ ] **Step 2: Run — expect FAIL** (`["mane"]` returns empty success; bogus is silent).

- [ ] **Step 3: Add `XREF_FILTER_ALIASES` to `constants.py`** — derive `{field: field}` for every `XREF_FIELDS` field, plus its lowercased label (spaces kept), plus curated synonyms:

```python
XREF_FILTER_ALIASES: dict[str, str] = {
    **{f: f for f, _ in XREF_FIELDS},
    **{label.lower(): f for f, label in XREF_FIELDS},
    "ncbi": "entrez_id", "ncbi_gene": "entrez_id", "ncbi_gene_id": "entrez_id",
    "entrez": "entrez_id", "gene_id": "entrez_id",
    "ensembl": "ensembl_gene_id", "ensg": "ensembl_gene_id",
    "uniprot": "uniprot_ids", "uniprot_id": "uniprot_ids",
    "refseq": "refseq_accession",
    "mane": "mane_select",
    "omim": "omim_id", "mim": "omim_id",
    "ucsc": "ucsc_id", "vega": "vega_id", "ccds": "ccds_id",
    "mgi": "mgd_id", "rgd": "rgd_id", "pubmed": "pubmed_id",
}
```

- [ ] **Step 4: Rewrite the filter** in `get_cross_references`:

```python
from hgnc_link.constants import XREF_FIELDS, XREF_FILTER_ALIASES, XREF_SOURCE_ALIASES
import difflib
...
wanted: set[str] | None = None
if databases:
    resolved: set[str] = set()
    unknown: list[str] = []
    for d in databases:
        key = (d or "").strip().lower()
        canon = XREF_FILTER_ALIASES.get(key)
        if canon is None:
            unknown.append(d)
        else:
            resolved.add(canon)
    if unknown:
        allowed = [f for f, _ in XREF_FIELDS]
        guess = difflib.get_close_matches(unknown[0].lower(), list(XREF_FILTER_ALIASES), n=1, cutoff=0.6)
        hint = f"Did you mean '{XREF_FILTER_ALIASES[guess[0]]}'? " if guess else ""
        raise InvalidInputError(
            f"Unknown cross-reference database(s): {', '.join(unknown)}.",
            field="databases", allowed=allowed,
            hint=hint + "Use a field key or label, e.g. ensembl, uniprot, mane, omim.",
        )
    wanted = resolved
xrefs: dict[str, Any] = {}
for field, label in XREF_FIELDS:
    if wanted is not None and field not in wanted:
        continue
    value = gene.get(field)
    if value:
        xrefs[field] = {"database": label, "value": value}
```

- [ ] **Step 5: Run targeted tests; full suite.** Confirm existing `test_cross_references_and_filter` (`databases=["ensembl"]`) still passes.

Run: `uv run pytest tests/unit/test_service.py tests/unit/test_tools_e2e.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "fix(xref): normalize friendly db labels, reject unknown keys loudly (finding #2)"
```

---

### Task 6 (Finding #3, Medium): value-aware argument errors

**Files:**
- Modify: `hgnc_link/mcp/arg_help.py` (add `describe_constraints`)
- Modify: `hgnc_link/mcp/envelope.py` (`build_arg_error_envelope` value branch)
- Modify: `hgnc_link/mcp/middleware.py` (`_error_result` passes field schema)
- Add tests: `tests/unit/test_arg_help.py`, `tests/unit/test_tools_e2e.py`

- [ ] **Step 1: Failing tests.**

`test_arg_help.py`:
```python
from hgnc_link.mcp.arg_help import describe_constraints

def test_describe_constraints_enum() -> None:
    allowed, human = describe_constraints({"enum": ["a", "b", "c"]})
    assert allowed == ["a", "b", "c"]
    assert "one of" in human

def test_describe_constraints_range() -> None:
    allowed, human = describe_constraints({"type": "integer", "minimum": 1, "maximum": 200})
    assert allowed == ["1..200"]
    assert "between 1 and 200" in human
```

`test_tools_e2e.py`:
```python
async def test_limit_out_of_range_envelope(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("search_genes", {"query": "x", "limit": 250}))
    assert payload["error_code"] == "invalid_input"
    assert "200" in payload["message"]
    assert payload["allowed_values"] == ["1..200"]

async def test_bad_response_mode_envelope(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("get_gene", {"query": "BRAF", "response_mode": "verbose"}))
    assert payload["error_code"] == "invalid_input"
    assert set(payload["allowed_values"]) == {"minimal", "compact", "standard", "full"}
```

- [ ] **Step 2: Run — expect FAIL** (allowed_values currently lists arg names).

- [ ] **Step 3: Add `describe_constraints` to `arg_help.py`:**

```python
def describe_constraints(field_schema: Mapping[str, Any]) -> tuple[list[str], str] | None:
    """Return (allowed_values, human) for an enum/range field, or None."""
    nodes = [field_schema, *field_schema.get("anyOf", []), *field_schema.get("allOf", []),
             *field_schema.get("oneOf", [])]
    for node in nodes:
        if isinstance(node, Mapping) and node.get("enum"):
            vals = [str(v) for v in node["enum"]]
            return vals, "must be one of: " + ", ".join(vals)
    lo = hi = None
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        lo = node.get("minimum", node.get("exclusiveMinimum", lo))
        hi = node.get("maximum", node.get("exclusiveMaximum", hi))
    if lo is not None or hi is not None:
        lo_s, hi_s = (str(int(lo)) if lo is not None else "?"), (str(int(hi)) if hi is not None else "?")
        return [f"{lo_s}..{hi_s}"], f"must be between {lo_s} and {hi_s}"
    return None
```

- [ ] **Step 4: Add a value-aware branch to `build_arg_error_envelope`** in `envelope.py` — accept an optional `constraints: tuple[list[str], str] | None` param; when present (a value error on a known field), use it:

```python
def build_arg_error_envelope(*, tool_name, loc, error_type, valid_params, signature,
                             suggestion, constraints=None):
    if constraints is not None:
        allowed, human = constraints
        message = f"Invalid value for argument `{loc}` of {tool_name}: {human}."
        return {
            "success": False, "error_code": "invalid_input", "message": message[:280],
            "retryable": False, "recovery_action": "reformulate_input",
            "field": loc, "allowed_values": allowed, "hint": signature,
            "_meta": {"tool": tool_name, "request_id": _request_id(),
                      "next_commands": [cmd("get_server_capabilities")]},
        }
    # ...existing name-error body unchanged...
```

- [ ] **Step 5: Wire the middleware** `_error_result` to compute constraints when `loc` is a real param:

```python
from hgnc_link.mcp.arg_help import describe_constraints
...
constraints = None
if loc in valid and error_type not in ("missing", "missing_argument"):
    field_schema = schema.get("properties", {}).get(loc, {})
    constraints = describe_constraints(field_schema)
envelope = build_arg_error_envelope(
    tool_name=name, loc=loc, error_type=error_type, valid_params=valid,
    signature=tool_signature(name, schema),
    suggestion=did_you_mean(loc, valid) if loc not in valid else None,
    constraints=constraints,
)
```

- [ ] **Step 6: Run targeted tests; full suite.** Confirm `test_bad_arg_name_returns_invalid_input` and `test_unknown_arg_suggests_canonical` still pass (name errors unaffected).

Run: `uv run pytest tests/unit/test_arg_help.py tests/unit/test_tools_e2e.py tests/unit/test_structured_and_middleware.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "fix(args): value errors surface valid range/enum, not arg names (finding #3)"
```

---

### Task 7 (Polish P2, D6): cross-tool xref hint

**Files:**
- Modify: `hgnc_link/identifiers.py` (add `infer_xref_source`)
- Modify: `hgnc_link/mcp/next_commands.py` (`default_error_next_commands`)
- Modify: `hgnc_link/services/hgnc_service.py` (`resolve_batch` unresolved hint)
- Add tests: `tests/unit/test_identifiers.py`, `tests/unit/test_next_commands.py`, `tests/unit/test_tools_e2e.py`

- [ ] **Step 1: Failing tests.**

`test_identifiers.py`:
```python
from hgnc_link.identifiers import infer_xref_source

def test_infer_xref_source() -> None:
    assert infer_xref_source("ENSG00000157764") == "ensembl_gene_id"
    assert infer_xref_source("P15056") == "uniprot"
    assert infer_xref_source("NM_004333") == "refseq"
    assert infer_xref_source("BRAF") is None
```

`test_tools_e2e.py`:
```python
async def test_ensembl_id_to_resolve_hints_xref(facade: Any, structured: Any) -> None:
    payload = structured(await facade.call_tool("resolve_symbol", {"query": "ENSG00000999999"}))
    assert payload["success"] is False
    tools = [c["tool"] for c in payload["_meta"]["next_commands"]]
    assert "lookup_by_xref" in tools
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Add `infer_xref_source` to `identifiers.py`:**

```python
_ENSG_RE = re.compile(r"^ENSG\d{6,}", re.IGNORECASE)
_ENST_RE = re.compile(r"^ENST\d{6,}", re.IGNORECASE)
_REFSEQ_RE = re.compile(r"^(NM_|NP_|NR_|XM_|XP_|NG_)\d+", re.IGNORECASE)
_UNIPROT_RE = re.compile(r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$")

def infer_xref_source(value: str) -> str | None:
    """Best-effort: map an external-id-shaped string to a lookup_by_xref source."""
    text = (value or "").strip()
    if _ENSG_RE.match(text):
        return "ensembl_gene_id"
    if _ENST_RE.match(text):
        return "ensembl"
    if _REFSEQ_RE.match(text):
        return "refseq"
    if _UNIPROT_RE.match(text):
        return "uniprot"
    return None
```

- [ ] **Step 4: Wire into `default_error_next_commands`** (next_commands.py) — prepend an xref step when the query looks like an external id:

```python
from hgnc_link.identifiers import infer_xref_source, looks_like_hgnc_id, looks_like_symbol
...
def default_error_next_commands(tool, error_code, arguments):
    if tool in ("resolve_symbol", "get_gene"):
        value = str(arguments.get("query", ""))
        source = infer_xref_source(value)
        if source:
            return [cmd("lookup_by_xref", source=source, value=value), cmd("search_genes", query=value)]
        if value and (looks_like_symbol(value) or not looks_like_hgnc_id(value)):
            return [cmd("search_genes", query=value), cmd("get_server_capabilities")]
    if error_code == "data_unavailable":
        return [cmd("get_hgnc_diagnostics")]
    return [cmd("get_server_capabilities")]
```

- [ ] **Step 5: Add a hint to batch unresolved entries** in `resolve_batch` (the generic catch):

```python
except (NotFoundError, InvalidInputError) as exc:
    entry = {"query": query, "hgnc_id": None, "unresolved": True, "reason": str(exc)}
    source = infer_xref_source(query)
    if source:
        entry["hint"] = f"Looks like a {source} id; try lookup_by_xref(source='{source}')."
    results.append(entry)
```

(Import `infer_xref_source` in hgnc_service.py.)

- [ ] **Step 6: Run targeted + suite.**

Run: `uv run pytest tests/unit/test_identifiers.py tests/unit/test_next_commands.py tests/unit/test_tools_e2e.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "feat(hints): suggest lookup_by_xref for external ids thrown at resolve (polish #5)"
```

---

### Task 8 (Polish P1, D7): build provenance

**Files:**
- Modify: `hgnc_link/buildinfo.py`
- Modify: `docker/Dockerfile` (build args)
- Modify: `tests/unit/test_exceptions_buildinfo.py`

- [ ] **Step 1: Failing test** in `test_exceptions_buildinfo.py`:

```python
def test_build_info_falls_back_to_git(monkeypatch) -> None:
    monkeypatch.delenv("HGNC_LINK_GIT_SHA", raising=False)
    monkeypatch.delenv("HGNC_LINK_BUILT_AT", raising=False)
    info = build_info()
    # In a git checkout the sha is resolved; built_at falls back to a timestamp.
    assert info["git_sha"] != "unknown"
    assert info["built_at"] is not None
```

- [ ] **Step 2: Run — expect FAIL** (currently returns "unknown"/None).

- [ ] **Step 3: Make `build_info()` resilient** in `buildinfo.py` with a pure-Python `.git` reader and an mtime fallback:

```python
from datetime import datetime, timezone
from pathlib import Path

def _git_sha_from_dotgit() -> str | None:
    root = Path(__file__).resolve().parent.parent
    git = root / ".git"
    if not git.exists():
        return None
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head[4:].strip()
            loose = git / ref
            if loose.exists():
                return loose.read_text(encoding="utf-8").strip()[:12]
            packed = git / "packed-refs"
            if packed.exists():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith(("#", "^")) and line.endswith(ref):
                        return line.split()[0][:12]
            return None
        return head[:12]  # detached HEAD
    except OSError:
        return None

def _built_at_fallback() -> str | None:
    try:
        mtime = Path(__file__).with_name("__init__.py").stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None

def build_info() -> dict[str, str | None]:
    return {
        "version": __version__,
        "git_sha": os.environ.get("HGNC_LINK_GIT_SHA") or _git_sha_from_dotgit() or "unknown",
        "built_at": os.environ.get("HGNC_LINK_BUILT_AT") or _built_at_fallback(),
    }
```

- [ ] **Step 4: Wire Docker build args** in `docker/Dockerfile` (production stage, before `USER app`):

```dockerfile
ARG HGNC_LINK_GIT_SHA=unknown
ARG HGNC_LINK_BUILT_AT
ENV HGNC_LINK_GIT_SHA=${HGNC_LINK_GIT_SHA} \
    HGNC_LINK_BUILT_AT=${HGNC_LINK_BUILT_AT}
```

- [ ] **Step 5: Confirm the existing `test_build_info_keys`** (monkeypatches the env to `deadbeef`) still passes, and run the new test.

Run: `uv run pytest tests/unit/test_exceptions_buildinfo.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hgnc_link/ docker/ tests/
git commit -m "feat(buildinfo): resolve git sha + built_at in dev and prod (observability)"
```

---

### Task 9 (Finding #4 docs): document the ambiguity contract + filter aliases

**Files:**
- Modify: `hgnc_link/mcp/capabilities.py` (`build_capabilities` — clarify ambiguity contract; expose filter aliases)
- Modify: `hgnc_link/mcp/tools/resolve.py` + `genes.py` (description sentences)
- Add test: `tests/unit/test_capabilities.py`

- [ ] **Step 1: Failing test** in `test_capabilities.py`:

```python
def test_capabilities_documents_ambiguity_contract() -> None:
    cap = build_capabilities()
    assert "ambiguity_contract" in cap
    assert "batch" in cap["ambiguity_contract"].lower()
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Add `ambiguity_contract` to `build_capabilities()`:**

```python
"ambiguity_contract": (
    "Single-result tools (resolve_symbol, get_gene, get_gene_cross_references) "
    "return error_code 'ambiguous_query' with a candidates list and next_commands "
    "to each candidate. resolve_symbols_batch never fails the whole call: each "
    "ambiguous query is returned inline with ambiguous:true + candidates so one "
    "ambiguity never blocks the others."
),
```

Also add `"cross_reference_filter_synonyms": sorted(set(XREF_FILTER_ALIASES))` (import it) so consumers can discover accepted filter labels.

- [ ] **Step 4: Update tool descriptions** — `resolve_symbol` description: change "is flagged ambiguous (not silently picked)" to "returns an ambiguous_query error with the candidate list (not silently picked)". `get_gene_cross_references` description: add "databases accepts field keys or friendly labels (e.g. 'mane', 'ncbi'); an unknown key is rejected with invalid_input."

- [ ] **Step 5: Run; full suite.**

Run: `uv run pytest tests/unit/test_capabilities.py -v && make test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hgnc_link/ tests/
git commit -m "docs(capabilities): document ambiguity contract + xref filter synonyms (finding #4)"
```

---

### Task 10: Full gate + changelog

**Files:**
- Modify: `CHANGELOG.md`, `MCP-TEST-REPORT.md` (brief note)

- [ ] **Step 1: Run the full local gate.**

Run: `make ci-local`
Expected: format-check, lint, line-budget, mypy strict, tests (≥ 80% cov) — all PASS.
If line-budget fails on `hgnc_service.py`, extract the xref-filter normalization into a small private helper or a `services/xref_filter.py` module.

- [ ] **Step 2: Add a CHANGELOG entry** summarizing the six fixes.

- [ ] **Step 3: Commit.**

```bash
git add CHANGELOG.md MCP-TEST-REPORT.md
git commit -m "docs: changelog for MCP excellence pass"
```

- [ ] **Step 4: Re-verify each finding** with a quick live facade probe (DUPE ambiguity, mane filter, bogus_db, limit=250, response_mode=verbose, ENSG→xref hint, build provenance) and confirm against the assessment appendix.

---

## Self-review

- **Spec coverage:** Findings #1 (Task 2), #2 (Task 5), #3 (Task 6), #4 (Tasks 2/4/9), #5 (Task 3), #6 (Task 3), P1 provenance (Task 8), P2 hint (Task 7). All covered.
- **Placeholders:** none — every code step shows the code.
- **Type consistency:** `_ambiguity_error` (Task 2) is reused conceptually by `_resolve_symbol_pairs` (Task 3); `shape_resolution` (Task 3) signature matches its test; `describe_constraints` returns `tuple|None` consistently across Tasks 6 steps; `infer_xref_source` returns `str|None` used in Tasks 7. `build_arg_error_envelope` gains an optional `constraints` kwarg (back-compatible).
- **Line budget risk:** flagged in Task 10 with a concrete remedy.
