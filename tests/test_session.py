"""Tests for Session, SessionManager, and session tools."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from homebox_mcp.session import Session, SessionManager


def _make_ctx(client, sessions, client_id="test-session"):
    ctx = MagicMock()
    ctx.client_id = client_id
    ctx.request_context.lifespan_state = {"client": client, "sessions": sessions}
    return ctx


def _get_tool_fn(mcp, name: str):
    return mcp._tool_manager._tools[name].fn


# --- Session dataclass ---

def test_session_set_location_updates(session):
    session.set_location({"id": "loc1", "name": "Storeroom"})
    assert session.current_location["name"] == "Storeroom"


def test_session_log_operation(session):
    session.log_operation("create", "item", "item1", "Added hammer", previous_state=None)
    assert session.last_operation["type"] == "create"
    assert session.last_operation["entity_id"] == "item1"
    assert session.last_operation["previous_state"] is None


def test_session_clear_last_operation(session):
    session.log_operation("create", "item", "item1", "Added hammer")
    session.clear_last_operation()
    assert session.last_operation is None


# --- SessionManager persistence ---

def test_session_manager_get_creates_new(session_manager):
    s = session_manager.get("abc")
    assert isinstance(s, Session)
    s2 = session_manager.get("abc")
    assert s is s2


def test_session_manager_save_and_load(tmp_path):
    mgr = SessionManager(str(tmp_path / "sessions.json"))
    s = mgr.get("user1")
    s.set_location({"id": "loc1", "name": "Storeroom"})
    mgr.save()

    mgr2 = SessionManager(str(tmp_path / "sessions.json"))
    mgr2.load()
    s2 = mgr2.get("user1")
    assert s2.current_location["id"] == "loc1"


def test_session_manager_load_handles_corrupt_file(tmp_path):
    f = tmp_path / "sessions.json"
    f.write_text("not valid json")
    mgr = SessionManager(str(f))
    mgr.load()  # should not raise
    s = mgr.get("default")
    assert s.current_location is None


# --- homebox_get_session ---

async def test_get_session_returns_state(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.session import register_tools

    mcp = FastMCP("test")
    register_tools(mcp)

    session = session_manager.get("test-session")
    session.set_location({"id": "loc1", "name": "Storeroom"})

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_get_session")
    result = await fn(ctx=ctx)

    data = json.loads(result)
    assert data["current_location"]["name"] == "Storeroom"
    assert data["last_operation"] is None


# --- homebox_undo_last ---

async def test_undo_create_item_calls_delete(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.session import register_tools

    mcp = FastMCP("test")
    register_tools(mcp)

    session = session_manager.get("test-session")
    session.log_operation("create", "item", "item1", "Added Hammer")

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_undo_last")
    result = await fn(ctx=ctx)

    mock_client.delete_item.assert_called_once_with("item1")
    assert "Undone" in result
    assert session.last_operation is None


async def test_undo_update_item_restores_state(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.session import register_tools

    mcp = FastMCP("test")
    register_tools(mcp)

    previous_state = {
        "id": "item1",
        "name": "Red Ball",
        "quantity": 3,
        "notes": "",
        "location": {"id": "loc1", "name": "Storeroom"},
        "tags": [],
    }
    mock_client.update_item.return_value = previous_state

    session = session_manager.get("test-session")
    session.log_operation("update", "item", "item1", "Updated Red Ball", previous_state=previous_state)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_undo_last")
    result = await fn(ctx=ctx)

    mock_client.update_item.assert_called_once()
    assert "Undone" in result
    assert session.last_operation is None


async def test_undo_nothing_to_undo(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.session import register_tools

    mcp = FastMCP("test")
    register_tools(mcp)

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_undo_last")
    result = await fn(ctx=ctx)

    assert "Nothing to undo" in result


async def test_undo_create_location_calls_delete(mock_client, session_manager):
    from mcp.server.fastmcp import FastMCP
    from homebox_mcp.tools.session import register_tools

    mcp = FastMCP("test")
    register_tools(mcp)

    session = session_manager.get("test-session")
    session.log_operation("create", "location", "loc-new", "Created Blue Bin #1")

    ctx = _make_ctx(mock_client, session_manager)
    fn = _get_tool_fn(mcp, "homebox_undo_last")
    result = await fn(ctx=ctx)

    mock_client.delete_location.assert_called_once_with("loc-new")
    assert "Undone" in result
