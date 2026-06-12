"""Prove the live-assessment probes against the REAL index via the real facade.

Run: uv run python scripts/verify_live_fix.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from hgnc_link.config import settings
from hgnc_link.data.repository import HgncRepository
from hgnc_link.mcp.facade import create_hgnc_mcp
from hgnc_link.mcp.service_adapters import set_hgnc_service
from hgnc_link.services.hgnc_service import HgncService


def _sc(result: Any) -> dict[str, Any]:
    sc = result.structured_content
    return sc if isinstance(sc, dict) else json.loads(result.content[0].text)


async def main() -> None:
    db = Path(settings.data.db_path)
    assert db.exists(), f"index missing at {db}"
    repo = HgncRepository(db)
    set_hgnc_service(HgncService(repo))
    mcp = create_hgnc_mcp()
    failures: list[str] = []

    # 1. The blocker: ambiguous resolve_symbol must NOT crash; clean ambiguous_query.
    for sym in ("p65", "PP1", "HCG", "ACSM2"):
        p = _sc(await mcp.call_tool("resolve_symbol", {"query": sym}))
        ok = (
            p.get("success") is False
            and p.get("error_code") == "ambiguous_query"
            and p.get("candidates")
        )
        print(
            f"resolve_symbol({sym!r}): success={p.get('success')} "
            f"error_code={p.get('error_code')} candidates={len(p.get('candidates') or [])}"
        )
        if not ok:
            failures.append(f"resolve_symbol({sym!r}) not a clean ambiguous_query: {p}")

    # 2. Finding #2: databases=['mane'] must resolve, not silently empty.
    p = _sc(
        await mcp.call_tool("get_gene_cross_references", {"query": "PKD1", "databases": ["mane"]})
    )
    print(
        f"PKD1 databases=['mane']: success={p.get('success')} "
        f"count={p.get('database_count')} keys={list((p.get('cross_references') or {}).keys())}"
    )
    if not (p.get("success") and "mane_select" in (p.get("cross_references") or {})):
        failures.append(f"PKD1 mane filter failed: {p}")

    # 3. Finding #4: compact xrefs include the high-value fields.
    p = _sc(await mcp.call_tool("get_gene_cross_references", {"query": "PKD1"}))
    keys = set(p.get("cross_references") or {})
    print(f"PKD1 compact xref keys: {sorted(keys)}")
    if not {"mane_select", "uniprot_ids", "omim_id"} <= keys:
        failures.append(f"compact xrefs missing high-value fields: {sorted(keys)}")

    # 4. Build provenance surfaced in capabilities.
    p = _sc(await mcp.call_tool("get_server_capabilities", {}))
    build = p.get("build") or {}
    print(f"build provenance: git_sha={build.get('git_sha')} built_at={build.get('built_at')}")
    if not build.get("git_sha") or build.get("git_sha") == "unknown":
        failures.append(f"build git_sha not populated: {build}")

    # 5. Pagination on a large group: truncated + next_offset + continuation command.
    p = _sc(await mcp.call_tool("get_gene_group", {"group": "1157", "limit": 1}))
    print(
        f"group 1157 limit=1: member_count={p.get('member_count')} "
        f"truncated={p.get('truncated')} next_offset={p.get('next_offset')}"
    )

    repo.close()
    set_hgnc_service(None)
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("\nALL LIVE PROBES PASS against the real index.")


if __name__ == "__main__":
    asyncio.run(main())
