"""
Statement-tools router — shared between plugin and standalone modes.

Endpoints:
  GET  /statements              → list statements from YFW external API
  POST /statements/merge        → fetch transactions from each selected statement,
                                  merge locally into a CSV, return download stream
                                  or cloud storage link
  GET  /statements/{id}         → get single statement with transactions
  POST /statements/upload       → parse uploaded CSV/PDF files, return merged CSV
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from shared.compat import get_current_user
from shared.services.statement_parser import parse_csv, parse_pdf
from shared.schemas.statements import (
    MergeRequest,
    MergeResponse,
    StatementDetail,
    StatementListResponse,
    StatementSummary,
    StatementTransaction,
    UploadToYFWResponse,
)
from shared.services.invoice_api_client import InvoiceAPIClient
from shared.services.storage import get_storage_backend

router = APIRouter()


def _csv_hint(content: bytes, ext: str) -> str:
    """Return a human-readable hint about what columns were found in a CSV."""
    try:
        import csv as _csv, io as _io
        text = content.decode("utf-8-sig", errors="replace")
        reader = _csv.reader(_io.StringIO(text))
        headers = next(reader, [])
        if headers:
            return f"Columns found: {', '.join(repr(h) for h in headers[:8])}. Expected: date and amount columns."
    except Exception:
        pass
    return ""


def _client(request: Request) -> InvoiceAPIClient:
    auth = request.headers.get("Authorization", "")
    extra = {"Authorization": auth} if auth else {}
    yfw_url = request.headers.get("X-YFW-URL") or None
    api_key = request.headers.get("X-API-Key") or None
    return InvoiceAPIClient(extra_headers=extra, yfw_url=yfw_url, api_key=api_key)


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


@router.post("/statements/process-with-yfw")
async def process_with_yfw(
    file: UploadFile = File(...),
    format: str = "csv",
    card_type: str = "auto",
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
):
    """
    Forward a single PDF/CSV file to YFW's AI statement processor
    (POST /api/v1/statements/process).

    YFW uses OCR + LLM to extract transactions — works for image-rendered PDFs
    that pdfplumber cannot parse.

    Plugin mode:  forwards the caller's JWT Authorization header → works.
    Standalone:   this endpoint requires JWT (not API key); returns 501.
    """
    from shared.compat import STANDALONE

    if STANDALONE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "YFW AI processing requires a JWT session and is only available "
                "when statement-tools runs as a YFW plugin. "
                "In standalone mode, use your bank's CSV export instead of the PDF."
            ),
        )

    # Plugin mode: forward the caller's JWT to YFW's internal API
    yfw_url = "http://localhost:8000"  # same process in plugin mode
    auth_header = request.headers.get("Authorization", "") if request else ""

    content = await file.read()
    filename = file.filename or "statement.pdf"

    import httpx
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{yfw_url}/api/v1/statements/process",
                params={"format": format, "card_type": card_type},
                files={"file": (filename, content, file.content_type or "application/octet-stream")},
                headers={"Authorization": auth_header} if auth_header else {},
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Cannot reach YFW: {exc}")

    if resp.status_code == 403:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"YFW denied access: {resp.text[:200]}")
    if resp.status_code == 402:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="YFW AI processing requires a commercial license or active trial.")
    if not resp.is_success:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"YFW returned {resp.status_code}: {resp.text[:200]}")

    ct = resp.headers.get("content-type", "text/csv")
    disposition = resp.headers.get("content-disposition", f'attachment; filename="yfw-{filename}.csv"')
    return StreamingResponse(
        iter([resp.content]),
        media_type=ct,
        headers={"Content-Disposition": disposition},
    )


@router.post("/statements/parse-debug")
async def parse_debug(
    file: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    """
    Dev helper: returns raw pdfplumber/csv extraction so you can see what
    the parser sees without attempting transaction mapping.
    """
    name = file.filename or ""
    content = await file.read()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ct = (file.content_type or "").lower()

    if ext == "pdf" or "pdf" in ct:
        try:
            import pdfplumber, io as _io
            result: dict = {"pages": []}
            with pdfplumber.open(_io.BytesIO(content)) as pdf:
                for i, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    text = page.extract_text() or ""
                    char_count = len(page.chars) if hasattr(page, "chars") else 0
                    image_count = len(page.images) if hasattr(page, "images") else 0
                    result["pages"].append({
                        "page": i + 1,
                        "text_lines": text.splitlines(),
                        "char_count": char_count,
                        "image_count": image_count,
                        "tables": [
                            {"rows": t[:6], "total_rows": len(t)}
                            for t in (tables or [])
                        ],
                    })
            return result
        except Exception as exc:
            return {"error": str(exc)}
    else:
        # CSV: return first 5 rows and detected columns
        import csv as _csv, io as _io
        text = content.decode("utf-8-sig", errors="replace")
        reader = _csv.reader(_io.StringIO(text))
        rows = [r for r, _ in zip(reader, range(6))]
        return {"rows": rows}


@router.post("/statements/upload")
async def upload_statements(
    files: list[UploadFile] = File(...),
    _user=Depends(get_current_user),
):
    """
    Parse one or more uploaded CSV or PDF bank statement files.
    Returns a merged CSV (all transactions combined, sorted by date).

    Accepts: text/csv, application/pdf  (detected by filename extension if
    Content-Type is missing or generic).
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files provided.")

    all_rows: list[dict] = []
    errors: list[str] = []

    for upload in files:
        name = upload.filename or ""
        content = await upload.read()

        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        ct = (upload.content_type or "").lower()

        try:
            if ext == "pdf" or "pdf" in ct:
                rows = parse_pdf(content)
            elif ext == "csv" or "csv" in ct or "text/plain" in ct:
                rows = parse_csv(content)
            else:
                # Last-resort: try CSV then PDF
                rows = parse_csv(content)
                if not rows:
                    rows = parse_pdf(content)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue

        if not rows:
            # Give a helpful hint about the columns we found vs what's needed
            hint = _csv_hint(content, ext) if ext != "pdf" and "pdf" not in ct else ""
            errors.append(
                f"{name}: no transactions found."
                + (f" {hint}" if hint else " Ensure the file has date and amount columns.")
            )
            continue

        for row in rows:
            row["source_statement"] = name
        all_rows.extend(rows)

    if errors and not all_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    if not all_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No transactions could be extracted from the uploaded files.",
        )

    # Sort by date string (lexicographic — works for ISO and most dd/mm/yyyy formats)
    all_rows.sort(key=lambda r: str(r.get("date") or ""))

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["date", "description", "amount", "transaction_type", "balance", "category", "source_statement"],
    )
    writer.writeheader()
    writer.writerows(all_rows)
    csv_bytes = output.getvalue().encode()

    filename = f"uploaded-statements-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"

    storage = get_storage_backend()

    from shared.compat import STANDALONE
    retention_days = 7
    if STANDALONE:
        from standalone.config import get_settings
        retention_days = get_settings().file_retention_days

    store_result = await storage.store(csv_bytes, filename, retention_days)

    if store_result is None:
        return StreamingResponse(  # type: ignore[return-value]
            iter([csv_bytes]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    download_url, expires_at = store_result
    return MergeResponse(
        success=True,
        message=f"Parsed {len(files)} file(s) — {len(all_rows)} transactions"
        + (f" ({len(errors)} file(s) had errors)" if errors else ""),
        transaction_count=len(all_rows),
        download_url=download_url,
        download_expires_at=expires_at,
    )


def _to_yfw_type(tx_type: str) -> str:
    """Map Credit/Debit → income/expense for YFW external-transactions API."""
    t = tx_type.strip().lower()
    if t in ("credit", "income", "deposit"):
        return "income"
    return "expense"


@router.post("/statements/upload-to-yfw", response_model=UploadToYFWResponse)
async def upload_statements_to_yfw(
    files: list[UploadFile] = File(...),
    source_system: str = "statement-tools",
    request: Request = None,  # type: ignore[assignment]
    _user=Depends(get_current_user),
):
    """
    Parse uploaded CSV/PDF files locally, then push each transaction to
    YFW's external-transactions API (POST /api/v1/external-transactions/transactions).

    The records will appear in YFW under External Transactions for review.

    Requires the API key to have external_transactions write permission in YFW.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files provided.")

    # 1. Parse files
    all_rows: list[dict] = []
    parse_errors: list[str] = []

    for upload in files:
        name = upload.filename or ""
        content = await upload.read()
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        ct = (upload.content_type or "").lower()

        try:
            if ext == "pdf" or "pdf" in ct:
                rows = parse_pdf(content)
            else:
                rows = parse_csv(content)
                if not rows:
                    rows = parse_pdf(content)
        except Exception as exc:
            parse_errors.append(f"{name}: {exc}")
            continue

        if not rows:
            parse_errors.append(f"{name}: no transactions found.")
            continue

        for row in rows:
            row["_source_file"] = name
        all_rows.extend(rows)

    if not all_rows:
        detail = "No transactions could be extracted."
        if parse_errors:
            detail += " " + "; ".join(parse_errors)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

    # 2. Push to YFW
    client = _client(request)
    created = 0
    failed = 0
    push_errors: list[str] = []

    for row in all_rows:
        raw_amount = float(row.get("amount") or 0)
        tx_type = _to_yfw_type(row.get("transaction_type") or ("income" if raw_amount >= 0 else "expense"))
        amount = abs(raw_amount) if raw_amount != 0 else 0.01  # API requires > 0

        payload = {
            "transaction_type": tx_type,
            "amount": str(amount),
            "currency": "USD",
            "date": row.get("date", datetime.utcnow().isoformat()),
            "description": row.get("description") or "(no description)",
            "source_system": source_system,
        }
        if row.get("category"):
            payload["category"] = row["category"]

        try:
            await client.create_external_transaction(payload)
            created += 1
        except Exception as exc:
            failed += 1
            if len(push_errors) < 10:  # cap error list
                push_errors.append(f"{row.get('_source_file', '')} [{row.get('date', '')}] {row.get('description', '')[:40]}: {exc}")

    all_errors = parse_errors + push_errors
    return UploadToYFWResponse(
        success=created > 0,
        message=f"Created {created} transaction(s) in YFW"
        + (f"; {failed} failed" if failed else "")
        + (f" ({len(parse_errors)} file(s) skipped)" if parse_errors else ""),
        created_count=created,
        failed_count=failed,
        errors=all_errors,
    )
