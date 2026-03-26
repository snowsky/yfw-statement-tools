"""
HTTP client for the YourFinanceWORKS bank statement API.

Used by both plugin mode (internal HTTP) and standalone mode (external API key).

In plugin mode:   base_url is the internal YFW address (e.g. http://localhost:8000)
In standalone:    base_url comes from settings.yfw_api_url

Authentication:
  - Standalone:  X-API-Key header from settings.yfw_api_key
  - Plugin mode: passes the caller's auth token through (resolved in the router)
"""
from __future__ import annotations

import httpx

from shared.compat import STANDALONE

if STANDALONE:
    from standalone.config import get_settings

    def _base_url() -> str:
        return get_settings().yfw_api_url

    def _auth_headers() -> dict[str, str]:
        key = get_settings().yfw_api_key
        return {"X-API-Key": key} if key else {}
else:
    def _base_url() -> str:
        return "http://localhost:8000"

    def _auth_headers() -> dict[str, str]:
        # In plugin mode the caller's JWT is forwarded by the router; no key needed here.
        return {}


class InvoiceAPIClient:
    """Thin async wrapper around the YFW statement API endpoints."""

    BASE = "/api/v1/statements"

    def __init__(self, extra_headers: dict[str, str] | None = None):
        self._extra = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        return {**_auth_headers(), **self._extra}

    async def list_statements(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        search: str | None = None,
        label: str | None = None,
    ) -> dict:
        params: dict = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if label:
            params["label"] = label

        async with httpx.AsyncClient(base_url=_base_url(), timeout=30.0) as client:
            resp = await client.get(self.BASE, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def merge(self, ids: list[int]) -> dict:
        """Call YFW's merge endpoint. Returns {success, message, id}."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=60.0) as client:
            resp = await client.post(
                f"{self.BASE}/merge",
                json={"ids": ids},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def download_file(self, statement_id: int) -> tuple[bytes, str, str]:
        """
        Download the raw statement file.
        Returns (content_bytes, filename, content_type).
        """
        async with httpx.AsyncClient(base_url=_base_url(), timeout=60.0) as client:
            resp = await client.get(
                f"{self.BASE}/{statement_id}/file",
                headers=self._headers(),
                params={"inline": "false"},
                follow_redirects=True,
            )
            resp.raise_for_status()

            cd = resp.headers.get("content-disposition", "")
            filename = "statement.csv"
            if 'filename="' in cd:
                filename = cd.split('filename="')[1].rstrip('"')
            content_type = resp.headers.get("content-type", "application/octet-stream")
            return resp.content, filename, content_type
