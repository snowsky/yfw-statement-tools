# Code Review — yfw-statement-tools

**Date:** 2026-03-26

## Overview

A well-architected dual-mode application (standalone SPA **or** YFW plugin) for uploading, parsing, merging, and exporting bank statement CSV/PDF files. FastAPI backend + React/TypeScript frontend with Docker Compose support.

**Overall verdict: solid foundation, well-structured code sharing, thoughtful parser heuristics.** Below are findings grouped by severity.

---

## Architecture — What's Done Well

| Aspect | Notes |
|---|---|
| **DRY code sharing** | `shared/` used by both plugin and standalone — routers, schemas, services, and UI pages are never duplicated |
| **Compat shim** | `shared/compat.py` — clean try/except for `get_db` and `get_current_user` import switching |
| **Strategy pattern for storage** | `shared/services/storage.py` — NoopStorage / S3Storage / Azure / GCS with clean ABC |
| **Parser robustness** | `shared/services/statement_parser.py` — very thorough column alias detection (30+ aliases), positional fallback, debit/credit split, PDF table + text-line extraction |
| **Plugin manifest** | `plugin.json` and `__init__.py` — clean plugin registration contract |
| **Docker setup** | Multi-stage UI Dockerfile, nginx reverse proxy with SPA fallback, configurable ports |

---

## Issues & Suggestions

### 🔴 Critical / Security

1. **Auth validates on every request by probing YFW**
   - `standalone/auth.py:48-58` — `get_current_user` makes an HTTP call to YFW's external API on **every single request** to validate the API key. This adds ~100-500ms latency and may rate-limit against YFW.
   - **Fix:** Cache the validation result (e.g. `@lru_cache` keyed on API key + YFW URL, with a TTL of 5 minutes), or issue a short-lived JWT after first validation.

2. **`cors_origins = ["*"]` in production**
   - `standalone/config.py:38` — Wide-open CORS is fine for local dev but dangerous for production deployments.
   - **Fix:** Default to the frontend's origin (e.g. `["http://localhost:5173"]`) and document that users should set `CORS_ORIGINS` in `.env`.

3. **No test suite at all** — zero test files found in the entire repo. The parser logic (392 lines) has many edge cases that should have unit tests.

### 🟡 Bugs / Correctness

4. **`datetime.utcnow()` is deprecated since Python 3.12**
   - Used in `shared/routers/statements.py` at lines 64, 173, 391, 497.
   - **Fix:** Use `datetime.now(timezone.utc)` instead.

5. **Merge endpoint return type mismatch**
   - `shared/routers/statements.py:188` — The endpoint declares `response_model=MergeResponse` but sometimes returns a `StreamingResponse`. The `# type: ignore[return-value]` suppresses this, but the OpenAPI docs will be misleading.
   - **Fix:** Remove `response_model=MergeResponse` from the decorator and document both response shapes.

6. **Date sorting is lexicographic — fragile**
   - `shared/routers/statements.py:161` — `all_rows.sort(key=lambda r: str(r.get("date")))` — comment says "works for ISO and most dd/mm/yyyy" but `15/03/2025` sorts after `02/12/2024` incorrectly.
   - **Fix:** Parse dates into actual `datetime` objects before sorting, with a fallback to string sort.

7. **`_parse_amount` silently returns 0.0 for unparseable values**
   - `shared/services/statement_parser.py:100-102` — A row with `amount = "N/A"` yields `0.0`, which is then included as a real transaction.

8. **`get` closure re-defined in a loop**
   - `shared/services/statement_parser.py:196-199` and `314-317` — The `get()` function is re-defined inside every loop iteration. Python closures capture by reference, so this works, but it's inefficient and confusing.
   - **Fix:** Move `get()` outside the loop or use a simple index helper.

### 🟡 Design / Maintainability

9. **`schemas/__init__.py` is missing newer exports**
   - `shared/schemas/__init__.py` — Only exports `MergeRequest`, `MergeResponse`, `StatementSummary`, `StatementListResponse`. Missing: `StatementDetail`, `StatementTransaction`, `UploadToYFWResponse`.
   - These are imported directly by the router (which works), but the `__init__.py` should be kept consistent.

10. **S3Storage uses sync `upload_fileobj` in an async endpoint**
    - `shared/services/storage.py:81` — `s3.upload_fileobj()` is a blocking call inside an `async def store()`. This blocks the event loop.
    - **Fix:** Use `asyncio.to_thread(s3.upload_fileobj, ...)` or switch to `aioboto3`.

11. **`upload-to-yfw` endpoint pushes transactions sequentially**
    - `shared/routers/statements.py:488-510` — Each transaction is pushed one-by-one with `await client.create_external_transaction()`. For 500 transactions, this is very slow.
    - **Fix:** Batch the calls with `asyncio.gather()` (with a semaphore for concurrency control), or implement a bulk endpoint.

12. **New httpx client created per API call**
    - `shared/services/invoice_api_client.py:78` — Every `list_statements()` / `get_statement()` / `create_external_transaction()` call creates a new `httpx.AsyncClient`. This loses connection pooling benefits.
    - **Fix:** Make `InvoiceAPIClient` a context manager or use a shared client with lifespan.

13. **`main.py` uses deprecated `@app.on_event("startup")`**
    - Since FastAPI 0.106+, use the `lifespan` parameter instead.

14. **Frontend uses `window.location.href` for navigation**
    - `ui/standalone/src/App.tsx:26` — `window.location.href = "/merge"` causes a full page reload. Should use `useNavigate()` from react-router-dom.

15. **No global CSS / no favicon** — The standalone app has zero CSS files and no favicon, making it look bare.

### 🟢 Minor / Nits

16. **Inline `import` statements** — `from shared.compat import STANDALONE` is imported at the top of `storage.py` and `invoice_api_client.py`, but then also imported inline inside functions in `statements.py` (lines 178, 222, 395). Pick one approach.

17. **Hardcoded `"USD"` currency** — `shared/routers/statements.py:496` — The upload-to-yfw endpoint hardcodes currency to `"USD"`. Should allow the user to specify it.

18. **`source_system` param is a query param, not in FormData** — `shared/routers/statements.py:432` uses `source_system: str = "statement-tools"` as a regular param, but the frontend sends it as `form.append("source_system", sourceSystem)` in `ui/shared/api.ts:177`. FastAPI should receive it via `Form(...)` instead.

19. **`csv.Sniffer().sniff()` can raise `csv.Error`** — `shared/services/statement_parser.py:113` — The sniffer isn't wrapped in try/except. If the sample is unusual, this will crash.

20. **Duplicate download-trigger pattern** — The CSV blob download logic (create `<a>`, click, revoke) is repeated 3 times in `api.ts`. Extract into a `triggerDownload(blob, filename)` helper.

---

## Summary & Recommended Next Steps

| Priority | Action |
|---|---|
| **P0** | Add caching to API key validation in `auth.py` |
| **P0** | Add unit tests for `statement_parser.py` (CSV + PDF parsing edge cases) |
| **P1** | Fix deprecated `datetime.utcnow()` → `datetime.now(timezone.utc)` |
| **P1** | Fix date sorting to use parsed dates, not string sort |
| **P1** | Wrap S3 blocking call in `asyncio.to_thread()` |
| **P2** | Tighten CORS origins for production |
| **P2** | Batch `upload-to-yfw` API calls |
| **P2** | Reuse httpx client for connection pooling |
| **P3** | Clean up minor issues (inline imports, duplicate download helper, `Form()` for source_system) |
