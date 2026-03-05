"""Shared test fixtures."""

from unittest.mock import AsyncMock

import pytest

from homebox_mcp.client import HomeboxClient
from homebox_mcp.session import Session, SessionManager


@pytest.fixture
def session():
    """Fresh session for testing."""
    return Session()


@pytest.fixture
def session_manager(tmp_path):
    """Session manager with temp file for testing."""
    return SessionManager(str(tmp_path / "sessions.json"))


@pytest.fixture
def mock_client():
    """AsyncMock HomeboxClient with sensible defaults."""
    client = AsyncMock(spec=HomeboxClient)
    client.list_locations.return_value = [
        {"id": "loc1", "name": "Storeroom", "description": "Main storage", "itemCount": 5},
        {"id": "loc2", "name": "Garage", "description": "Garage shelves", "itemCount": 2},
    ]
    client.list_items.return_value = [
        {
            "id": "item1",
            "name": "Red Ball",
            "quantity": 3,
            "description": "",
            "location": {"id": "loc1", "name": "Storeroom"},
            "tags": [],
        }
    ]
    client.list_tags.return_value = [
        {"id": "tag1", "name": "fragile"},
    ]
    return client
