"""
core.mcp – MCP (Model Context Protocol) server management.

Public API::

    from core.mcp import McpServerRegistry, McpClient
"""

from .client import McpClient
from .registry import McpServerRegistry

__all__ = ["McpClient", "McpServerRegistry"]
