"""
Statement-tools router — upload portal.

Endpoints:
  POST /statements/upload            → forward files to YFW, return merged CSV download link
  GET  /statements/download/{token}  → serve a previously generated CSV (public, no auth)
  POST /batch/upload                 → async batch upload, returns job ID
  GET  /batch/jobs/{job_id}          → poll batch job status
  GET  /batch/jobs/{job_id}/csv      → download a completed job's transactions as CSV
  POST /batch/merge-csv              → merge multiple jobs into a single CSV download
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from auth import PluginUser, get_current_user
from config import Settings, get_settings
from schemas import BatchJobStatus, BatchUploadResponse, MergeRequest, UploadResponse
from services import get_yfw_client

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {"csv", "pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024        # 20 MB for authenticated users
PUBLIC_MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB for public visitors


# ── Temp file helpers ─────────────────────────────────────────────────────────

def _temp_dir(settings: Settings) -> Path:
    d = Path(settings.temp_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_expired(filepath: Path, expiry_minutes: int) -> bool:
    if not filepath.exists():
        return True
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime > timedelta(minutes=expiry_minutes)


def cleanup_expired_files(settings: Settings) -> int:
    """Remove expired CSV files from the temp directory. Returns count removed."""
    removed = 0
    for f in _temp_dir(settings).glob("*.csv"):
        if _is_expired(f, settings.download_expiry_minutes):
            f.unlink(missing_ok=True)
            removed += 1
    return removed


def _validate_file(upload: UploadFile) -> str:
    name = upload.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {name}. Only CSV and PDF are accepted.",
        )
    return ext


def _build_csv(all_transactions: list[dict]) -> bytes:
    output = io.StringIO()
    fieldnames = [
        "date",
        "description",
        "amount",
        "transaction_type",
        "category",
        "balance",
        "source_file",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_transactions)
    return output.getvalue().encode("utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/statements/upload", response_model=UploadResponse)
async def upload_statements(
    files: list[UploadFile] = File(...),
    user: PluginUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """
    Upload one or more bank statement files (CSV/PDF).

    Each file is forwarded to YFW's AI statement processor.
    All extracted transactions are merged into a single CSV.
    Returns a download link valid for the configured retention period (default: 1 hour).
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No files provided.",
        )

    for upload in files:
        _validate_file(upload)

    limit = PUBLIC_MAX_FILE_SIZE if user.is_public else MAX_FILE_SIZE
    client = get_yfw_client(
        settings.yfw_api_url,
        settings.yfw_api_key,
        secret_key=settings.yfw_secret_key,
        user_email=None if user.is_public else user.email,
    )
    all_transactions: list[dict] = []
    errors: list[str] = []

    visitor_id = user.visitor_id if user.is_public else None
    tenant_id = user.visitor_tenant_id if user.is_public else (str(user.tenant_id) if user.tenant_id else None)

    for upload in files:
        name = upload.filename or "unknown"
        content = await upload.read()
        if len(content) > limit:
            errors.append(f"{name}: file exceeds {'1 MB' if user.is_public else '20 MB'} limit.")
            continue

        try:
            transactions = await client.process_statement(
                content,
                name,
                upload.content_type or "application/octet-stream",
                visitor_id=visitor_id,
                tenant_id=tenant_id,
            )
            for transaction in transactions:
                transaction["source_file"] = name
            all_transactions.extend(transactions)
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if not all_transactions:
        detail = "No transactions could be extracted."
        if errors:
            detail += " " + "; ".join(errors)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )

    all_transactions.sort(key=lambda record: str(record.get("date") or ""))
    csv_bytes = _build_csv(all_transactions)

    token = uuid.uuid4().hex
    filepath = _temp_dir(settings) / f"{token}.csv"
    filepath.write_bytes(csv_bytes)

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.download_expiry_minutes,
    )
    return UploadResponse(
        success=True,
        message=(
            f"Processed {len(files)} file(s) — "
            f"{len(all_transactions)} transactions extracted."
        ),
        transaction_count=len(all_transactions),
        file_count=len(files),
        download_url=f"/api/v1/statement-tools/statements/download/{token}",
        expires_at=expires_at,
        errors=errors,
    )


@router.get("/statements/download/{token}")
async def download_csv(
    token: str,
    settings: Settings = Depends(get_settings),
):
    """
    Download a previously generated merged CSV.

    This endpoint is intentionally public — no authentication required.
    The token acts as the access credential; share the URL to share the file.
    Links expire after the configured retention period (default: 1 hour).
    """
    try:
        uuid.UUID(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid download token.",
        ) from exc

    filepath = _temp_dir(settings) / f"{token}.csv"
    if not filepath.exists() or _is_expired(filepath, settings.download_expiry_minutes):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Download link has expired. Please upload again.",
        )

    download_name = (
        f"statements-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    )
    return FileResponse(
        path=str(filepath),
        media_type="text/csv",
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@router.get("/batch/jobs")
async def list_batch_jobs(
    limit: int = 50,
    user: PluginUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """
    Return the authenticated user's batch job history from the YFW server.

    Public visitors have no server-side identity, so an empty list is returned —
    their history is managed client-side via localStorage.
    """
    if user.is_public:
        return {"jobs": [], "total": 0}

    client = get_yfw_client(
        settings.yfw_api_url,
        settings.yfw_api_key,
        secret_key=settings.yfw_secret_key,
        user_email=user.email,
    )
    try:
        return await client.list_jobs(limit=min(limit, 100))
    except Exception as exc:
        logger.error("Failed to list batch jobs: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post("/batch/upload", response_model=BatchUploadResponse)
async def upload_batch(
    files: list[UploadFile] = File(...),
    user: PluginUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """
    Upload one or more files for asynchronous batch processing.
    Returns a YFW job ID that can be polled for progress.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No files provided.",
        )

    for upload in files:
        _validate_file(upload)

    limit = PUBLIC_MAX_FILE_SIZE if user.is_public else MAX_FILE_SIZE
    client = get_yfw_client(
        settings.yfw_api_url,
        settings.yfw_api_key,
        secret_key=settings.yfw_secret_key,
        user_email=None if user.is_public else user.email,
    )
    file_tuples: list[tuple[str, bytes, str]] = []

    visitor_id = user.visitor_id if user.is_public else None
    visitor_tenant = user.visitor_tenant_id if user.is_public else (str(user.tenant_id) if user.tenant_id else None)

    for upload in files:
        content = await upload.read()
        if len(content) > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {upload.filename} exceeds {'1 MB' if user.is_public else '20 MB'} limit.",
            )
        file_tuples.append((
            upload.filename or "unknown",
            content,
            upload.content_type or "application/octet-stream",
        ))

    try:
        yfw_resp = await client.upload_batch(
            file_tuples, 
            visitor_id=visitor_id, 
            tenant_id=visitor_tenant
        )
        return BatchUploadResponse(
            success=True,
            job_id=yfw_resp.get("job_id", ""),
            status=yfw_resp.get("status", "pending"),
            message="Batch job created successfully.",
        )
    except Exception as exc:
        logger.error("Batch upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get("/batch/jobs/{job_id}", response_model=BatchJobStatus)
async def get_batch_job_status(
    job_id: str,
    user: PluginUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Get the status and results of a batch processing job."""
    client = get_yfw_client(
        settings.yfw_api_url,
        settings.yfw_api_key,
        secret_key=settings.yfw_secret_key,
        user_email=None if user.is_public else user.email,
    )
    try:
        yfw_resp = await client.get_job_status(job_id)
        progress = yfw_resp.get("progress", {})
        return BatchJobStatus(
            job_id=yfw_resp.get("job_id", ""),
            status=yfw_resp.get("status", "unknown"),
            processed_files=progress.get("processed", 0),
            total_files=progress.get("total", 0),
            successful_files=progress.get("successful", 0),
            failed_files=progress.get("failed", 0),
            progress_percentage=progress.get("percentage", 0.0),
            files=yfw_resp.get("files", []),
            completed_at=yfw_resp.get("timestamps", {}).get("completed_at"),
        )
    except Exception as exc:
        logger.error("Failed to get job status for %s: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


def _extract_job_transactions(yfw_resp: dict) -> list[dict]:
    """Pull all transactions out of the completed files in a job response."""
    all_transactions: list[dict] = []
    for file in yfw_resp.get("files", []):
        if file.get("status") != "completed":
            continue
        extracted = file.get("extracted_data") or {}
        if isinstance(extracted, list):
            transactions = extracted
        else:
            transactions = extracted.get("transactions", [])
        if not isinstance(transactions, list):
            continue
        for t in transactions:
            t.setdefault("source_file", file.get("filename", ""))
        all_transactions.extend(transactions)
    return all_transactions


@router.get("/batch/jobs/{job_id}/csv")
async def download_job_csv(
    job_id: str,
    user: PluginUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """
    Download the extracted transactions for a completed batch job as a CSV file.
    Jobs that are still in progress return 409.
    """
    client = get_yfw_client(
        settings.yfw_api_url,
        settings.yfw_api_key,
        secret_key=settings.yfw_secret_key,
        user_email=None if user.is_public else user.email,
    )
    try:
        yfw_resp = await client.get_job_status(job_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    job_status = yfw_resp.get("status", "unknown")
    if job_status in ("pending", "processing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is still {job_status}. Wait for it to complete before downloading.",
        )

    transactions = _extract_job_transactions(yfw_resp)
    if not transactions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No transactions found in this job.",
        )

    transactions.sort(key=lambda r: str(r.get("date") or ""))
    csv_bytes = _build_csv(transactions)
    short_id = job_id[:8]
    filename = f"statements-job-{short_id}.csv"
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/batch/merge-csv")
async def merge_jobs_csv(
    payload: MergeRequest,
    user: PluginUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """
    Merge the transactions from multiple completed batch jobs into a single CSV.
    Each row gets a 'source_file' column; jobs with no completed files are skipped.
    """
    if not payload.job_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No job IDs provided.")
    if len(payload.job_ids) > 20:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot merge more than 20 jobs at once.")

    client = get_yfw_client(
        settings.yfw_api_url,
        settings.yfw_api_key,
        secret_key=settings.yfw_secret_key,
        user_email=None if user.is_public else user.email,
    )

    all_transactions: list[dict] = []
    errors: list[str] = []

    for jid in payload.job_ids:
        try:
            yfw_resp = await client.get_job_status(jid)
        except Exception as exc:
            errors.append(f"Job {jid[:8]}: {exc}")
            continue
        transactions = _extract_job_transactions(yfw_resp)
        # Tag each transaction with its originating job for traceability
        for t in transactions:
            t["job_id"] = jid[:8]
        all_transactions.extend(transactions)

    if not all_transactions:
        detail = "No transactions found across the selected jobs."
        if errors:
            detail += " Errors: " + "; ".join(errors)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

    all_transactions.sort(key=lambda r: str(r.get("date") or ""))

    # Build CSV with an extra job_id column for merged files
    output = io.StringIO()
    fieldnames = ["date", "description", "amount", "transaction_type", "category", "balance", "source_file", "job_id"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_transactions)
    csv_bytes = output.getvalue().encode("utf-8")

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"statements-merged-{ts}.csv"
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
