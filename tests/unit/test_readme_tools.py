"""The README's ``## Tools`` table must match the server's registered tools exactly.

The table is the repo's front door and the one README section permitted to grow with
the server (GeneFoundry README Standard v1, rule 6). Hand-maintained, it silently
drifts the first time a tool is added or renamed — this test is what stops that.

The live tool list comes from the same ``facade`` fixture ``test_tool_names.py`` uses,
never from a hardcoded copy: a hardcoded list would drift in lockstep with the README
and guard nothing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

README = Path(__file__).resolve().parents[2] / "README.md"

#: A table row whose first cell is a backticked tool name: ``| `resolve_symbol` | … |``.
_TOOL_ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|")


def _tools_section() -> list[str]:
    """The lines between the ``## Tools`` heading and the next H2."""
    lines = README.read_text(encoding="utf-8").splitlines()
    assert "## Tools" in lines, "README.md has no '## Tools' section"
    start = lines.index("## Tools")

    section: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        section.append(line)
    return section


def _documented_tool_names() -> set[str]:
    names = {match.group(1) for line in _tools_section() if (match := _TOOL_ROW.match(line))}
    assert names, "no tool rows parsed from the README '## Tools' table"
    return names


async def test_readme_tools_table_matches_registered_tools(facade: Any) -> None:
    registered = {tool.name for tool in await facade.list_tools()}
    assert registered, "no tools registered on the facade"

    documented = _documented_tool_names()

    undocumented = registered - documented
    assert not undocumented, (
        f"tools are registered but missing from the README '## Tools' table: "
        f"{sorted(undocumented)}. Add a row for each."
    )

    phantom = documented - registered
    assert not phantom, (
        f"the README '## Tools' table lists tools that are not registered: "
        f"{sorted(phantom)}. Remove the stale rows."
    )

    assert documented == registered
