"""Atomic SQLite builder for the HGNC bulk dumps.

Streams the complete-set genes and withdrawn list into a temporary database,
builds the exploded resolution / cross-reference / gene-group indexes and the
FTS5 table, records provenance in ``meta``, then atomically swaps the finished
file into place. Callers get back a typed :class:`BuildMeta`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hgnc_link.constants import LIST_FIELDS, SCHEMA_VERSION
from hgnc_link.data import load_schema_sql
from hgnc_link.exceptions import DataUnavailableError
from hgnc_link.ingest.downloader import BulkDownload, download_bulk
from hgnc_link.ingest.lock import build_lock
from hgnc_link.ingest.parser import (
    group_rows,
    iter_normalized_genes,
    parse_withdrawn,
    symbol_lookup_rows,
    xref_rows,
)

if TYPE_CHECKING:
    from hgnc_link.config import HgncDataConfig

_GENE_COLUMNS: tuple[str, ...] = (
    "hgnc_id",
    "symbol",
    "symbol_upper",
    "name",
    "status",
    "locus_group",
    "locus_type",
    "location",
    "location_sortable",
    "entrez_id",
    "ensembl_gene_id",
    "vega_id",
    "ucsc_id",
    "cosmic",
    "orphanet",
    "agr",
    "date_approved_reserved",
    "date_symbol_changed",
    "date_name_changed",
    "date_modified",
    "uuid",
    *LIST_FIELDS,
)
_INSERT_BATCH = 2000


@dataclass
class BuildMeta:
    """Provenance for a built HGNC index database (one ``meta`` row)."""

    schema_version: int
    release: str | None
    source_complete_set_url: str
    source_withdrawn_url: str
    source_etag: str | None
    source_last_modified: str | None
    gene_count: int
    withdrawn_count: int
    symbol_lookup_count: int
    build_utc: str
    build_duration_s: float | None


@dataclass
class RebuildResult:
    """Outcome of a conditional refresh/rebuild."""

    meta: BuildMeta
    changed: bool
    not_modified: bool


def _gene_value(gene: dict[str, Any], column: str) -> Any:
    if column == "symbol_upper":
        symbol = gene.get("symbol") or ""
        return symbol.upper()
    if column in LIST_FIELDS:
        return json.dumps(gene.get(column, []))
    return gene.get(column)


def _load_genes(conn: sqlite3.Connection, genes: list[dict[str, Any]]) -> int:
    # Column names come from the hardcoded _GENE_COLUMNS tuple, never user input.
    gene_cols = ", ".join(_GENE_COLUMNS)
    gene_ph = ", ".join("?" for _ in _GENE_COLUMNS)
    gene_sql = f"INSERT OR REPLACE INTO gene ({gene_cols}) VALUES ({gene_ph})"  # noqa: S608
    lookup_sql = "INSERT INTO symbol_lookup (lookup_symbol, hgnc_id, symbol_type) VALUES (?, ?, ?)"
    xref_sql = "INSERT INTO xref (source, value_upper, value, hgnc_id) VALUES (?, ?, ?, ?)"
    group_sql = "INSERT INTO gene_group (group_id, group_name, hgnc_id) VALUES (?, ?, ?)"
    fts_sql = "INSERT INTO gene_fts (hgnc_id, symbol, name, alias_symbol, prev_symbol) VALUES (?, ?, ?, ?, ?)"

    gene_batch: list[tuple[Any, ...]] = []
    lookup_batch: list[tuple[str, str, str]] = []
    xref_batch: list[tuple[str, str, str, str]] = []
    group_batch: list[tuple[str, str, str]] = []
    fts_batch: list[tuple[Any, ...]] = []
    count = 0

    for gene in genes:
        gene_batch.append(tuple(_gene_value(gene, col) for col in _GENE_COLUMNS))
        lookup_batch.extend(symbol_lookup_rows(gene))
        xref_batch.extend(xref_rows(gene))
        group_batch.extend(group_rows(gene))
        fts_batch.append(
            (
                gene["hgnc_id"],
                gene.get("symbol") or "",
                gene.get("name") or "",
                " ".join(gene.get("alias_symbol", [])),
                " ".join(gene.get("prev_symbol", [])),
            )
        )
        count += 1
        if len(gene_batch) >= _INSERT_BATCH:
            conn.executemany(gene_sql, gene_batch)
            conn.executemany(lookup_sql, lookup_batch)
            conn.executemany(xref_sql, xref_batch)
            conn.executemany(group_sql, group_batch)
            conn.executemany(fts_sql, fts_batch)
            gene_batch, lookup_batch, xref_batch, group_batch, fts_batch = [], [], [], [], []

    if gene_batch:
        conn.executemany(gene_sql, gene_batch)
        conn.executemany(lookup_sql, lookup_batch)
        conn.executemany(xref_sql, xref_batch)
        conn.executemany(group_sql, group_batch)
        conn.executemany(fts_sql, fts_batch)
    return count


def _load_withdrawn(conn: sqlite3.Connection, withdrawn_text: str) -> int:
    sql = (
        "INSERT OR REPLACE INTO withdrawn "
        "(hgnc_id, status, withdrawn_symbol, withdrawn_symbol_upper, replaced_by) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    rows = parse_withdrawn(withdrawn_text)
    batch = [
        (
            r["hgnc_id"],
            r["status"],
            r["withdrawn_symbol"],
            (r["withdrawn_symbol"] or "").upper(),
            json.dumps(r["replaced_by"]),
        )
        for r in rows
    ]
    if batch:
        conn.executemany(sql, batch)
    return len(batch)


def _insert_meta(conn: sqlite3.Connection, meta: BuildMeta) -> None:
    values = asdict(meta)
    columns = list(values.keys())  # dataclass field names, not user input
    placeholders = ", ".join("?" for _ in columns)
    col_list = ", ".join(columns)
    conn.execute(
        f"INSERT INTO meta (id, {col_list}) VALUES (1, {placeholders})",  # noqa: S608
        tuple(values[col] for col in columns),
    )


def build_database(
    config: HgncDataConfig,
    *,
    complete_set_path: Path,
    withdrawn_path: Path | None,
    etag: str | None,
    last_modified: str | None,
) -> BuildMeta:
    """Build the HGNC SQLite index from the dump files, atomically."""
    start = time.perf_counter()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=config.data_dir, suffix=".sqlite.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        conn = sqlite3.connect(tmp_path)
        try:
            conn.executescript(load_schema_sql())
            genes = iter_normalized_genes(complete_set_path)
            gene_count = _load_genes(conn, genes)
            withdrawn_count = 0
            if withdrawn_path is not None and withdrawn_path.exists():
                withdrawn_count = _load_withdrawn(conn, withdrawn_path.read_text(encoding="utf-8"))
            symbol_lookup_count = conn.execute("SELECT COUNT(*) FROM symbol_lookup").fetchone()[0]
            conn.execute("INSERT INTO gene_fts(gene_fts) VALUES ('optimize')")

            meta = BuildMeta(
                schema_version=SCHEMA_VERSION,
                release=_release_date(last_modified),
                source_complete_set_url=config.complete_set_url,
                source_withdrawn_url=config.withdrawn_url,
                source_etag=etag,
                source_last_modified=last_modified,
                gene_count=gene_count,
                withdrawn_count=withdrawn_count,
                symbol_lookup_count=symbol_lookup_count,
                build_utc=datetime.now(tz=UTC).isoformat(),
                build_duration_s=round(time.perf_counter() - start, 3),
            )
            _insert_meta(conn, meta)
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp_path, config.db_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return meta


def _release_date(last_modified: str | None) -> str | None:
    """Derive a human-readable release date from the source Last-Modified header."""
    return last_modified


def read_meta(db_path: Path) -> BuildMeta | None:
    """Read provenance from an existing database, or ``None`` if absent."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM meta WHERE id = 1").fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return BuildMeta(
        schema_version=row["schema_version"],
        release=row["release"],
        source_complete_set_url=row["source_complete_set_url"],
        source_withdrawn_url=row["source_withdrawn_url"],
        source_etag=row["source_etag"],
        source_last_modified=row["source_last_modified"],
        gene_count=row["gene_count"],
        withdrawn_count=row["withdrawn_count"],
        symbol_lookup_count=row["symbol_lookup_count"],
        build_utc=row["build_utc"],
        build_duration_s=row["build_duration_s"],
    )


def _build_from_download(config: HgncDataConfig, download: BulkDownload) -> BuildMeta:
    if download.complete_set.path is None:
        raise DataUnavailableError("Download reported no complete-set file to build from.")
    return build_database(
        config,
        complete_set_path=download.complete_set.path,
        withdrawn_path=download.withdrawn.path,
        etag=download.complete_set.etag,
        last_modified=download.complete_set.last_modified,
    )


def ensure_database(config: HgncDataConfig) -> Path:
    """Return the database path, building it on first use if configured."""
    if config.db_path.exists():
        return config.db_path
    if not config.auto_bootstrap:
        raise DataUnavailableError(
            "HGNC database not built. Run `hgnc-link-data build` (or `make data`)."
        )
    with build_lock(config.data_dir, timeout=config.build_lock_timeout):
        if config.db_path.exists():  # double-checked locking
            return config.db_path
        download = download_bulk(config)
        _build_from_download(config, download)
    return config.db_path


def rebuild(config: HgncDataConfig, *, force: bool) -> RebuildResult:
    """Download (conditionally) and rebuild the database under the build lock."""
    with build_lock(config.data_dir, timeout=config.build_lock_timeout):
        download = download_bulk(config, force=force)
        if not download.changed and config.db_path.exists():
            existing = read_meta(config.db_path)
            if existing is not None:
                return RebuildResult(meta=existing, changed=False, not_modified=True)
        meta = _build_from_download(config, download)
    return RebuildResult(meta=meta, changed=True, not_modified=False)
