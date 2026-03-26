"""
Statement-tools router — upload portal.

Endpoints:
  POST /statements/upload          → forward files to YFW, return merged CSV download link
  GET  /statements/download/{token} → serve a previously generated CSV (valid 1 hour)
"""
from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from shared.schemas.statements import UploadResponse, BatchUploadResponse, BatchJobStatus
from shared.services.invoice_api_client import YFWClient
from standalone.auth import get_current_user
from standalone.config import get_settings

router = APIRouter()


# ── Temp file management ──────────────────────────────────────────────────────

def _temp_dir() -> Path:
    settings = get_settings()
    d = Path(settings.temp_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_expired(filepath: Path, expiry_minutes: int) -> bool:
    """Check if a file is older than expiry_minutes."""
    if not filepath.exists():
        return True
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime > timedelta(minutes=expiry_minutes)


def cleanup_expired_files() -> int:
    """Remove expired CSV files from the temp directory. Returns count removed."""
    settings = get_settings()
    removed = 0
    for f in _temp_dir().glob("*.csv"):
        if _is_expired(f, settings.download_expiry_minutes):
            f.unlink(missing_ok=True)
            removed += 1
    return removed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_client(request: Request) -> YFWClient:
    """Build a YFWClient from request headers or server config."""
    api_key = request.headers.get("X-API-Key") or ""
    yfw_url = request.headers.get("X-YFW-URL") or ""

    if not api_key or not yfw_url:
        settings = get_settings()
        api_key = api_key or settings.yfw_api_key
        yfw_url = yfw_url or settings.yfw_api_url

    return YFWClient(yfw_url=yfw_url, api_key=api_key)


ALLOWED_EXTENSIONS = {"csv", "pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _validate_file(upload: UploadFile) -> str:
    """Validate a file and return its extension."""
    name = upload.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {name}. Only CSV and PDF are accepted.",
        )
    return ext


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/statements/upload", response_model=UploadResponse)
async def upload_statements(
    files: list[UploadFile] = File(...),
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
):
    """
    Upload one or more bank statement files (CSV/PDF).

    Each file is forwarded to YFW's AI statement processor.
    All extracted transactions are merged into a single CSV.
    Returns a download link valid for 1 hour.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No files provided.",
        )

    # Validate all files first
    for f in files:
        _validate_file(f)

    client = _build_client(request)
    settings = get_settings()

    all_transactions: list[dict] = []
    errors: list[str] = []

    for upload in files:
        name = upload.filename or "unknown"
        content = await upload.read()

        if len(content) > MAX_FILE_SIZE:
            errors.append(f"{name}: file exceeds 20 MB limit.")
            continue

        ct = upload.content_type or "application/octet-stream"

        try:
            transactions = await client.process_statement(content, name, ct)
            for t in transactions:
                t["source_file"] = name
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

    # Sort by date (best-effort)
    all_transactions.sort(key=lambda r: str(r.get("date") or ""))

    # Build merged CSV
    output = io.StringIO()
    fieldnames = [
        "date", "description", "amount", "transaction_type",
        "category", "balance", "source_file",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_transactions)
    csv_bytes = output.getvalue().encode("utf-8")

    # Save to temp directory with a UUID token
    token = uuid.uuid4().hex
    filename = f"{token}.csv"
    filepath = _temp_dir() / filename
    filepath.write_bytes(csv_bytes)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.download_expiry_minutes)

    # Build download URL (relative — frontend prepends base)
    prefix = "/api/v1/external/statement-tools"
    download_url = f"{prefix}/statements/download/{token}"

    return UploadResponse(
        success=True,
        message=f"Processed {len(files)} file(s) — {len(all_transactions)} transactions extracted.",
        transaction_count=len(all_transactions),
        file_count=len(files),
        download_url=download_url,
        expires_at=expires_at,
        errors=errors,
    )


@router.post("/batch/upload", response_model=BatchUploadResponse)
async def upload_batch(
    files: list[UploadFile] = File(...),
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
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

    # Validate all files
    for f in files:
        _validate_file(f)

    client = _build_client(request)
    
    # Prepare files for the client
    file_tuples = []
    for upload in files:
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
             raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {upload.filename} exceeds 20 MB limit."
            )
        file_tuples.append((
            upload.filename or "unknown",
            content,
            upload.content_type or "application/octet-stream"
        ))

    try:
        yfw_resp = await client.upload_batch(file_tuples)
        return BatchUploadResponse(
            success=True,
            job_id=yfw_resp.get("job_id", ""),
            status=yfw_resp.get("status", "pending"),
            message="Batch job created successfully."
        )
    except Exception as exc:
        logger.error(f"Batch upload failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )


@router.get("/batch/jobs/{job_id}", response_model=BatchJobStatus)
async def get_batch_job_status(
    job_id: str,
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
):
    """
    Get the status and results of a batch processing job.
    """
    client = _build_client(request)
    try:
        yfw_resp = await client.get_job_status(job_id)
        
        # Map YFW response to our BatchJobStatus schema
        # We need to extract progress info from the 'progress' dict in YFW response
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
            completed_at=yfw_resp.get("timestamps", {}).get("completed_at")
        )
    except Exception as exc:
        logger.error(f"Failed to get job status for {job_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )


@router.get("/statements/download/{token}")
async def download_csv(token: str):
    """
    Download a previously generated merged CSV.

    The token is a UUID returned by the upload endpoint.
    Links expire after the configured retention period (default: 1 hour).
    """
    # Sanitize token — must be a valid hex UUID
    try:
        uuid.UUID(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid download token.")

    settings = get_settings()
    filepath = _temp_dir() / f"{token}.csv"

    if not filepath.exists() or _is_expired(filepath, settings.download_expiry_minutes):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Download link has expired. Please upload again.",
        )

    download_name = f"statements-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"

    return FileResponse(
        path=str(filepath),
        media_type="text/csv",
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
