"""
Statement-tools FastAPI entry point.

Standalone mode:  docker-compose up
Sidecar mode:     docker-compose -f docker-compose.yml -f ../yfw-statement-tools/docker-compose.plugin.yml up

Run locally:
    uvicorn main:app --reload --port 8000
"""
import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers.statements import cleanup_expired_files, router as statements_router

logger = logging.getLogger(__name__)

settings = get_settings()

PLUGIN_PREFIX = "/api/v1/statement-tools"
_PLUGIN_MANIFEST = json.loads((Path(__file__).parent / "plugin.json").read_text())

app = FastAPI(
    title="Statement Tools",
    description="Upload bank statements, parse via YFW AI, get merged CSV.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(statements_router, prefix=PLUGIN_PREFIX)


async def _cleanup_loop() -> None:
    """Remove expired CSV files every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        try:
            removed = cleanup_expired_files(settings)
            if removed:
                logger.info("Cleanup: removed %d expired CSV file(s)", removed)
        except Exception as exc:
            logger.warning("Cleanup error: %s", exc)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_cleanup_loop())


@app.get("/health")
def health():
    return {"status": "ok", "service": "yfw-statement-tools"}


@app.get("/plugin.json")
def plugin_manifest():
    """Standard sidecar discovery endpoint — consumed by the main app's plugin loader."""
    return _PLUGIN_MANIFEST
