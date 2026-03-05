"""Async HTTP client for the Homebox REST API."""

import httpx


class HomeboxClient:
    """Wraps Homebox REST API with async methods and auto-auth.

    Usage:
        client = HomeboxClient("http://homebox:7745", "user@example.com", "pass")
        await client.connect()
        locations = await client.list_locations()
        await client.close()
    """

    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize HTTP client and authenticate."""
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        await self._authenticate()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()

    async def _authenticate(self) -> None:
        """Login to Homebox and store Bearer token."""
        resp = await self._client.post(
            "/api/v1/users/login",
            json={"username": self.email, "password": self.password},
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request with error handling.

        Handles token refresh on 401, raises descriptive errors.
        """
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = await self._client.request(method, path, headers=headers, **kwargs)
        if resp.status_code == 401:
            await self._authenticate()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = await self._client.request(method, path, headers=headers, **kwargs)
        if not resp.is_success:
            raise RuntimeError(f"Homebox API error {resp.status_code}: {resp.text}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # --- Locations ---

    async def list_locations(self) -> list[dict]:
        """GET /api/v1/locations"""
        return await self._request("GET", "/api/v1/locations")

    async def create_location(self, data: dict) -> dict:
        """POST /api/v1/locations"""
        return await self._request("POST", "/api/v1/locations", json=data)

    async def get_location(self, location_id: str) -> dict:
        """GET /api/v1/locations/{id}"""
        return await self._request("GET", f"/api/v1/locations/{location_id}")

    async def delete_location(self, location_id: str) -> None:
        """DELETE /api/v1/locations/{id}"""
        await self._request("DELETE", f"/api/v1/locations/{location_id}")

    # --- Items ---

    async def list_items(self, query: str = "", location_id: str = "") -> list[dict]:
        """GET /api/v1/items with optional search and location filter."""
        params: dict = {"pageSize": 9999}
        if query:
            params["q"] = query
        if location_id:
            params["locations"] = location_id
        result = await self._request("GET", "/api/v1/items", params=params)
        return result.get("items", [])

    async def create_item(self, data: dict) -> dict:
        """POST /api/v1/items"""
        return await self._request("POST", "/api/v1/items", json=data)

    async def get_item(self, item_id: str) -> dict:
        """GET /api/v1/items/{id}"""
        return await self._request("GET", f"/api/v1/items/{item_id}")

    async def update_item(self, item_id: str, data: dict) -> dict:
        """PUT /api/v1/items/{id}"""
        return await self._request("PUT", f"/api/v1/items/{item_id}", json=data)

    async def delete_item(self, item_id: str) -> None:
        """DELETE /api/v1/items/{id}"""
        await self._request("DELETE", f"/api/v1/items/{item_id}")

    # --- Tags (called "labels" in spec, "tags" in API) ---

    async def list_tags(self) -> list[dict]:
        """GET /api/v1/tags"""
        return await self._request("GET", "/api/v1/tags")

    async def create_tag(self, data: dict) -> dict:
        """POST /api/v1/tags"""
        return await self._request("POST", "/api/v1/tags", json=data)
