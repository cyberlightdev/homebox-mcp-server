"""Sync Homebox API client, ported from homebox_tool.py."""

import requests
from typing import Optional


class HomeboxClient:
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token: Optional[str] = None

    def update_credentials(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token = None  # force re-auth on next request

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _authenticate(self):
        self._token = None
        r = requests.post(
            f"{self.base_url}/api/v1/users/login",
            headers={"Content-Type": "application/json"},
            json={"username": self.email, "password": self.password, "stayLoggedIn": True},
        )
        r.raise_for_status()
        token = r.json().get("token")
        if not token:
            raise Exception(f"Auth succeeded but no token in response: {r.text}")
        # Homebox includes "Bearer " prefix in the token value — strip it
        self._token = token.removeprefix("Bearer ").strip()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        if not self._token:
            self._authenticate()

        headers = {"Authorization": f"Bearer {self._token}"}
        if method.upper() in ("POST", "PUT", "PATCH"):
            headers["Content-Type"] = "application/json"

        r = requests.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)

        if r.status_code == 401:
            self._token = None
            self._authenticate()
            headers["Authorization"] = f"Bearer {self._token}"
            r = requests.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)

        r.raise_for_status()
        return r

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def normalize_name(self, name: str) -> str:
        return " ".join(name.strip().split()).title()

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------

    def list_locations(self) -> list[dict]:
        r = self._request("GET", "/api/v1/locations")
        results = r.json()
        return results if isinstance(results, list) else results.get("items", [])

    def find_location(self, name: str) -> Optional[dict]:
        for loc in self.list_locations():
            if loc["name"].lower() == name.lower():
                return loc
        return None

    def create_location(self, name: str) -> dict:
        r = self._request("POST", "/api/v1/locations", json={"name": name})
        return r.json()

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def find_item_at_location(self, name: str, location_id: str) -> Optional[dict]:
        r = self._request("GET", "/api/v1/items", params={"q": name, "locations": location_id})
        results = r.json()
        items = results if isinstance(results, list) else results.get("items", [])
        for item in items:
            if item["name"].lower() == name.lower():
                return item
        return None

    def find_item_global(self, name: str) -> list[dict]:
        r = self._request("GET", "/api/v1/items", params={"q": name, "pageSize": 9999})
        results = r.json()
        return results if isinstance(results, list) else results.get("items", [])

    def create_item(self, name: str, location_id: str, quantity: int) -> dict:
        r = self._request(
            "POST", "/api/v1/items",
            json={"name": name, "locationId": location_id, "quantity": quantity},
        )
        return r.json()

    def update_item_quantity(self, item: dict, new_quantity: int) -> dict:
        # Resolve locationId — GET responses nest location as an object;
        # PUT requires a flat locationId string.
        location_id = item.get("locationId") or (item.get("location") or {}).get("id", "")
        payload = {
            "id": item["id"],
            "name": item["name"],
            "quantity": new_quantity,
            "locationId": location_id,
            "description": item.get("description", ""),
            "archived": item.get("archived", False),
            "insured": item.get("insured", False),
            "notes": item.get("notes", ""),
            "serialNumber": item.get("serialNumber", ""),
            "modelNumber": item.get("modelNumber", ""),
            "manufacturer": item.get("manufacturer", ""),
            "lifetimeWarranty": item.get("lifetimeWarranty", False),
            "tagIds": [t["id"] for t in item.get("tags", [])],
        }
        r = self._request("PUT", f"/api/v1/items/{item['id']}", json=payload)
        return r.json()

    def delete_item(self, item_id: str):
        self._request("DELETE", f"/api/v1/items/{item_id}")
