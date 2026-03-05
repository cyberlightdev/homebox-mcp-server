"""Location management tools: create, search, set current."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context, FastMCP
from thefuzz import process as fuzz_process

from homebox_mcp.client import HomeboxClient
from homebox_mcp.session import SessionManager


def _fuzzy_match_location(query: str, locations: list[dict], score_cutoff: int = 60) -> list[dict]:
    """Return locations whose names fuzzy-match query above the score cutoff.

    Exact case-insensitive matches are returned immediately without fuzzy scoring.
    """
    if not locations:
        return []
    query_lower = query.lower()
    exact = [loc for loc in locations if loc["name"].lower() == query_lower]
    if exact:
        return exact
    choices = {loc["id"]: loc["name"] for loc in locations}
    matches = fuzz_process.extractBests(query, choices, score_cutoff=score_cutoff)
    matched_ids = {loc_id for _, _, loc_id in matches}
    return [loc for loc in locations if loc["id"] in matched_ids]


def register_tools(mcp: FastMCP) -> None:
    """Register location tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": False, "idempotentHint": True},
        description=(
            "Sets the working location for subsequent operations. "
            "Fuzzy-matches the name against existing locations. "
            "Returns matched location info, or a list of candidates if ambiguous."
        ),
    )
    async def homebox_set_location(name: str, ctx: Context) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_context["client"]
        sessions: SessionManager = ctx.request_context.lifespan_context["sessions"]
        session = sessions.get(ctx.client_id or "default")

        locations = await client.list_locations()
        matches = _fuzzy_match_location(name, locations, score_cutoff=60)

        if not matches:
            return f"No location found matching '{name}'. Use homebox_search_locations to browse available locations."

        if len(matches) == 1:
            loc = matches[0]
            session.set_location({"id": loc["id"], "name": loc["name"]})
            sessions.save()
            return f"Current location set to '{loc['name']}' (id: {loc['id']})."

        candidates = [{"id": m["id"], "name": m["name"]} for m in matches]
        return (
            f"Multiple locations match '{name}'. Please be more specific:\n"
            + json.dumps(candidates, indent=2)
        )

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False},
        description=(
            "Creates a new inventory location in Homebox. "
            "If parent_name is given, fuzzy-matches it against existing locations. "
            "If omitted, uses the current session location's parent or creates top-level. "
            "Sets the new location as the current working location."
        ),
    )
    async def homebox_create_location(
        name: str,
        ctx: Context,
        parent_name: str | None = None,
        description: str | None = None,
    ) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_context["client"]
        sessions: SessionManager = ctx.request_context.lifespan_context["sessions"]
        session = sessions.get(ctx.client_id or "default")

        parent_id: str | None = None
        parent_display: str = "(top-level)"

        if parent_name:
            locations = await client.list_locations()
            matches = _fuzzy_match_location(parent_name, locations, score_cutoff=60)
            if not matches:
                return (
                    f"No location found matching '{parent_name}'. "
                    "Use homebox_search_locations to find the correct parent."
                )
            if len(matches) > 1:
                candidates = [{"id": m["id"], "name": m["name"]} for m in matches]
                return (
                    f"Multiple locations match '{parent_name}'. Please be more specific:\n"
                    + json.dumps(candidates, indent=2)
                )
            parent_id = matches[0]["id"]
            parent_display = matches[0]["name"]
        elif session.current_location:
            parent_id = session.current_location["id"]
            parent_display = session.current_location["name"]

        payload: dict = {"name": name}
        if description:
            payload["description"] = description
        if parent_id:
            payload["parentId"] = parent_id

        result = await client.create_location(payload)
        loc_id = result["id"]
        session.set_location({"id": loc_id, "name": name})
        session.log_operation(
            op_type="create",
            entity_type="location",
            entity_id=loc_id,
            summary=f"Created location '{name}' under '{parent_display}'",
        )
        sessions.save()
        return f"Created location '{name}' under '{parent_display}' (id: {loc_id}). Now set as current location."

    @mcp.tool(
        annotations={"readOnlyHint": True},
        description=(
            "Search for locations by name. Returns matching locations with id, name, "
            "description, and item count."
        ),
    )
    async def homebox_search_locations(query: str, ctx: Context) -> str:
        client: HomeboxClient = ctx.request_context.lifespan_context["client"]

        locations = await client.list_locations()
        matches = _fuzzy_match_location(query, locations, score_cutoff=50)

        if not matches:
            return f"No locations found matching '{query}'."

        results = [
            {
                "id": loc["id"],
                "name": loc["name"],
                "description": loc.get("description", ""),
                "itemCount": loc.get("itemCount", 0),
            }
            for loc in matches
        ]
        return json.dumps(results, indent=2)
