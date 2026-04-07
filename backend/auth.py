"""
Statement-tools authentication.

Two modes selected by environment variables:

Standalone mode (no YFW_SECRET_KEY):
  - If STATEMENT_TOOLS_API_KEY is set, validate it via X-API-Key header.
  - If neither is set, allow all requests (local dev).

Sidecar/plugin mode (YFW_SECRET_KEY is set):
  - Validate the JWT issued by the main YFW app.
  - tenant_id and user_id are extracted from the JWT payload.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from config import Settings, get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


@dataclass
class PluginUser:
    email: str
    id: Optional[int] = None
    tenant_id: Optional[str] = None
    is_public: bool = False
    visitor_id: Optional[str] = None
    visitor_tenant_id: Optional[str] = None


async def get_current_user(
    request: Request,
    api_key_header: Optional[str] = Depends(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> PluginUser:
    yfw_secret = os.getenv("YFW_SECRET_KEY", "")

    # ── Sidecar mode: validate JWT from the main YFW app ──────────────────
    if yfw_secret:
        if bearer:
            try:
                from jose import JWTError, jwt
                payload = jwt.decode(bearer.credentials, yfw_secret, algorithms=["HS256"])
                return PluginUser(
                    email=payload.get("sub", "unknown"),
                    id=payload.get("user_id"),
                    tenant_id=payload.get("tenant_id"),
                )
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token.",
                )
        
        # Check for Public Visitor headers (unauthenticated)
        visitor_id = request.headers.get("X-Public-Visitor-Id")
        visitor_tenant_id = request.headers.get("X-Public-Tenant-Id")
        if visitor_id and visitor_tenant_id:
            return PluginUser(
                email=f"public:{visitor_id}",
                is_public=True,
                visitor_id=visitor_id,
                visitor_tenant_id=visitor_tenant_id
            )

    # ── Standalone mode: API key or open dev access ────────────────────────
    local_key = os.getenv("STATEMENT_TOOLS_API_KEY", "")
    if not local_key:
        return PluginUser(email="admin@standalone")

    provided_key = api_key_header or (bearer.credentials if bearer else None)
    if provided_key != local_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return PluginUser(email="admin@standalone")
