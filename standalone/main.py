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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
