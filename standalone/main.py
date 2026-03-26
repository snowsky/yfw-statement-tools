"""
Standalone FastAPI entry point for statement-tools.

Run with:
    uvicorn standalone.main:app --reload --port 8000

Or via Docker Compose:
    docker-compose up api
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.routers import statements_router
from standalone.config import get_settings
from standalone.database import create_tables

settings = get_settings()

app = FastAPI(
    title="Statement Tools — Standalone",
    description="Merge, download, and manage YFW bank statements.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PLUGIN_PREFIX = "/api/v1/statement-tools"
app.include_router(statements_router, prefix=PLUGIN_PREFIX, tags=["statement-tools"])


@app.on_event("startup")
async def startup():
    create_tables()


@app.get("/health")
def health():
    return {"status": "ok", "service": "statement-tools"}


class ConnectionCheckRequest(BaseModel):
    yfw_api_url: str
    yfw_api_key: str


@app.post("/api/v1/statement-tools/check-connection")
async def check_connection(body: ConnectionCheckRequest):
    """
    Server-side connectivity check — avoids CORS issues when the browser
    cannot reach the YFW instance directly.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{body.yfw_api_url.rstrip('/')}/api/v1/external/me",
                headers={"X-API-Key": body.yfw_api_key},
            )
        if resp.status_code == 401:
            return {"ok": False, "error": "Invalid API key."}
        if resp.status_code == 402:
            return {"ok": False, "error": "External API access not enabled on your YFW license."}
        if not resp.is_success:
            return {"ok": False, "error": f"YFW returned HTTP {resp.status_code}."}
        return {"ok": True}
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"Cannot reach {body.yfw_api_url}: {exc}"}
