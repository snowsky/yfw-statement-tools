"""
HTTP client for the YourFinanceWORKS external developer API.

Uses the /api/v1/external/ endpoints which are authenticated via X-API-Key.
These are read-only endpoints — merge is performed locally in statement-tools.

Endpoint base: GET /api/v1/external/statements/
                GET /api/v1/external/statements/{id}   (includes full transactions)
"""
from __future__ import annotations

import httpx

from shared.compat import STANDALONE

if STANDALONE:
    from standalone.config import get_settings

    def _base_url() -> str:
        return get_settings().yfw_api_url.rstrip("/")

    def _auth_headers() -> dict[str, str]:
        key = get_settings().yfw_api_key
        return {"X-API-Key": key} if key else {}
else:
    def _base_url() -> str:
        return "http://localhost:8000"

    def _auth_headers() -> dict[str, str]:
        # In plugin mode the caller's JWT is forwarded by the router.
        return {}

# External API base — API-key authenticated
_EXT = "/api/v1/external/statements"


class InvoiceAPIClient:
    """Async wrapper for YFW external statement endpoints."""

    def __init__(
        self,
        extra_headers: dict[str, str] | None = None,
        yfw_url: str | None = None,
        api_key: str | None = None,
    ):
        self._extra = extra_headers or {}
        self._yfw_url = yfw_url
        self._api_key = api_key

    def _base(self) -> str:
        return (self._yfw_url or _base_url()).rstrip("/")

    def _headers(self) -> dict[str, str]:
        base = _auth_headers()
        if self._api_key:
            base["X-API-Key"] = self._api_key
        return {**base, **self._extra}

    async def list_statements(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        search: str | None = None,
        label: str | None = None,
    ) -> dict:
        """
        Returns {statements: [...], total: int}.

        Note: the external API response uses 'account_name' (filename) and
        'statement_date'; status/labels/card_type are not exposed externally.
        """
        params: dict = {"skip": skip, "limit": limit}
        # External API doesn't support status/label filters — silently ignored
        if search:
            params["search"] = search

        async with httpx.AsyncClient(base_url=self._base(), timeout=30.0) as client:
            resp = await client.get(_EXT + "/", params=params, headers=self._headers())
            resp.raise_for_status()

        data = resp.json()
        # External API may return a plain list or {statements, total}
        if isinstance(data, list):
            return {"statements": data, "total": len(data)}
        return data

    async def get_statement(self, statement_id: int) -> dict:
        """Fetch a single statement including its full transactions list."""
        async with httpx.AsyncClient(base_url=self._base(), timeout=30.0) as client:
            resp = await client.get(
                f"{_EXT}/{statement_id}", headers=self._headers()
            )
            resp.raise_for_status()
        return resp.json()

    async def create_external_transaction(self, payload: dict) -> dict:
        """
        POST /api/v1/external-transactions/transactions

        Required keys: transaction_type ("income"|"expense"), amount (>0),
        currency, date (ISO string), description, source_system.
        """
        async with httpx.AsyncClient(base_url=self._base(), timeout=30.0) as client:
            resp = await client.post(
                "/api/v1/external-transactions/transactions",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
        return resp.json()
