"""MCP facade for hgnc-link."""

from __future__ import annotations

from fastmcp import FastMCP

from hgnc_link import __version__
from hgnc_link.mcp.capabilities import register_capability_resources
from hgnc_link.mcp.middleware import ArgValidationMiddleware
from hgnc_link.mcp.resources import HGNC_SERVER_INSTRUCTIONS
from hgnc_link.mcp.tools import (
    register_discovery_tools,
    register_gene_tools,
    register_group_tools,
    register_resolve_tools,
    register_xref_tools,
)


def create_hgnc_mcp() -> FastMCP:
    """Build a FastMCP instance with all hgnc-link tools and resources."""
    mcp = FastMCP(
        name="hgnc-link",
        version=__version__,
        instructions=HGNC_SERVER_INSTRUCTIONS,
        mask_error_details=True,
    )

    register_discovery_tools(mcp)
    register_resolve_tools(mcp)
    register_gene_tools(mcp)
    register_xref_tools(mcp)
    register_group_tools(mcp)
    register_capability_resources(mcp)
    mcp.add_middleware(ArgValidationMiddleware())

    return mcp
