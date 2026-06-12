"""Orchestration over the read-only repository (with optional live fallback).

Returns plain dicts (no envelope); the MCP layer owns ``success``/``_meta``.
The resolution cascade (HGNC ID -> current symbol -> previous symbol -> alias ->
withdrawn redirect) is the centrepiece — it returns the match provenance and
surfaces ambiguity instead of silently collapsing it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hgnc_link.constants import XREF_FIELDS, XREF_SOURCE_ALIASES
from hgnc_link.exceptions import (
    AmbiguousQueryError,
    DataUnavailableError,
    InvalidInputError,
    NotFoundError,
    WithdrawnEntryError,
)
from hgnc_link.identifiers import normalize_hgnc_id
from hgnc_link.services.shaping import shape_gene, shape_summary

if TYPE_CHECKING:
    from hgnc_link.api.client import HgncRestClient
    from hgnc_link.data.repository import HgncRepository

_MAX_BATCH = 200
_MAX_CANDIDATES = 25
_XREF_LABELS = dict(XREF_FIELDS)


class HgncService:
    """High-level HGNC operations backed by the local SQLite index."""

    def __init__(
        self,
        repository: HgncRepository | None,
        *,
        rest_client: HgncRestClient | None = None,
    ) -> None:
        """Wire a repository (primary) and an optional REST client (fallback)."""
        self._repo = repository
        self._rest = rest_client

    @property
    def repo(self) -> HgncRepository:
        """Return the repository or raise a data-unavailable error."""
        if self._repo is None:
            raise DataUnavailableError(
                "The local HGNC index is not built yet. Run `hgnc-link-data build`."
            )
        return self._repo

    # -- diagnostics -----------------------------------------------------------

    def get_diagnostics(self) -> dict[str, Any]:
        """Return data-source provenance and freshness."""
        if self._repo is None:
            return {
                "data_available": False,
                "live_fallback_enabled": self._rest is not None,
                "message": "Local HGNC index not built. Run `hgnc-link-data build`.",
            }
        meta = self._repo.get_meta()
        return {
            "data_available": True,
            "release": meta.get("release"),
            "gene_count": meta.get("gene_count"),
            "withdrawn_count": meta.get("withdrawn_count"),
            "symbol_lookup_rows": meta.get("symbol_lookup_count"),
            "schema_version": meta.get("schema_version"),
            "source_last_modified": meta.get("source_last_modified"),
            "built_utc": meta.get("build_utc"),
            "live_fallback_enabled": self._rest is not None,
        }

    # -- resolution ------------------------------------------------------------

    def resolve(self, query: str, mode: str = "compact") -> dict[str, Any]:
        """Resolve any symbol/ID form to a canonical record (provenance + candidates)."""
        raw = (query or "").strip()
        if not raw:
            raise InvalidInputError("query must be a non-empty symbol or HGNC ID.", field="query")

        hgnc_id = normalize_hgnc_id(raw)
        if hgnc_id:
            return self._resolve_id(raw, hgnc_id)

        pairs = self.repo.lookup_symbol(raw)
        if pairs:
            return self._resolve_symbol_pairs(raw, pairs, mode)

        self._raise_for_withdrawn_symbol(raw)
        raise NotFoundError(f"No HGNC record matches '{raw}'.")

    def _resolve_id(self, raw: str, hgnc_id: str) -> dict[str, Any]:
        gene = self.repo.get_gene(hgnc_id)
        if gene is not None:
            return self._resolution(raw, gene, "hgnc_id", candidates=[_brief(gene, "current")])
        withdrawn = self.repo.get_withdrawn(hgnc_id)
        if withdrawn is not None:
            raise WithdrawnEntryError(
                hgnc_id, status=withdrawn["status"], replaced_by=withdrawn["replaced_by"]
            )
        raise NotFoundError(f"No HGNC record for {hgnc_id}.")

    def _resolve_symbol_pairs(
        self, raw: str, pairs: list[tuple[str, str]], mode: str
    ) -> dict[str, Any]:
        best_type = pairs[0][1]
        best = [p for p in pairs if p[1] == best_type]
        candidates = [
            _brief(self.repo.get_gene(hid) or {"hgnc_id": hid}, stype)
            for hid, stype in pairs[:_MAX_CANDIDATES]
        ]
        if len(best) > 1:
            return {
                "query": raw,
                "hgnc_id": None,
                "approved_symbol": None,
                "match_type": best_type,
                "ambiguous": True,
                "candidate_count": len(candidates),
                "candidates": [shape_summary(c, mode) for c in candidates],
                "note": (
                    f"'{raw}' is a {best_type} symbol for {len(best)} genes; "
                    "pick one and call get_gene."
                ),
            }
        gene = self.repo.get_gene(best[0][0])
        if gene is None:  # pragma: no cover - index integrity
            raise NotFoundError(f"No HGNC record for {best[0][0]}.")
        return self._resolution(raw, gene, best_type, candidates=candidates)

    def _resolution(
        self,
        raw: str,
        gene: dict[str, Any],
        match_type: str,
        *,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "query": raw,
            "hgnc_id": gene.get("hgnc_id"),
            "approved_symbol": gene.get("symbol"),
            "name": gene.get("name"),
            "status": gene.get("status"),
            "locus_type": gene.get("locus_type"),
            "location": gene.get("location"),
            "match_type": match_type,
            "ambiguous": False,
            "candidate_count": len(candidates),
            "candidates": candidates,
        }

    def _raise_for_withdrawn_symbol(self, raw: str) -> None:
        withdrawn = self.repo.find_withdrawn_by_symbol(raw)
        if withdrawn:
            record = withdrawn[0]
            raise WithdrawnEntryError(
                record["withdrawn_symbol"] or raw,
                status=record["status"],
                replaced_by=record["replaced_by"],
            )

    def resolve_batch(self, queries: list[str], mode: str = "compact") -> dict[str, Any]:
        """Resolve a batch of symbols/IDs; never raises for an individual miss."""
        if not queries:
            raise InvalidInputError("queries must be a non-empty list.", field="queries")
        if len(queries) > _MAX_BATCH:
            raise InvalidInputError(
                f"Too many queries ({len(queries)}); max is {_MAX_BATCH}.",
                field="queries",
                hint=f"Split into batches of <= {_MAX_BATCH}.",
            )
        results: list[dict[str, Any]] = []
        resolved = 0
        for query in queries:
            try:
                res = self.resolve(query, mode)
                if res.get("hgnc_id"):
                    resolved += 1
                results.append(res)
            except WithdrawnEntryError as exc:
                results.append(
                    {
                        "query": query,
                        "hgnc_id": None,
                        "match_type": "withdrawn",
                        "obsolete": True,
                        "withdrawn_status": exc.withdrawn_status,
                        "replaced_by": exc.replaced_by,
                    }
                )
            except (NotFoundError, AmbiguousQueryError, InvalidInputError) as exc:
                results.append(
                    {"query": query, "hgnc_id": None, "unresolved": True, "reason": str(exc)}
                )
        return {
            "query_count": len(queries),
            "resolved_count": resolved,
            "unresolved_count": len(queries) - resolved,
            "results": results,
        }

    # -- records ---------------------------------------------------------------

    def _resolve_to_gene(self, raw: str) -> tuple[dict[str, Any], str]:
        hgnc_id = normalize_hgnc_id(raw)
        if hgnc_id:
            gene = self.repo.get_gene(hgnc_id)
            if gene is not None:
                return gene, "hgnc_id"
            withdrawn = self.repo.get_withdrawn(hgnc_id)
            if withdrawn is not None:
                raise WithdrawnEntryError(
                    hgnc_id, status=withdrawn["status"], replaced_by=withdrawn["replaced_by"]
                )
            raise NotFoundError(f"No HGNC record for {hgnc_id}.")
        pairs = self.repo.lookup_symbol(raw)
        if pairs:
            best_type = pairs[0][1]
            best = [p for p in pairs if p[1] == best_type]
            if len(best) > 1:
                candidates = [
                    _brief(self.repo.get_gene(hid) or {"hgnc_id": hid}, stype)
                    for hid, stype in best
                ]
                raise AmbiguousQueryError(
                    f"'{raw}' is a {best_type} symbol for {len(best)} genes; "
                    "use resolve_symbol or get_gene with the HGNC ID.",
                    candidates=candidates,
                )
            gene = self.repo.get_gene(best[0][0])
            if gene is not None:
                return gene, best_type
        self._raise_for_withdrawn_symbol(raw)
        raise NotFoundError(f"No HGNC record matches '{raw}'.")

    def get_gene(self, query: str, mode: str = "compact") -> dict[str, Any]:
        """Return the full gene record for an HGNC ID or symbol (alias/prev aware)."""
        raw = (query or "").strip()
        if not raw:
            raise InvalidInputError("query must be a non-empty symbol or HGNC ID.", field="query")
        gene, match_type = self._resolve_to_gene(raw)
        record = dict(gene)
        record["requested_query"] = raw
        record["match_type"] = match_type
        return shape_gene(record, mode)

    def search(self, query: str, *, limit: int = 25, mode: str = "compact") -> dict[str, Any]:
        """Free-text search over symbol/name/alias/previous symbols."""
        raw = (query or "").strip()
        if not raw:
            raise InvalidInputError("query must be a non-empty search string.", field="query")
        limit = max(1, min(limit, 200))
        hits = self.repo.search(raw, limit=limit)
        return {
            "query": raw,
            "count": len(hits),
            "results": [shape_summary(h, mode) for h in hits],
        }

    def get_cross_references(
        self, query: str, *, databases: list[str] | None = None, mode: str = "compact"
    ) -> dict[str, Any]:
        """Return external cross-references for a gene (forward identifier mapping)."""
        gene, match_type = self._resolve_to_gene((query or "").strip())
        wanted = {d.strip().lower() for d in databases} if databases else None
        xrefs: dict[str, Any] = {}
        for field, label in XREF_FIELDS:
            if wanted is not None and field.lower() not in wanted and label.lower() not in wanted:
                continue
            value = gene.get(field)
            if value:
                xrefs[field] = {"database": label, "value": value}
        return {
            "hgnc_id": gene.get("hgnc_id"),
            "symbol": gene.get("symbol"),
            "match_type": match_type,
            "database_count": len(xrefs),
            "cross_references": xrefs,
        }

    def lookup_by_xref(self, source: str, value: str, mode: str = "compact") -> dict[str, Any]:
        """Reverse lookup: external identifier -> HGNC gene(s)."""
        src = (source or "").strip().lower()
        field = XREF_SOURCE_ALIASES.get(src)
        if field is None:
            allowed = sorted(set(XREF_SOURCE_ALIASES.values()))
            raise InvalidInputError(
                f"Unknown cross-reference source '{source}'.",
                field="source",
                allowed=allowed,
                hint="e.g. entrez_id, ensembl_gene_id, uniprot, omim, refseq.",
            )
        val = (value or "").strip()
        if not val:
            raise InvalidInputError("value must be non-empty.", field="value")
        hgnc_ids = self.repo.lookup_by_xref(field, val)
        if not hgnc_ids:
            raise NotFoundError(f"No HGNC gene with {field}={val}.")
        genes = [self.repo.get_gene(hid) for hid in hgnc_ids]
        summaries = [shape_summary(_brief(g, "current"), mode) for g in genes if g is not None]
        return {
            "source": field,
            "source_label": _XREF_LABELS.get(field, field),
            "value": val,
            "count": len(summaries),
            "results": summaries,
        }

    def get_gene_group(
        self, group: str, *, limit: int = 200, mode: str = "compact"
    ) -> dict[str, Any]:
        """Return the member genes of a gene group/family (by id or name)."""
        raw = (group or "").strip()
        if not raw:
            raise InvalidInputError("group must be a group id or name.", field="group")
        limit = max(1, min(limit, 1000))
        if raw.isdigit():
            group_id: str | None = raw
            group_name = self.repo.group_name_for_id(raw)
            if group_name is None:
                raise NotFoundError(f"No HGNC gene group with id {raw}.")
        else:
            matches = self.repo.resolve_group_name(raw)
            if not matches:
                raise NotFoundError(f"No HGNC gene group matching '{raw}'.")
            exact = [m for m in matches if (m["group_name"] or "").lower() == raw.lower()]
            chosen = exact[0] if exact else matches[0]
            group_id = chosen["group_id"]
            group_name = chosen["group_name"]
            if len(matches) > 1 and not exact:
                return {
                    "query": raw,
                    "ambiguous": True,
                    "match_count": len(matches),
                    "matches": matches[:50],
                    "note": "Multiple groups matched; call get_gene_group with a group id.",
                }
        hgnc_ids = self.repo.group_members(group_id=group_id, group_name=group_name)
        genes = [self.repo.get_gene(hid) for hid in hgnc_ids[:limit]]
        members = [shape_summary(_brief(g, "current"), mode) for g in genes if g is not None]
        members.sort(key=lambda m: m.get("symbol") or "")
        return {
            "group_id": group_id,
            "group_name": group_name,
            "member_count": len(hgnc_ids),
            "returned": len(members),
            "members": members,
        }


def _brief(gene: dict[str, Any], symbol_type: str) -> dict[str, Any]:
    """Compact candidate/summary view of a gene."""
    return {
        "hgnc_id": gene.get("hgnc_id"),
        "symbol": gene.get("symbol"),
        "name": gene.get("name"),
        "locus_type": gene.get("locus_type"),
        "status": gene.get("status"),
        "symbol_type": symbol_type,
    }
