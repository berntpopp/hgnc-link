"""Command-line interface for building and refreshing the HGNC index.

Exposed as the ``hgnc-link-data`` console script and intended as the cron entry
point. Commands: ``build`` (force a download + rebuild), ``refresh`` (conditional
rebuild — the cron job), and ``status`` (print provenance of the existing DB).
"""

from __future__ import annotations

import typer

from hgnc_link.config import get_data_config
from hgnc_link.exceptions import DownloadError
from hgnc_link.ingest.builder import BuildMeta, build_database, read_meta, rebuild
from hgnc_link.ingest.downloader import download_bulk

app = typer.Typer(
    add_completion=False,
    help="Build and refresh the local HGNC SQLite index from the bulk dumps.",
)


def _print_summary(meta: BuildMeta, *, header: str) -> None:
    """Print a compact provenance summary for a build."""
    print(header)
    print(f"  schema_version      : {meta.schema_version}")
    print(f"  release             : {meta.release}")
    print(f"  genes               : {meta.gene_count}")
    print(f"  withdrawn           : {meta.withdrawn_count}")
    print(f"  symbol_lookup_rows  : {meta.symbol_lookup_count}")
    print(f"  source_etag         : {meta.source_etag}")
    print(f"  source_last_modified: {meta.source_last_modified}")
    print(f"  built_utc           : {meta.build_utc}")
    if meta.build_duration_s is not None:
        print(f"  build_seconds       : {meta.build_duration_s}")


@app.command()
def build() -> None:
    """Force a download and full rebuild of the database."""
    config = get_data_config()
    try:
        download = download_bulk(config, force=True)
    except DownloadError as exc:
        print(f"ERROR: download failed: {exc}")
        raise typer.Exit(code=1) from exc
    if download.complete_set.path is None:
        print("ERROR: download produced no complete-set file.")
        raise typer.Exit(code=1)
    meta = build_database(
        config,
        complete_set_path=download.complete_set.path,
        withdrawn_path=download.withdrawn.path,
        etag=download.complete_set.etag,
        last_modified=download.complete_set.last_modified,
    )
    _print_summary(meta, header="Built HGNC database:")


@app.command()
def refresh() -> None:
    """Conditionally refresh the database; rebuild only if the dumps changed."""
    config = get_data_config()
    try:
        result = rebuild(config, force=False)
    except DownloadError as exc:
        print(f"ERROR: download failed: {exc}")
        raise typer.Exit(code=1) from exc
    if result.not_modified:
        print(f"HGNC database is up to date (source not modified; release {result.meta.release}).")
        return
    _print_summary(result.meta, header="HGNC database refreshed:")


@app.command()
def status() -> None:
    """Print provenance of the existing database, or a hint to build it."""
    config = get_data_config()
    meta = read_meta(config.db_path)
    if meta is None:
        print(f"No HGNC database at {config.db_path}.")
        print("Run `hgnc-link-data build` to download and build it.")
        raise typer.Exit(code=1)
    _print_summary(meta, header=f"HGNC database at {config.db_path}:")


def main() -> None:
    """Console-script entry point for ``hgnc-link-data``."""
    app()


if __name__ == "__main__":
    main()
