"""
Standalone FastAPI entry point for statement-tools.

Run with:
    uvicorn standalone.main:app --reload --port 8000

Or via Docker Compose:
    docker-compose up api
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.routers import statements_router
from standalone.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup: ensure temp dir exists
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Statement-tools started (temp_dir=%s)", settings.temp_dir)

    # Start background cleanup task
    task = asyncio.create_task(_cleanup_loop())

    yield

    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _cleanup_loop():
    """Periodically remove expired download files."""
    from shared.routers.statements import cleanup_expired_files

    while True:
        await asyncio.sleep(300)  # every 5 minutes
        try:
            removed = cleanup_expired_files()
            if removed:
                logger.info("Cleaned up %d expired download(s)", removed)
        except Exception as exc:
            logger.warning("Cleanup error: %s", exc)


app = FastAPI(
    title="Statement Tools",
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

PLUGIN_PREFIX = "/api/v1/external/statement-tools"
app.include_router(statements_router, prefix=PLUGIN_PREFIX, tags=["statement-tools"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "statement-tools"}


class ConnectionCheckRequest(BaseModel):
    yfw_api_url: str
    yfw_api_key: str


@app.post(f"{PLUGIN_PREFIX}/check-connection")
async def check_connection(body: ConnectionCheckRequest):
    """
    Server-side connectivity check — avoids CORS issues when the browser
    cannot reach the YFW instance directly.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{body.yfw_api_url.rstrip('/')}/api/v1/external/statements/health"
            logger.info("Checking YFW health at: %s", url)
            resp = await client.get(
                url,
                headers={"X-API-Key": body.yfw_api_key},
            )
            logger.info("YFW health check response: status=%d, body=%s", resp.status_code, resp.text[:100])
        if resp.status_code == 401:
            return {"ok": False, "error": "Invalid API key."}
        if resp.status_code == 402:
            return {"ok": False, "error": "External API access not enabled on your YFW license."}
        if not resp.is_success:
            return {"ok": False, "error": f"YFW returned HTTP {resp.status_code}."}
        return {"ok": True}
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"Cannot reach {body.yfw_api_url}: {exc}"}
