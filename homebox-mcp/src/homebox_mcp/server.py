"""Homebox AI MCP Server — entry point.

Provides LLM tool access to a Homebox inventory instance.
Run: python -m homebox_mcp.server
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from homebox_mcp.client import HomeboxClient
from homebox_mcp.config import settings
from homebox_mcp.session import SessionManager


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Initialize shared resources available to all tools."""
    client = HomeboxClient(
        base_url=settings.homebox_url,
        email=settings.homebox_email,
        password=settings.homebox_password,
    )
    await client.connect()

    session_mgr = SessionManager(settings.session_file)
    session_mgr.load()

    yield {"client": client, "sessions": session_mgr}

    session_mgr.save()
    await client.close()


mcp = FastMCP("homebox_mcp", lifespan=app_lifespan, host="0.0.0.0", port=settings.mcp_port, stateless_http=True)

from homebox_mcp.tools.locations import register_tools as register_location_tools
from homebox_mcp.tools.items import register_tools as register_item_tools
from homebox_mcp.tools.session import register_tools as register_session_tools

register_location_tools(mcp)
register_item_tools(mcp)
register_session_tools(mcp)


def main():
    """Run the MCP server with streamable HTTP transport."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
