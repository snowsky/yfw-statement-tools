"""
Internal YFW client that calls the core processing service directly.

Used when statement-tools runs as a plugin inside the main YFW app,
bypassing the external HTTP API and API key requirement.
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class InternalYFWClient:
    """
    Drop-in replacement for ``YFWClient`` that calls the core processing
    service directly instead of making HTTP requests to the external API.
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

        ext = ".pdf" if "pdf" in content_type else ".csv"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=ext, prefix=f"plugin_stmt_{uuid.uuid4().hex[:8]}_"
        ) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            db = None
            if self._db_session_factory:
                db = self._db_session_factory()

            ai_config = None
            if db:
                try:
                    from core.models.models_per_tenant import AIConfig as AIConfigModel

                    ai_row = (
                        db.query(AIConfigModel)
                        .filter(AIConfigModel.is_active == True, AIConfigModel.tested == True)
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
                raise RuntimeError("AI processing service temporarily unavailable.")

            if db:
                db.close()

            return transactions or []
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def upload_batch(self, files: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        raise NotImplementedError("Batch processing is not yet supported in plugin mode.")

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        raise NotImplementedError("Batch job status is not yet supported in plugin mode.")

    async def health_check(self) -> dict[str, Any]:
        from core.services.statement_service import is_bank_llm_reachable

        available = is_bank_llm_reachable()
        return {
            "status": "healthy" if available else "degraded",
            "mode": "plugin",
            "ai_processing": "available" if available else "unavailable",
        }
