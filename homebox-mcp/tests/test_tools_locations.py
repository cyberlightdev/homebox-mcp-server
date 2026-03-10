"""Tests for location tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from homebox_mcp.tools.locations import _fuzzy_match_location


LOCATIONS = [
    {"id": "loc1", "name": "Storeroom", "description": "Main storage", "itemCount": 5},
    {"id": "loc2", "name": "Garage", "description": "Garage shelves", "itemCount": 2},
    {"id": "loc3", "name": "Storage Unit", "description": "", "itemCount": 0},
]


def _make_ctx(client, sessions, client_id="test-session"):
    """Build a minimal mock Context with lifespan_context."""
    ctx = MagicMock()
    ctx.client_id = client_id
    ctx.request_context.lifespan_context = {"client": client, "sessions": sessions}
    return ctx


# --- _fuzzy_match_location helper ---

def test_fuzzy_match_exact():
    results = _fuzzy_match_location("Storeroom", LOCATIONS)
    assert len(results) == 1
    assert results[0]["id"] == "loc1"


def test_fuzzy_match_partial():
    results = _fuzzy_match_location("Storage", LOCATIONS, score_cutoff=50)
    ids = {r["id"] for r in results}
    assert "loc3" in ids


def test_fuzzy_match_no_results():
    results = _fuzzy_match_location("Basement", LOCATIONS)
    assert results == []


def test_fuzzy_match_empty_locations():
    results = _fuzzy_match_location("Storeroom", [])
    assert results == []


# --- Tool function tests via internal registration ---

def _get_tool_fn(mcp, name: str):
    """Extract the underlying async function from a registered FastMCP tool."""
    return mcp._tool_manager._tools[name].fn


async def test_set_location_single_match(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.locations import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_set_location")
    result = await fn(name="Storeroom", ctx=ctx)

    assert "Storeroom" in result
    session = session_manager.get("test-session")
    assert session.current_location["id"] == "loc1"


async def test_set_location_no_match(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.locations import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_set_location")
    result = await fn(name="Basement", ctx=ctx)

    assert "No location found" in result


async def test_set_location_multiple_matches_returns_candidates(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.locations import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_set_location")
    # "Store" should match both "Storeroom" and "Storage Unit"
    result = await fn(name="Store", ctx=ctx)

    assert "Multiple" in result or "loc1" in result  # either narrows or lists


async def test_create_location_with_parent(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.locations import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mock_client.create_location.return_value = {
        "id": "loc-new", "name": "Blue Bin #1", "description": "", "createdAt": "", "updatedAt": ""
    }
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_create_location")
    result = await fn(name="Blue Bin #1", ctx=ctx, parent_name="Storeroom")

    assert "Blue Bin #1" in result
    mock_client.create_location.assert_called_once()
    call_data = mock_client.create_location.call_args[0][0]
    assert call_data["parentId"] == "loc1"


async def test_search_locations_found(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.locations import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_search_locations")
    result = await fn(query="Garage", ctx=ctx)

    assert "Garage" in result
    assert "loc2" in result


async def test_search_locations_not_found(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.locations import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_search_locations")
    result = await fn(query="Basement", ctx=ctx)

    assert "No locations found" in result
