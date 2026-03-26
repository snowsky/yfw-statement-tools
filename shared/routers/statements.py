"""
Statement-tools router — shared between plugin and standalone modes.

Endpoints:
  GET  /statements              → list statements from YFW external API
  POST /statements/merge        → fetch transactions from each selected statement,
                                  merge locally into a CSV, return download stream
                                  or cloud storage link
  GET  /statements/{id}         → get single statement with transactions
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from shared.compat import get_current_user
from shared.schemas.statements import (
    MergeRequest,
    MergeResponse,
    StatementDetail,
    StatementListResponse,
    StatementSummary,
    StatementTransaction,
)
from shared.services.invoice_api_client import InvoiceAPIClient
from shared.services.storage import get_storage_backend

router = APIRouter()


def _client(request: Request) -> InvoiceAPIClient:
    auth = request.headers.get("Authorization", "")
    extra = {"Authorization": auth} if auth else {}
    return InvoiceAPIClient(extra_headers=extra)


def _to_summary(s: dict) -> StatementSummary:
    return StatementSummary(
        id=s["id"],
        account_name=s.get("account_name", s.get("original_filename", f"Statement {s['id']}")),
        statement_date=s.get("statement_date") or s.get("created_at") or datetime.utcnow().isoformat(),
        total_transactions=s.get("total_transactions", s.get("extracted_count", 0)),
    )


@router.get("/statements", response_model=StatementListResponse)
async def list_statements(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
):
    client = _client(request)
    try:
        data = await client.list_statements(skip=skip, limit=limit, search=search)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    raw = data.get("statements", data if isinstance(data, list) else [])
    statements = [_to_summary(s) for s in raw]
    return StatementListResponse(statements=statements, total=data.get("total", len(statements)))


@router.get("/statements/{statement_id}", response_model=StatementDetail)
async def get_statement(
    statement_id: int,
    request: Request,
    _user=Depends(get_current_user),
):
    client = _client(request)
    try:
        data = await client.get_statement(statement_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    summary = _to_summary(data)
    transactions = [
        StatementTransaction(**t) for t in data.get("transactions", [])
    ]
    return StatementDetail(**summary.model_dump(), transactions=transactions)


@router.post("/statements/merge", response_model=MergeResponse)
async def merge_statements(
    payload: MergeRequest,
    request: Request,
    _user=Depends(get_current_user),
):
    """
    Local merge: fetch each selected statement's transactions from YFW, combine
    into a single CSV, then either stream directly or upload to cloud storage.

    No JWT required — uses the external API (X-API-Key) to read transactions.
    """
    if len(payload.ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least 2 statements to merge.",
        )

    client = _client(request)

    # 1. Fetch transactions for each selected statement
    all_rows: list[dict] = []
    failed: list[int] = []

    for stmt_id in payload.ids:
        try:
            data = await client.get_statement(stmt_id)
            source = data.get("account_name", data.get("original_filename", f"Statement {stmt_id}"))
            for t in data.get("transactions", []):
                all_rows.append({
                    "source_statement": source,
                    "date": t.get("date", ""),
                    "description": t.get("description", ""),
                    "amount": t.get("amount", 0),
                    "transaction_type": t.get("transaction_type", ""),
                    "balance": t.get("balance", ""),
                    "category": t.get("category", ""),
                })
        except Exception:
            failed.append(stmt_id)

    if failed:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch statements: {failed}",
        )

    if not all_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected statements contain no transactions.",
        )

    # 2. Sort by date
    all_rows.sort(key=lambda r: str(r.get("date") or ""))

    # 3. Build CSV
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["date", "description", "amount", "transaction_type", "balance", "category", "source_statement"],
    )
    writer.writeheader()
    writer.writerows(all_rows)
    csv_bytes = output.getvalue().encode()

    filename = f"merged-statements-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"

    # 4. Store or stream
    storage = get_storage_backend()

    from shared.compat import STANDALONE
    retention_days = 7
    if STANDALONE:
        from standalone.config import get_settings
        retention_days = get_settings().file_retention_days

    store_result = await storage.store(csv_bytes, filename, retention_days)

    if store_result is None:
        # Stateless: stream directly
        return StreamingResponse(  # type: ignore[return-value]
            iter([csv_bytes]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    download_url, expires_at = store_result
    return MergeResponse(
        success=True,
        message=f"Merged {len(payload.ids)} statements ({len(all_rows)} transactions)",
        transaction_count=len(all_rows),
        download_url=download_url,
        download_expires_at=expires_at,
    )
