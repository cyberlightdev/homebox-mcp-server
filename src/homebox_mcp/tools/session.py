"""Session tools: get state and undo last operation."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context, FastMCP

from homebox_mcp.client import HomeboxClient
from homebox_mcp.session import SessionManager


def register_tools(mcp: FastMCP) -> None:
    """Register session tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": True},
        description=(
            "Returns current session context: the active working location and the last mutating "
            "operation (for undo awareness)."
        ),
    )
    async def homebox_get_session(ctx: Context) -> str:
        sessions: SessionManager = ctx.request_context.lifespan_context["sessions"]
        session = sessions.get(ctx.client_id or "default")

        result = {
            "current_location": session.current_location,
            "last_operation": session.last_operation,
        }
        return json.dumps(result, indent=2)

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True},
        description=(
            "Undo the most recent mutating operation (create → delete, update → restore previous state). "
            "Returns a description of what was undone, or an error if nothing to undo."
        ),
    )
    async def homebox_undo_last(ctx: Context) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_context["client"]
        sessions: SessionManager = ctx.request_context.lifespan_context["sessions"]
        session = sessions.get(ctx.client_id or "default")

        op = session.last_operation
        if op is None:
            return "Nothing to undo."

        op_type = op["type"]
        entity_type = op["entity_type"]
        entity_id = op["entity_id"]
        summary = op["summary"]
        previous_state = op.get("previous_state")

        if op_type == "create":
            if entity_type == "item":
                await client.delete_item(entity_id)
            elif entity_type == "location":
                await client.delete_location(entity_id)
            else:
                return f"Cannot undo: unknown entity type '{entity_type}'."
        elif op_type == "update":
            if entity_type == "item" and previous_state:
                # Restore previous state — build a minimal update payload from snapshot
                payload = {
                    "id": entity_id,
                    "name": previous_state.get("name", ""),
                    "quantity": previous_state.get("quantity", 1),
                    "notes": previous_state.get("notes", ""),
                    "locationId": (
                        previous_state.get("location", {}).get("id", "")
                        if previous_state.get("location")
                        else ""
                    ),
                    "tagIds": [t["id"] for t in previous_state.get("tags", [])],
                }
                await client.update_item(entity_id, payload)
            else:
                return f"Cannot undo: no previous state recorded for this {entity_type} update."
        else:
            return f"Cannot undo operation of type '{op_type}'."

        session.clear_last_operation()
        sessions.save()
        return f"Undone: {summary}."
