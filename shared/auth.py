"""
Authentication helpers shared by standalone and plugin entry points.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)
_key_cache: dict[tuple[str, str], float] = {}
_CACHE_TTL = 300


@dataclass
class AuthenticatedUser:
    api_key: str
    yfw_url: str


async def get_current_user(
    request: Request,
    api_key_header: Optional[str] = Depends(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    key = api_key_header or (bearer.credentials if bearer else None)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required (X-API-Key header or Authorization: Bearer <key>).",
        )

    yfw_url = request.headers.get("X-YFW-URL") or settings.yfw_api_url
    cache_key = (key, yfw_url)
    cached_expiry = _key_cache.get(cache_key)
    if cached_expiry and time.time() < cached_expiry:
        return AuthenticatedUser(api_key=key, yfw_url=yfw_url)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            url = f"{yfw_url.rstrip('/')}/api/v1/external/statements/health"
            logger.info("Checking API key at YFW: %s", url)
            resp = await client.get(url, headers={"X-API-Key": key})
            logger.info("YFW auth check status: %d", resp.status_code)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Cannot reach YFW at {yfw_url}: {exc}",
            ) from exc

    if resp.status_code == 401:
        _key_cache.pop(cache_key, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    if resp.status_code == 402:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="External API access not enabled on your YFW license.",
        )
    if not resp.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"YFW returned {resp.status_code}.",
        )

    _key_cache[cache_key] = time.time() + _CACHE_TTL
    return AuthenticatedUser(api_key=key, yfw_url=yfw_url)
