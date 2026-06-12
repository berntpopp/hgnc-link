"""Shared annotated argument types for the MCP tools."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

ResponseMode = Annotated[
    Literal["minimal", "compact", "standard", "full"],
    Field(description="Verbosity: minimal | compact | standard | full (default compact)."),
]

QueryStr = Annotated[
    str,
    Field(
        description="A gene symbol (current/previous/alias, case-insensitive) or HGNC id "
        "(HGNC:1100 or 1100).",
        examples=["BRAF", "HGNC:1097", "MLL2", "1100"],
    ),
]
