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

    async def upload_batch(
        self, files: list[tuple[str, bytes, str]], document_type: str = "statement"
    ) -> dict[str, Any]:
        """Call BatchProcessingService directly — no API key needed."""
        from commercial.batch_processing.service import BatchProcessingService
        from core.models.database import get_db as _get_db, get_tenant_context

        tenant_id = get_tenant_context()
        db = None
        try:
            db_gen = _get_db()
            db = next(db_gen)

            service = BatchProcessingService(db)

            file_infos = []
            for idx, (filename, content, content_type) in enumerate(files):
                file_infos.append({
                    "content": content,
                    "filename": filename,
                    "size": len(content),
                    "content_type": content_type,
                })

            batch_job = await service.create_batch_job(
                files=file_infos,
                tenant_id=tenant_id,
                user_id=1,
                api_client_id=None,
                export_destination_id=None,
                document_types=[document_type] if document_type else None,
                card_type="auto",
            )

            # Enqueue files for processing
            try:
                await service.enqueue_files_to_kafka(batch_job.job_id)
            except Exception as exc:
                logger.warning("Kafka enqueue failed, job will need manual retry: %s", exc)

            return {
                "job_id": batch_job.job_id,
                "status": batch_job.status,
                "total_files": batch_job.total_files,
            }
        except Exception as exc:
            logger.error("Internal batch upload failed: %s", exc)
            raise RuntimeError(f"Batch upload failed: {exc}") from exc
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Query BatchProcessingService directly for job status."""
        from commercial.batch_processing.service import BatchProcessingService
        from core.models.database import get_db as _get_db, get_tenant_context

        tenant_id = get_tenant_context()
        db = None
        try:
            db_gen = _get_db()
            db = next(db_gen)
            service = BatchProcessingService(db)
            job_status = service.get_job_status(job_id, tenant_id)
            if not job_status:
                raise RuntimeError(f"Job {job_id} not found")
            return job_status
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

    async def health_check(self) -> dict[str, Any]:
        from core.services.statement_service import is_bank_llm_reachable

        available = is_bank_llm_reachable()
        return {
            "status": "healthy" if available else "degraded",
            "mode": "plugin",
            "ai_processing": "available" if available else "unavailable",
        }
