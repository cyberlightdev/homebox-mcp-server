"""Tests for HomeboxClient."""

import httpx
import pytest
import respx

from homebox_mcp.client import HomeboxClient


BASE_URL = "http://homebox:7745"


@pytest.fixture
def client():
    return HomeboxClient(BASE_URL, "user@example.com", "secret")


@respx.mock
async def test_authenticate_stores_token(client):
    respx.post(f"{BASE_URL}/api/v1/users/login").mock(
        return_value=httpx.Response(200, json={"token": "abc123", "attachmentToken": "", "expiresAt": ""})
    )
    client._client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
    await client._authenticate()
    assert client._token == "abc123"


@respx.mock
async def test_list_locations(client):
    respx.post(f"{BASE_URL}/api/v1/users/login").mock(
        return_value=httpx.Response(200, json={"token": "tok", "attachmentToken": "", "expiresAt": ""})
    )
    respx.get(f"{BASE_URL}/api/v1/locations").mock(
        return_value=httpx.Response(200, json=[{"id": "loc1", "name": "Storeroom"}])
    )
    await client.connect()
    locations = await client.list_locations()
    assert len(locations) == 1
    assert locations[0]["name"] == "Storeroom"
    await client.close()


@respx.mock
async def test_list_items_extracts_items_array(client):
    respx.post(f"{BASE_URL}/api/v1/users/login").mock(
        return_value=httpx.Response(200, json={"token": "tok", "attachmentToken": "", "expiresAt": ""})
    )
    respx.get(f"{BASE_URL}/api/v1/items").mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"id": "i1", "name": "Hammer"}], "page": 1, "pageSize": 9999, "total": 1},
        )
    )
    await client.connect()
    items = await client.list_items(query="hammer")
    assert len(items) == 1
    assert items[0]["name"] == "Hammer"
    await client.close()


@respx.mock
async def test_request_retries_on_401(client):
    login_route = respx.post(f"{BASE_URL}/api/v1/users/login")
    login_route.side_effect = [
        httpx.Response(200, json={"token": "tok1", "attachmentToken": "", "expiresAt": ""}),
        httpx.Response(200, json={"token": "tok2", "attachmentToken": "", "expiresAt": ""}),
    ]
    locations_route = respx.get(f"{BASE_URL}/api/v1/locations")
    locations_route.side_effect = [
        httpx.Response(401, text="Unauthorized"),
        httpx.Response(200, json=[{"id": "loc1", "name": "Room"}]),
    ]

    await client.connect()
    locations = await client.list_locations()
    assert client._token == "tok2"
    assert locations[0]["name"] == "Room"
    await client.close()


@respx.mock
async def test_delete_returns_empty_dict(client):
    respx.post(f"{BASE_URL}/api/v1/users/login").mock(
        return_value=httpx.Response(200, json={"token": "tok", "attachmentToken": "", "expiresAt": ""})
    )
    respx.delete(f"{BASE_URL}/api/v1/items/item1").mock(
        return_value=httpx.Response(204)
    )
    await client.connect()
    result = await client.delete_item("item1")
    assert result is None
    await client.close()
