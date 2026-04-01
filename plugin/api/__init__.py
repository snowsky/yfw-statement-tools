"""
Plugin entry points for YourFinanceWORKS deployment.

When running as a plugin inside the main YFW app, statement processing
is handled directly via the internal service — no external API key needed.
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from typing import Any

logger = logging.getLogger(__name__)

PLUGIN_PREFIX = "/api/v1/statement-tools"


class InternalYFWClient:
    """
    Drop-in replacement for ``YFWClient`` that calls the core processing
    service directly instead of making HTTP requests to the external API.

    Used automatically when the plugin runs inside the main YFW app.
    """

    def __init__(self, db_session_factory=None):
        self._db_session_factory = db_session_factory

    async def process_statement(
        self,
        file_content: bytes,
        filename: str,
        content_type: str = "application/pdf",
    ) -> list[dict[str, Any]]:
        from core.services.statement_service import (
            process_bank_pdf_with_llm,
            is_bank_llm_reachable,
            BankLLMUnavailableError,
        )

        if not is_bank_llm_reachable():
            raise RuntimeError(
                "AI processing service is not available. "
                "Please configure it in Settings > AI Configuration."
            )

        # Write to a temp file for the processing function
        ext = ".pdf" if "pdf" in content_type else ".csv"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=ext, prefix=f"plugin_stmt_{uuid.uuid4().hex[:8]}_"
        ) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Obtain a tenant database session for AI config lookup
            db = None
            if self._db_session_factory:
                db = self._db_session_factory()

            # Load AI config from the tenant database (if available)
            ai_config = None
            if db:
                try:
                    from core.models.models_per_tenant import AIConfig as AIConfigModel

                    ai_row = (
                        db.query(AIConfigModel)
                        .filter(
                            AIConfigModel.is_active == True,
                            AIConfigModel.tested == True,
                        )
                        .order_by(AIConfigModel.is_default.desc())
                        .first()
                    )
                    if ai_row:
                        ai_config = {
                            "provider_name": ai_row.provider_name,
                            "model_name": ai_row.model_name,
                            "api_key": ai_row.api_key,
                            "provider_url": ai_row.provider_url,
                        }
                except Exception as exc:
                    logger.warning("Could not load AI config: %s", exc)

            try:
                transactions = process_bank_pdf_with_llm(
                    tmp_path, ai_config, db, card_type="auto"
                )
            except BankLLMUnavailableError:
                raise RuntimeError(
                    "AI processing service temporarily unavailable."
                )

            if db:
                db.close()

            return transactions or []
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def upload_batch(self, files: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        raise NotImplementedError(
            "Batch processing is not yet supported in plugin mode."
        )

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        raise NotImplementedError(
            "Batch job status is not yet supported in plugin mode."
        )

    async def health_check(self) -> dict[str, Any]:
        from core.services.statement_service import is_bank_llm_reachable

        available = is_bank_llm_reachable()
        return {
            "status": "healthy" if available else "degraded",
            "mode": "plugin",
            "ai_processing": "available" if available else "unavailable",
        }


def _make_internal_client_factory():
    """Return a factory that creates InternalYFWClient using the tenant DB."""

    def factory(request):
        db_factory = None
        try:
            from core.models.database import get_db

            # get_db is a generator dependency; for direct use, call the
            # tenant session factory instead.
            from core.models.database import get_tenant_context
            from core.services.tenant_database_manager import tenant_db_manager

            tenant_id = get_tenant_context()
            if tenant_id:
                db_factory = tenant_db_manager.get_tenant_session(tenant_id)
        except Exception:
            pass
        return InternalYFWClient(db_session_factory=db_factory)

    return factory


def register_plugin(app, mcp_registry=None, feature_gate=None):
    """Called by the YourFinanceWORKS plugin loader at startup."""
    from shared.routers.statements import create_router

    try:
        from core.routers.auth import get_current_user

        auth_dep = get_current_user
    except ImportError:
        auth_dep = None

    app.include_router(
        create_router(
            api_prefix=PLUGIN_PREFIX,
            auth_dependency=auth_dep,
            client_factory=_make_internal_client_factory(),
        ),
        prefix=PLUGIN_PREFIX,
        tags=["statement-tools"],
    )
    return {
        "name": "statement-tools",
        "version": "1.0.0",
        "routes": [
            f"{PLUGIN_PREFIX}/statements/upload",
            f"{PLUGIN_PREFIX}/statements/download/{{token}}",
            f"{PLUGIN_PREFIX}/batch/upload",
            f"{PLUGIN_PREFIX}/batch/jobs/{{job_id}}",
        ],
    }
