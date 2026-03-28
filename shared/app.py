"""
Shared FastAPI app factory for statement-tools deployments.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.auth import get_current_user
from shared.config import get_settings
from shared.routers.statements import cleanup_expired_files, create_router

logger = logging.getLogger(__name__)


def create_app(
    *,
    api_prefix: str,
    require_auth: bool,
    include_connection_check: bool,
    title: str = "Statement Tools",
    service_name: str = "statement-tools",
) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
        logger.info("%s started (temp_dir=%s)", service_name, settings.temp_dir)

        task = asyncio.create_task(_cleanup_loop())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title=title,
        description="Upload bank statements, get parsed CSV via YFW.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    auth_dependency = get_current_user if require_auth else None
    app.include_router(
        create_router(api_prefix=api_prefix, auth_dependency=auth_dependency),
        prefix=api_prefix,
        tags=["statement-tools"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "service": service_name}

    if include_connection_check:
        _attach_connection_check(app, api_prefix)

    return app


async def _cleanup_loop():
    while True:
        await asyncio.sleep(300)
        try:
            removed = cleanup_expired_files()
            if removed:
                logger.info("Cleaned up %d expired download(s)", removed)
        except Exception as exc:
            logger.warning("Cleanup error: %s", exc)


def _attach_connection_check(app: FastAPI, api_prefix: str) -> None:
    class ConnectionCheckRequest(BaseModel):
        yfw_api_url: str
        yfw_api_key: str

    @app.post(f"{api_prefix}/check-connection")
    async def check_connection(body: ConnectionCheckRequest):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{body.yfw_api_url.rstrip('/')}/api/v1/external/statements/health"
                logger.info("Checking YFW health at: %s", url)
                resp = await client.get(url, headers={"X-API-Key": body.yfw_api_key})
                logger.info(
                    "YFW health check response: status=%d, body=%s",
                    resp.status_code,
                    resp.text[:100],
                )
            if resp.status_code == 401:
                return {"ok": False, "error": "Invalid API key."}
            if resp.status_code == 402:
                return {
                    "ok": False,
                    "error": "External API access not enabled on your YFW license.",
                }
            if not resp.is_success:
                return {"ok": False, "error": f"YFW returned HTTP {resp.status_code}."}
            return {"ok": True}
        except httpx.RequestError as exc:
            return {"ok": False, "error": f"Cannot reach {body.yfw_api_url}: {exc}"}
