"""MCP tool registration entry points."""

from __future__ import annotations

from hgnc_link.mcp.tools.discovery import register_discovery_tools
from hgnc_link.mcp.tools.genes import register_gene_tools
from hgnc_link.mcp.tools.groups import register_group_tools
from hgnc_link.mcp.tools.resolve import register_resolve_tools
from hgnc_link.mcp.tools.xref import register_xref_tools

__all__ = [
    "register_discovery_tools",
    "register_gene_tools",
    "register_group_tools",
    "register_resolve_tools",
    "register_xref_tools",
]
