"""Tests for item tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from homebox_mcp.tools.items import _resolve_location_id, _resolve_tag_ids
from homebox_mcp.session import Session


LOCATIONS = [
    {"id": "loc1", "name": "Storeroom", "description": "", "itemCount": 5},
    {"id": "loc2", "name": "Garage", "description": "", "itemCount": 2},
]

ITEMS = [
    {
        "id": "item1",
        "name": "Red Ball",
        "quantity": 3,
        "description": "",
        "location": {"id": "loc1", "name": "Storeroom"},
        "tags": [],
        "notes": "",
    }
]


def _make_ctx(client, sessions, client_id="test-session"):
    ctx = MagicMock()
    ctx.client_id = client_id
    ctx.request_context.lifespan_context = {"client": client, "sessions": sessions}
    return ctx


def _get_tool_fn(mcp, name: str):
    return mcp._tool_manager._tools[name].fn


# --- _resolve_location_id helper ---

async def test_resolve_location_by_name(mock_client):
    mock_client.list_locations.return_value = LOCATIONS
    session = Session()
    loc_id, loc_name = await _resolve_location_id("Storeroom", mock_client, session)
    assert loc_id == "loc1"
    assert loc_name == "Storeroom"


async def test_resolve_location_falls_back_to_session(mock_client):
    session = Session()
    session.set_location({"id": "loc2", "name": "Garage"})
    loc_id, loc_name = await _resolve_location_id(None, mock_client, session)
    assert loc_id == "loc2"
    assert loc_name == "Garage"
    mock_client.list_locations.assert_not_called()


async def test_resolve_location_no_location_raises(mock_client):
    session = Session()
    with pytest.raises(ValueError, match="No location specified"):
        await _resolve_location_id(None, mock_client, session)


async def test_resolve_location_not_found_raises(mock_client):
    mock_client.list_locations.return_value = LOCATIONS
    session = Session()
    with pytest.raises(ValueError, match="No location found"):
        await _resolve_location_id("Basement", mock_client, session)


# --- _resolve_tag_ids helper ---

async def test_resolve_tag_ids_existing(mock_client):
    mock_client.list_tags.return_value = [{"id": "tag1", "name": "fragile"}]
    ids = await _resolve_tag_ids(["fragile"], mock_client)
    assert ids == ["tag1"]
    mock_client.create_tag.assert_not_called()


async def test_resolve_tag_ids_creates_missing(mock_client):
    mock_client.list_tags.return_value = []
    mock_client.create_tag.return_value = {"id": "tag-new", "name": "electronics"}
    ids = await _resolve_tag_ids(["electronics"], mock_client)
    assert ids == ["tag-new"]
    mock_client.create_tag.assert_called_once_with({"name": "electronics"})


# --- homebox_search_items ---

async def test_search_items_returns_results(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.items import register_tools

    mock_client.list_items.return_value = ITEMS
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_search_items")
    result = await fn(query="Red Ball", ctx=ctx)

    assert "Red Ball" in result
    assert "item1" in result


async def test_search_items_no_results(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.items import register_tools

    mock_client.list_items.return_value = []
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_search_items")
    result = await fn(query="Unicorn", ctx=ctx)

    assert "No items found" in result


# --- homebox_add_item ---

async def test_add_item_logs_operation(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.items import register_tools

    mock_client.list_locations.return_value = LOCATIONS
    mock_client.create_item.return_value = {"id": "item-new", "name": "Hammer"}
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_add_item")
    result = await fn(name="Hammer", ctx=ctx, location_name="Storeroom", quantity=1)

    assert "Hammer" in result
    session = session_manager.get("test-session")
    assert session.last_operation is not None
    assert session.last_operation["type"] == "create"
    assert session.last_operation["entity_id"] == "item-new"


async def test_add_item_no_location_returns_error(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.items import register_tools

    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_add_item")
    result = await fn(name="Hammer", ctx=ctx)  # no location, no session location

    assert "No location specified" in result


# --- homebox_update_item ---

async def test_update_item_snapshots_previous_state(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.items import register_tools

    current_item = {
        "id": "item1",
        "name": "Red Ball",
        "quantity": 3,
        "notes": "",
        "location": {"id": "loc1", "name": "Storeroom"},
        "tags": [],
    }
    mock_client.get_item.return_value = current_item
    mock_client.update_item.return_value = {**current_item, "quantity": 5}
    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_update_item")
    result = await fn(item_id="item1", ctx=ctx, quantity=5)

    session = session_manager.get("test-session")
    assert session.last_operation["type"] == "update"
    assert session.last_operation["previous_state"]["quantity"] == 3
    assert "quantity" in result
