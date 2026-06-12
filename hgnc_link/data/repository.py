"""Read-only SQLite repository for the built HGNC index.

All indexes are pre-computed by the builder, so this layer only reads rows and
decodes the JSON list columns back into Python lists. FTS5 queries are sanitized
so raw user text never reaches ``MATCH`` (which can raise on operator
characters), with a ``LIKE`` fallback for pathological input.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from hgnc_link.constants import LIST_FIELDS
from hgnc_link.exceptions import DataUnavailableError
from hgnc_link.identifiers import normalize_hgnc_id

_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
# Priority used when a symbol resolves to several lookup rows.
_TYPE_PRIORITY = {"current": 0, "previous": 1, "alias": 2}


class HgncRepository:
    """Read-only access to the built HGNC SQLite index."""

    def __init__(self, db_path: Path | str) -> None:
        """Open a read-only connection to the HGNC database."""
        self._path = Path(db_path)
        if not self._path.exists():
            raise DataUnavailableError(
                f"HGNC database not found at {self._path}. Build it with `hgnc-link-data build`."
            )
        try:
            self._conn = sqlite3.connect(
                f"file:{self._path}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:  # pragma: no cover - rare OS-level failure
            raise DataUnavailableError(
                f"Cannot open HGNC database at {self._path}: {exc}."
            ) from exc
        self._conn.row_factory = sqlite3.Row

    # -- provenance ------------------------------------------------------------

    def get_meta(self) -> dict[str, Any]:
        """Return build provenance from the ``meta`` table."""
        try:
            row = self._conn.execute("SELECT * FROM meta WHERE id = 1").fetchone()
        except sqlite3.Error as exc:
            raise DataUnavailableError(
                f"HGNC database at {self._path} is unreadable: {exc}."
            ) from exc
        if row is None:
            raise DataUnavailableError(f"HGNC database at {self._path} has no build metadata.")
        return dict(row)

    # -- gene records ----------------------------------------------------------

    def _gene_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for key in row.keys():  # noqa: SIM118 - sqlite3.Row iterates values, not keys
            if key == "symbol_upper":
                continue
            value = row[key]
            if key in LIST_FIELDS:
                record[key] = json.loads(value) if value else []
            else:
                record[key] = value
        return record

    def get_gene(self, hgnc_id: str) -> dict[str, Any] | None:
        """Return the full gene record for an HGNC ID, or ``None``."""
        row = self._conn.execute("SELECT * FROM gene WHERE hgnc_id = ?", (hgnc_id,)).fetchone()
        return self._gene_from_row(row) if row is not None else None

    def get_gene_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Return the gene whose approved symbol matches (case-insensitive)."""
        row = self._conn.execute(
            "SELECT * FROM gene WHERE symbol_upper = ?", (symbol.upper(),)
        ).fetchone()
        return self._gene_from_row(row) if row is not None else None

    # -- resolution ------------------------------------------------------------

    def lookup_symbol(self, symbol: str) -> list[tuple[str, str]]:
        """Return ``(hgnc_id, symbol_type)`` rows for a symbol, best type first."""
        rows = self._conn.execute(
            "SELECT hgnc_id, symbol_type FROM symbol_lookup WHERE lookup_symbol = ?",
            (symbol.upper(),),
        ).fetchall()
        pairs = [(r["hgnc_id"], r["symbol_type"]) for r in rows]
        pairs.sort(key=lambda p: _TYPE_PRIORITY.get(p[1], 9))
        return pairs

    def get_withdrawn(self, hgnc_id: str) -> dict[str, Any] | None:
        """Return a withdrawn record by HGNC ID, or ``None``."""
        row = self._conn.execute("SELECT * FROM withdrawn WHERE hgnc_id = ?", (hgnc_id,)).fetchone()
        return self._withdrawn_from_row(row) if row is not None else None

    def find_withdrawn_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """Return withdrawn records whose withdrawn symbol matches (case-insensitive)."""
        rows = self._conn.execute(
            "SELECT * FROM withdrawn WHERE withdrawn_symbol_upper = ?",
            (symbol.upper(),),
        ).fetchall()
        return [self._withdrawn_from_row(r) for r in rows]

    @staticmethod
    def _withdrawn_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "hgnc_id": row["hgnc_id"],
            "status": row["status"],
            "withdrawn_symbol": row["withdrawn_symbol"],
            "replaced_by": json.loads(row["replaced_by"]) if row["replaced_by"] else [],
        }

    # -- search ----------------------------------------------------------------

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """FTS search over symbol/name/alias/prev; returns ranked summary rows."""
        match = self._fts_query(query)
        sql = (
            "SELECT g.hgnc_id, g.symbol, g.name, g.locus_group, g.locus_type, "
            "g.status, g.location, bm25(gene_fts) AS rank "
            "FROM gene_fts JOIN gene g ON g.hgnc_id = gene_fts.hgnc_id "
            "WHERE gene_fts MATCH ? ORDER BY rank LIMIT ?"
        )
        try:
            rows = self._conn.execute(sql, (match, limit)).fetchall()
        except sqlite3.Error:
            rows = self._search_like(query, limit=limit)
        return [self._summary_from_row(r) for r in rows]

    def _search_like(self, query: str, *, limit: int) -> list[sqlite3.Row]:
        pattern = "%" + query.replace("%", "").replace("_", "") + "%"
        sql = (
            "SELECT hgnc_id, symbol, name, locus_group, locus_type, status, location, "
            "0.0 AS rank FROM gene "
            "WHERE symbol_upper LIKE ? OR UPPER(name) LIKE ? ORDER BY symbol LIMIT ?"
        )
        up = pattern.upper()
        return self._conn.execute(sql, (up, up, limit)).fetchall()

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> dict[str, Any]:
        rank = row["rank"]
        return {
            "hgnc_id": row["hgnc_id"],
            "symbol": row["symbol"],
            "name": row["name"],
            "locus_group": row["locus_group"],
            "locus_type": row["locus_type"],
            "status": row["status"],
            "location": row["location"],
            "score": round(-rank, 4) if rank else 0.0,
        }

    @staticmethod
    def _fts_query(text: str) -> str:
        """Build a safe FTS5 MATCH string (token OR, last token prefix-matched)."""
        tokens = _FTS_TOKEN_RE.findall(text or "")
        if not tokens:
            return '""'
        quoted = [f'"{tok}"' for tok in tokens[:-1]]
        quoted.append(f'"{tokens[-1]}"*')
        return " OR ".join(quoted)

    # -- cross references ------------------------------------------------------

    def lookup_by_xref(self, source: str, value: str) -> list[str]:
        """Return HGNC IDs whose ``source`` cross-reference equals ``value``."""
        rows = self._conn.execute(
            "SELECT DISTINCT hgnc_id FROM xref WHERE source = ? AND value_upper = ?",
            (source, value.strip().upper()),
        ).fetchall()
        return [r["hgnc_id"] for r in rows]

    # -- gene groups -----------------------------------------------------------

    def group_members(self, *, group_id: str | None, group_name: str | None) -> list[str]:
        """Return HGNC IDs belonging to a gene group, ordered by symbol.

        The stable, global symbol ordering (resolved in SQL via a join to ``gene``)
        is what makes ``offset``/``limit`` pagination partition the membership
        without overlaps or skips.
        """
        if group_id is not None:
            rows = self._conn.execute(
                "SELECT DISTINCT gg.hgnc_id, g.symbol FROM gene_group gg "
                "JOIN gene g ON g.hgnc_id = gg.hgnc_id "
                "WHERE gg.group_id = ? ORDER BY g.symbol, gg.hgnc_id",
                (str(group_id),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT DISTINCT gg.hgnc_id, g.symbol FROM gene_group gg "
                "JOIN gene g ON g.hgnc_id = gg.hgnc_id "
                "WHERE UPPER(gg.group_name) = ? ORDER BY g.symbol, gg.hgnc_id",
                ((group_name or "").upper(),),
            ).fetchall()
        return [r["hgnc_id"] for r in rows]

    def resolve_group_name(self, name: str) -> list[dict[str, str]]:
        """Return ``{group_id, group_name}`` entries matching a name (LIKE)."""
        rows = self._conn.execute(
            "SELECT DISTINCT group_id, group_name FROM gene_group "
            "WHERE UPPER(group_name) LIKE ? ORDER BY group_name",
            (f"%{name.upper()}%",),
        ).fetchall()
        return [{"group_id": r["group_id"], "group_name": r["group_name"]} for r in rows]

    def group_name_for_id(self, group_id: str) -> str | None:
        """Return the display name for a group id, or ``None``."""
        row = self._conn.execute(
            "SELECT group_name FROM gene_group WHERE group_id = ? LIMIT 1",
            (str(group_id),),
        ).fetchone()
        return row["group_name"] if row is not None else None

    def close(self) -> None:
        """Release the underlying database connection."""
        self._conn.close()


def normalize_id_query(value: str) -> str | None:
    """Convenience re-export: canonical ``HGNC:NNNN`` form, or ``None``."""
    return normalize_hgnc_id(value)
