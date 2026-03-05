"""Item management tools: add, search, update."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context, FastMCP
from thefuzz import process as fuzz_process

from homebox_mcp.client import HomeboxClient
from homebox_mcp.session import Session, SessionManager


async def _resolve_location_id(
    location_name: str | None,
    client: HomeboxClient,
    session: Session,
) -> tuple[str, str]:
    """Resolve a location name to (id, name). Falls back to session current_location.

    Returns (location_id, location_name) or raises ValueError with a user-friendly message.
    """
    if location_name:
        locations = await client.list_locations()
        choices = {loc["id"]: loc["name"] for loc in locations}
        matches = fuzz_process.extractBests(location_name, choices, score_cutoff=60)
        if not matches:
            raise ValueError(
                f"No location found matching '{location_name}'. "
                "Use homebox_search_locations to find available locations."
            )
        if len(matches) > 1:
            candidates = [
                {"id": loc_id, "name": loc_name}
                for loc_name, _, loc_id in matches
            ]
            raise ValueError(
                f"Multiple locations match '{location_name}'. Please be more specific:\n"
                + json.dumps(candidates, indent=2)
            )
        loc_name, _, loc_id = matches[0]
        return loc_id, loc_name

    if session.current_location:
        return session.current_location["id"], session.current_location["name"]

    raise ValueError(
        "No location specified and no current location set. "
        "Use homebox_set_location first or provide a location_name."
    )


async def _resolve_tag_ids(labels: list[str], client: HomeboxClient) -> list[str]:
    """Resolve label names to tag IDs, creating tags that don't exist."""
    existing = await client.list_tags()
    name_to_id = {tag["name"].lower(): tag["id"] for tag in existing}
    tag_ids = []
    for label in labels:
        key = label.lower()
        if key in name_to_id:
            tag_ids.append(name_to_id[key])
        else:
            new_tag = await client.create_tag({"name": label})
            tag_ids.append(new_tag["id"])
    return tag_ids


def register_tools(mcp: FastMCP) -> None:
    """Register item tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": True},
        description=(
            "Search for items by name/description. Use before homebox_add_item to check for duplicates. "
            "Optionally scope search to a specific location by name."
        ),
    )
    async def homebox_search_items(
        query: str,
        ctx: Context,
        location_name: str | None = None,
    ) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_state["client"]
        sessions: SessionManager = ctx.request_context.lifespan_state["sessions"]
        session = sessions.get(ctx.client_id)

        location_id = ""
        if location_name:
            try:
                location_id, _ = await _resolve_location_id(location_name, client, session)
            except ValueError as e:
                return str(e)

        items = await client.list_items(query=query, location_id=location_id)

        if not items:
            return f"No items found matching '{query}'."

        results = [
            {
                "id": item["id"],
                "name": item["name"],
                "quantity": item.get("quantity", 1),
                "location": item.get("location", {}).get("name", "") if item.get("location") else "",
                "description": item.get("description", ""),
            }
            for item in items
        ]
        return json.dumps(results, indent=2)

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False},
        description=(
            "Adds a new item to Homebox. Does NOT auto-deduplicate — call homebox_search_items "
            "first and decide whether to create or update. "
            "Defaults to the current session location if location_name is not provided. "
            "Labels are created as tags if they don't already exist."
        ),
    )
    async def homebox_add_item(
        name: str,
        ctx: Context,
        quantity: int = 1,
        location_name: str | None = None,
        notes: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_state["client"]
        sessions: SessionManager = ctx.request_context.lifespan_state["sessions"]
        session = sessions.get(ctx.client_id)

        try:
            location_id, resolved_location_name = await _resolve_location_id(
                location_name, client, session
            )
        except ValueError as e:
            return str(e)

        tag_ids: list[str] = []
        if labels:
            tag_ids = await _resolve_tag_ids(labels, client)

        payload: dict = {
            "name": name,
            "quantity": quantity,
            "locationId": location_id,
        }
        if notes:
            payload["notes"] = notes
        if tag_ids:
            payload["tagIds"] = tag_ids

        result = await client.create_item(payload)
        item_id = result["id"]

        session.log_operation(
            op_type="create",
            entity_type="item",
            entity_id=item_id,
            summary=f"Added '{name}' (qty: {quantity}) to '{resolved_location_name}'",
        )
        sessions.save()

        qty_str = f"{quantity}× " if quantity != 1 else ""
        return f"Added {qty_str}'{name}' to '{resolved_location_name}' (id: {item_id})."

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
        description=(
            "Modify an existing item's quantity, notes, location, or name. "
            "Provide the item_id from homebox_search_items results. "
            "Only specified fields are changed; others keep their current values. "
            "Supports undo via homebox_undo_last."
        ),
    )
    async def homebox_update_item(
        item_id: str,
        ctx: Context,
        quantity: int | None = None,
        notes: str | None = None,
        location_name: str | None = None,
        name: str | None = None,
    ) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_state["client"]
        sessions: SessionManager = ctx.request_context.lifespan_state["sessions"]
        session = sessions.get(ctx.client_id)

        current = await client.get_item(item_id)

        # Build update payload starting from current values (PUT requires full object)
        payload: dict = {
            "id": item_id,
            "name": name if name is not None else current.get("name", ""),
            "quantity": quantity if quantity is not None else current.get("quantity", 1),
            "notes": notes if notes is not None else current.get("notes", ""),
            "locationId": current.get("location", {}).get("id", "") if current.get("location") else "",
            "tagIds": [t["id"] for t in current.get("tags", [])],
        }

        if location_name is not None:
            try:
                new_loc_id, _ = await _resolve_location_id(location_name, client, session)
                payload["locationId"] = new_loc_id
            except ValueError as e:
                return str(e)

        result = await client.update_item(item_id, payload)

        changes = []
        if name is not None:
            changes.append(f"name → '{name}'")
        if quantity is not None:
            changes.append(f"quantity → {quantity}")
        if notes is not None:
            changes.append("notes updated")
        if location_name is not None:
            changes.append(f"location → '{location_name}'")

        summary = f"Updated '{current.get('name', item_id)}': " + ", ".join(changes)
        session.log_operation(
            op_type="update",
            entity_type="item",
            entity_id=item_id,
            summary=summary,
            previous_state=current,
        )
        sessions.save()

        return summary + f" (id: {result.get('id', item_id)})."
