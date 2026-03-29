"""Compatibility shim for the canonical Forkit MCP server."""

from forkit.mcp.server import ForkitMCPService, build_mcp_server, main, serve_stdio

__all__ = ["ForkitMCPService", "build_mcp_server", "serve_stdio", "main"]
