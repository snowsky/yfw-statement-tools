"""
Statement-tools router — shared between plugin and standalone modes.

Endpoints:
  GET  /statements                → list statements (proxied from YFW)
  POST /statements/merge          → merge selected statements; returns direct
                                    download stream or cloud storage link
  GET  /statements/{id}/download  → stream a statement file directly to browser
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from shared.compat import get_current_user
from shared.schemas.statements import (
    MergeRequest,
    MergeResponse,
    StatementListResponse,
    StatementSummary,
)
from shared.services.invoice_api_client import InvoiceAPIClient
from shared.services.storage import get_storage_backend

router = APIRouter()


def _client(request: Request) -> InvoiceAPIClient:
    """Build an API client that forwards the caller's Authorization header if present."""
    auth = request.headers.get("Authorization", "")
    extra = {"Authorization": auth} if auth else {}
    return InvoiceAPIClient(extra_headers=extra)


@router.get("/statements", response_model=StatementListResponse)
async def list_statements(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    search: str | None = None,
    label: str | None = None,
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
):
    """Return a paginated list of bank statements from YFW."""
    client = _client(request)
    try:
        data = await client.list_statements(
            skip=skip, limit=limit, status=status, search=search, label=label
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    statements = [StatementSummary(**s) for s in data.get("statements", [])]
    return StatementListResponse(statements=statements, total=data.get("total", len(statements)))


@router.post("/statements/merge", response_model=MergeResponse)
async def merge_statements(
    payload: MergeRequest,
    request: Request,
    _user=Depends(get_current_user),
):
    """
    Merge two or more bank statements.

    - Calls YFW's merge API to produce a consolidated statement.
    - Then downloads the merged file.
    - If STORAGE_BACKEND=none  → streams the file directly back to the browser.
    - If STORAGE_BACKEND=s3|…  → uploads to cloud, returns a presigned URL.
    """
    if len(payload.ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least 2 statements to merge.",
        )

    client = _client(request)

    # 1. Trigger merge on YFW
    try:
        result = await client.merge(payload.ids)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    merged_id: int = result["id"]

    # 2. Download the merged file from YFW
    try:
        content, filename, _ct = await client.download_file(merged_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Merge succeeded (id={merged_id}) but file download failed: {exc}",
        )

    # 3. Store or prepare for direct streaming
    storage = get_storage_backend()

    from shared.compat import STANDALONE
    if STANDALONE:
        from standalone.config import get_settings
        retention_days = get_settings().file_retention_days
    else:
        retention_days = 7

    store_result = await storage.store(content, filename, retention_days)

    if store_result is None:
        # Noop storage: tell the frontend to call /statements/{id}/download
        return MergeResponse(
            success=True,
            message=result.get("message", f"Merged into statement #{merged_id}"),
            merged_id=merged_id,
            direct_download_path=f"/statements/{merged_id}/download",
        )

    download_url, expires_at = store_result
    return MergeResponse(
        success=True,
        message=result.get("message", f"Merged into statement #{merged_id}"),
        merged_id=merged_id,
        download_url=download_url,
        download_expires_at=expires_at,
    )


@router.get("/statements/{statement_id}/download")
async def download_statement(
    statement_id: int,
    request: Request,
    _user=Depends(get_current_user),
):
    """Stream a statement file directly to the browser (used when STORAGE_BACKEND=none)."""
    client = _client(request)
    try:
        content, filename, content_type = await client.download_file(statement_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
