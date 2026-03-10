"""Tool function implementations and OpenAI JSON schemas for the inventory assistant."""

from collections import deque
from homebox_client import HomeboxClient


# ------------------------------------------------------------------
# Tool functions — all take (session, client, **kwargs)
# Session dict shape:
#   {
#     "current_location_id": str | None,
#     "current_location_name": str | None,
#     "undo_stack": deque(maxlen=5),
#     "message_history": list,
#   }
# ------------------------------------------------------------------

def set_location(session: dict, client: HomeboxClient, name: str, **_) -> str:
    normalized = client.normalize_name(name)
    existing = client.find_location(normalized)

    prev_id = session["current_location_id"]
    prev_name = session["current_location_name"]

    if existing:
        session["current_location_id"] = existing["id"]
        session["current_location_name"] = existing["name"]
        session["undo_stack"].append({
            "action": "restore_location",
            "location_id": prev_id,
            "location_name": prev_name,
            "description": f"Switch back to '{prev_name}'" if prev_name else "Clear location",
        })
        return f"Switched to existing location: '{existing['name']}'."
    else:
        created = client.create_location(normalized)
        session["current_location_id"] = created["id"]
        session["current_location_name"] = created["name"]
        session["undo_stack"].append({
            "action": "restore_location",
            "location_id": prev_id,
            "location_name": prev_name,
            "description": f"Switch back to '{prev_name}'" if prev_name else "Clear location",
        })
        return f"Created new location and switched to it: '{created['name']}'."


def get_current_location(session: dict, client: HomeboxClient, **_) -> str:
    if session["current_location_id"]:
        return f"Current location: '{session['current_location_name']}'."
    return "No location set. Use set_location first."


def add_item(session: dict, client: HomeboxClient, name: str, quantity: int = 1, **_) -> str:
    if not session["current_location_id"]:
        return "No location set. Please call set_location first."

    normalized = client.normalize_name(name)
    existing = client.find_item_at_location(normalized, session["current_location_id"])

    if existing:
        old_qty = existing.get("quantity", 1)
        new_qty = old_qty + quantity
        client.update_item_quantity(existing, new_qty)
        session["undo_stack"].append({
            "action": "set_quantity",
            "item_id": existing["id"],
            "item": existing,
            "item_name": normalized,
            "location_name": session["current_location_name"],
            "quantity": old_qty,
            "description": f"Revert '{normalized}' quantity to {old_qty}",
        })
        return (
            f"Updated '{normalized}' at '{session['current_location_name']}': "
            f"{old_qty} + {quantity} = {new_qty}."
        )
    else:
        created = client.create_item(normalized, session["current_location_id"], quantity)
        session["undo_stack"].append({
            "action": "delete_item",
            "item_id": created["id"],
            "item_name": normalized,
            "location_name": session["current_location_name"],
            "description": f"Delete newly created '{normalized}'",
        })
        return (
            f"Created '{normalized}' at '{session['current_location_name']}' "
            f"with quantity {quantity}."
        )


def update_item_quantity(session: dict, client: HomeboxClient, name: str, quantity: int, **_) -> str:
    if not session["current_location_id"]:
        return "No location set. Please call set_location first."

    normalized = client.normalize_name(name)
    existing = client.find_item_at_location(normalized, session["current_location_id"])

    if not existing:
        return (
            f"No item named '{normalized}' found at '{session['current_location_name']}'. "
            f"Use add_item to create it."
        )

    old_qty = existing.get("quantity", 1)

    if quantity == 0:
        client.delete_item(existing["id"])
        session["undo_stack"].append({
            "action": "recreate_item",
            "name": normalized,
            "location_id": session["current_location_id"],
            "location_name": session["current_location_name"],
            "quantity": old_qty,
            "description": f"Recreate '{normalized}' with quantity {old_qty}",
        })
        return f"Deleted '{normalized}' from '{session['current_location_name']}' (quantity set to 0)."

    client.update_item_quantity(existing, quantity)
    session["undo_stack"].append({
        "action": "set_quantity",
        "item_id": existing["id"],
        "item": existing,
        "item_name": normalized,
        "location_name": session["current_location_name"],
        "quantity": old_qty,
        "description": f"Revert '{normalized}' quantity to {old_qty}",
    })
    return (
        f"Updated '{normalized}' at '{session['current_location_name']}': "
        f"{old_qty} → {quantity}."
    )


def remove_item(session: dict, client: HomeboxClient, name: str, **_) -> str:
    if not session["current_location_id"]:
        return "No location set. Please call set_location first."

    normalized = client.normalize_name(name)
    existing = client.find_item_at_location(normalized, session["current_location_id"])

    if not existing:
        return f"No item named '{normalized}' found at '{session['current_location_name']}'."

    client.delete_item(existing["id"])
    session["undo_stack"].append({
        "action": "recreate_item",
        "name": normalized,
        "location_id": session["current_location_id"],
        "location_name": session["current_location_name"],
        "quantity": existing.get("quantity", 1),
        "description": f"Recreate '{normalized}' with quantity {existing.get('quantity', 1)}",
    })
    return f"Deleted '{normalized}' from '{session['current_location_name']}'."


def undo(session: dict, client: HomeboxClient, **_) -> str:
    if not session["undo_stack"]:
        return "Nothing left to undo."

    entry = session["undo_stack"].pop()
    action = entry["action"]
    description = entry["description"]

    try:
        if action == "delete_item":
            client.delete_item(entry["item_id"])
            result = f"Deleted '{entry['item_name']}' from '{entry['location_name']}'."

        elif action == "set_quantity":
            client.update_item_quantity(entry["item"], entry["quantity"])
            result = (
                f"'{entry['item_name']}' at '{entry['location_name']}' "
                f"is now {entry['quantity']}."
            )

        elif action == "recreate_item":
            client.create_item(entry["name"], entry["location_id"], entry["quantity"])
            result = (
                f"Restored '{entry['name']}' at '{entry['location_name']}' "
                f"with quantity {entry['quantity']}."
            )

        elif action == "restore_location":
            session["current_location_id"] = entry["location_id"]
            session["current_location_name"] = entry["location_name"]
            if entry["location_name"]:
                result = f"Location restored to '{entry['location_name']}'."
            else:
                result = "Location cleared — no active location set."

        elif action == "move_item_reverse":
            # Recreate at source
            client.create_item(entry["item_name"], entry["source_location_id"], entry["quantity"])
            # Remove from target — find and delete/decrement
            target_item = client.find_item_at_location(entry["item_name"], entry["target_location_id"])
            if target_item:
                target_qty = target_item.get("quantity", 1)
                if target_qty <= entry["quantity"]:
                    client.delete_item(target_item["id"])
                else:
                    client.update_item_quantity(target_item, target_qty - entry["quantity"])
            result = (
                f"Moved '{entry['item_name']}' back to '{entry['source_location_name']}' "
                f"from '{entry['target_location_name']}'."
            )

        else:
            return f"Unknown undo action: {action}"

    except Exception as e:
        return f"Undo failed ({description}): {e}"

    remaining = len(session["undo_stack"])
    suffix = f"{remaining} undo step{'s' if remaining != 1 else ''} remaining." if remaining else "No more undo steps."
    return f"{result} {suffix}"


def find_item(session: dict, client: HomeboxClient, name: str, **_) -> str:
    normalized = client.normalize_name(name)
    matches = client.find_item_global(normalized)

    if not matches:
        return f"No items found matching '{normalized}'."

    lines = []
    for item in matches:
        loc_name = (item.get("location") or {}).get("name", "unknown location")
        qty = item.get("quantity", 1)
        lines.append(f"- '{item['name']}' at '{loc_name}', quantity {qty}")

    return f"Found {len(matches)} match(es) for '{normalized}':\n" + "\n".join(lines)


def move_item(session: dict, client: HomeboxClient, name: str, to_location: str, **_) -> str:
    if not session["current_location_id"]:
        return "No location set. Please call set_location first."

    normalized_name = client.normalize_name(name)
    normalized_dest = client.normalize_name(to_location)

    source_item = client.find_item_at_location(normalized_name, session["current_location_id"])
    if not source_item:
        return f"No item named '{normalized_name}' found at '{session['current_location_name']}'."

    qty = source_item.get("quantity", 1)

    # Find or create target location
    target_loc = client.find_location(normalized_dest)
    if not target_loc:
        target_loc = client.create_location(normalized_dest)

    # Add to target (increment if exists, create if not)
    target_item = client.find_item_at_location(normalized_name, target_loc["id"])
    if target_item:
        client.update_item_quantity(target_item, target_item.get("quantity", 1) + qty)
    else:
        client.create_item(normalized_name, target_loc["id"], qty)

    # Remove from source
    client.delete_item(source_item["id"])

    session["undo_stack"].append({
        "action": "move_item_reverse",
        "item_name": normalized_name,
        "quantity": qty,
        "source_location_id": session["current_location_id"],
        "source_location_name": session["current_location_name"],
        "target_location_id": target_loc["id"],
        "target_location_name": target_loc["name"],
        "description": f"Move '{normalized_name}' back to '{session['current_location_name']}'",
    })

    return (
        f"Moved {qty}x '{normalized_name}' from '{session['current_location_name']}' "
        f"to '{target_loc['name']}'."
    )


def list_locations(session: dict, client: HomeboxClient, **_) -> str:
    locs = client.list_locations()
    if not locs:
        return "No locations found."

    locs_sorted = sorted(locs, key=lambda l: l["name"].lower())
    names = [l["name"] for l in locs_sorted]

    # Detect near-duplicates (same name case-insensitively)
    seen_lower: dict[str, str] = {}
    warnings = []
    for name in names:
        key = name.lower()
        if key in seen_lower:
            warnings.append(f"  WARNING: '{name}' and '{seen_lower[key]}' look like duplicates")
        else:
            seen_lower[key] = name

    lines = [f"- {n}" for n in names]
    result = f"{len(locs)} location(s):\n" + "\n".join(lines)
    if warnings:
        result += "\n\nPossible duplicates:\n" + "\n".join(warnings)
    return result


# ------------------------------------------------------------------
# OpenAI tool definitions
# ------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "set_location",
            "description": (
                "Set the current working location for this session. Creates the location "
                "if it doesn't exist. Call this at the start of each session or when moving "
                "to a new area. All add_item calls will use this location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable location name, e.g. 'Garage Shelf 3' or 'Attic Bin 7'",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_location",
            "description": "Returns the currently active location for this session.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": (
                "Add an item to the current location. If the item already exists there, "
                "its quantity is increased. If not, a new item is created. "
                "Only call when the user explicitly states they physically found an item."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Item name, e.g. 'XLR Cable', 'Arduino Uno', 'Zip Ties (bag)'",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of units found. Defaults to 1.",
                        "default": 1,
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_item_quantity",
            "description": (
                "Explicitly set the quantity of an existing item at the current location "
                "to an absolute value. Use for corrections, not additions. "
                "Setting quantity to 0 deletes the item."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Exact item name as previously stored"},
                    "quantity": {"type": "integer", "description": "The new absolute quantity to set"},
                },
                "required": ["name", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item",
            "description": (
                "Completely remove an item from the current location. "
                "Use when the user wants to delete an entry entirely, not just reduce quantity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the item to delete"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "undo",
            "description": (
                "Undo the last inventory action. Can be called up to 5 times in a row. "
                "Use when the user says 'undo', 'that was wrong', 'go back', or 'never mind'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_item",
            "description": (
                "Search for an item by name across ALL locations. Use for any question about "
                "whether something exists or how many there are. "
                "NEVER use add_item to answer a question — use this first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Item name to search for"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_item",
            "description": (
                "Move an item from the current location to another location. "
                "The source is always the current location. "
                "Creates the destination location if it doesn't exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the item to move"},
                    "to_location": {"type": "string", "description": "Name of the destination location"},
                },
                "required": ["name", "to_location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_locations",
            "description": (
                "List all locations in the inventory, sorted alphabetically. "
                "Flags suspected duplicate location names. "
                "Use when the user asks what locations exist."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


TOOL_DISPATCH = {
    "set_location": set_location,
    "get_current_location": get_current_location,
    "add_item": add_item,
    "update_item_quantity": update_item_quantity,
    "remove_item": remove_item,
    "undo": undo,
    "find_item": find_item,
    "move_item": move_item,
    "list_locations": list_locations,
}
