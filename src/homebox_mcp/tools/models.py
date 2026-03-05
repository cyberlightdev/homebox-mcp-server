"""Pydantic models for MCP tool inputs and outputs."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


# --- Input Models ---

class SetLocationInput(BaseModel):
    """Input for homebox_set_location."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        ...,
        description="Location name to search for and set as current (e.g., 'Blue Bin #2', 'Storeroom')",
        min_length=1,
        max_length=200,
    )


class CreateLocationInput(BaseModel):
    """Input for homebox_create_location."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., description="Name for the new location", min_length=1, max_length=200)
    parent_name: Optional[str] = Field(
        default=None,
        description="Parent location name. If omitted, uses current location's parent or creates at top level.",
    )
    description: Optional[str] = Field(default=None, description="Optional description of the location")


class SearchLocationsInput(BaseModel):
    """Input for homebox_search_locations."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Search query for location names", min_length=1)


class AddItemInput(BaseModel):
    """Input for homebox_add_item."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., description="Item name", min_length=1, max_length=200)
    quantity: int = Field(default=1, description="Number of this item", ge=1)
    location_name: Optional[str] = Field(
        default=None,
        description="Location name to add item to. Defaults to current session location.",
    )
    notes: Optional[str] = Field(default=None, description="Optional notes about the item")
    labels: Optional[list[str]] = Field(
        default=None,
        description="Optional label names to apply (created if they don't exist)",
    )


class SearchItemsInput(BaseModel):
    """Input for homebox_search_items."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Search query for item names/descriptions", min_length=1)
    location_name: Optional[str] = Field(
        default=None,
        description="Optional location name to scope the search",
    )


class UpdateItemInput(BaseModel):
    """Input for homebox_update_item."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    item_id: str = Field(..., description="Item ID from search results")
    quantity: Optional[int] = Field(default=None, description="New quantity", ge=1)
    notes: Optional[str] = Field(default=None, description="Replace existing notes")
    location_name: Optional[str] = Field(default=None, description="Move item to this location")
    name: Optional[str] = Field(default=None, description="Rename the item")
