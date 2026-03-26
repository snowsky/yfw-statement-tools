"""
Parse bank statement files (CSV or PDF) into a list of transaction dicts.

Each returned row has keys:
  date, description, amount (float), transaction_type, balance, category

Supports:
  - CSV with flexible column name detection (debit/credit split or single amount)
    Falls back to positional/content heuristics when header names are unrecognised.
  - PDF via pdfplumber table extraction (best-effort)
"""
from __future__ import annotations

import csv
import io
import re
from typing import Optional


# ── Column name normalisation ──────────────────────────────────────────────────

_DATE_ALIASES = {
    "date", "transaction date", "posted date", "value date", "trans date",
    "txn date", "posting date", "settlement date", "effective date",
    "processed date", "booking date", "entry date", "value", "trans. date",
}
_DESC_ALIASES = {
    "description", "memo", "payee", "narrative", "details", "transaction",
    "particulars", "reference", "narration", "remarks", "note", "notes",
    "transaction description", "transaction details", "payment details",
    "beneficiary", "transaction narrative", "trans description", "additional info",
    "transaction memo",
}
_AMOUNT_ALIASES = {
    "amount", "transaction amount", "net amount", "value", "sum",
    "transaction value", "net", "local amount", "amount (aud)", "amount (usd)",
    "amount (gbp)", "amount (eur)", "amt", "transaction amt",
}
_DEBIT_ALIASES = {
    "debit", "withdrawal", "withdrawals", "dr", "debit amount", "money out",
    "payments", "paid out", "charges", "debit (aud)", "debit (usd)",
    "out", "expenditure",
}
_CREDIT_ALIASES = {
    "credit", "deposit", "deposits", "cr", "credit amount", "money in",
    "receipts", "paid in", "credit (aud)", "credit (usd)", "in",
    "income",
}
_BALANCE_ALIASES = {
    "balance", "running balance", "closing balance", "available balance",
    "ledger balance", "current balance", "bal", "account balance",
}
_TYPE_ALIASES = {
    "type", "transaction type", "cr/dr", "dr/cr", "dc indicator",
    "debit/credit", "dr / cr",
}


def _norm(s: str) -> str:
    return re.sub(r"[\s/\-\.]+", " ", s.strip().lower()).strip()


def _find_col(headers: list[str], aliases: set[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        if _norm(h) in aliases:
            return i
    return None


_DATE_RE = re.compile(
    r"^\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}$"
    r"|^\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}$"
    r"|^\d{1,2}\s+\w{3}\s+\d{2,4}$"
    r"|^\w{3}\s+\d{1,2},?\s+\d{4}$"
)
_AMOUNT_RE = re.compile(r"^-?[\$£€]?[\d,]+\.?\d*$")


def _looks_like_date(val: str) -> bool:
    return bool(_DATE_RE.match(val.strip()))


def _looks_like_amount(val: str) -> bool:
    s = re.sub(r"[()$£€,\s]", "", val.strip())
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _parse_amount(raw: str) -> float:
    """Strip currency symbols, commas, parentheses; treat (x) as negative."""
    s = raw.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[()$£€,\s]", "", s)
    try:
        val = float(s) if s else 0.0
    except ValueError:
        val = 0.0
    return -val if negative else val


# ── CSV parser ─────────────────────────────────────────────────────────────────

def parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")  # handle BOM

    # Auto-detect delimiter
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|") if sample.strip() else None
    try:
        reader = csv.reader(io.StringIO(text), dialect=dialect)  # type: ignore[arg-type]
    except Exception:
        reader = csv.reader(io.StringIO(text))

    rows = list(reader)
    if not rows:
        return []

    # Find the header row (first row with ANY recognisable column name)
    all_aliases = (
        _DATE_ALIASES | _DESC_ALIASES | _AMOUNT_ALIASES |
        _DEBIT_ALIASES | _CREDIT_ALIASES | _BALANCE_ALIASES | _TYPE_ALIASES
    )
    header_idx = 0
    headers: list[str] = rows[0]
    best_score = 0
    for i, row in enumerate(rows[:10]):
        score = sum(1 for c in row if _norm(c) in all_aliases)
        if score > best_score:
            best_score = score
            header_idx = i
            headers = row

    col_date = _find_col(headers, _DATE_ALIASES)
    col_desc = _find_col(headers, _DESC_ALIASES)
    col_amount = _find_col(headers, _AMOUNT_ALIASES)
    col_debit = _find_col(headers, _DEBIT_ALIASES)
    col_credit = _find_col(headers, _CREDIT_ALIASES)
    col_balance = _find_col(headers, _BALANCE_ALIASES)
    col_type = _find_col(headers, _TYPE_ALIASES)

    # ── Positional fallback when header names are unrecognised ────────────────
    # Sample data rows to infer columns by content type
    sample_rows = [r for r in rows[header_idx + 1: header_idx + 6] if any(c.strip() for c in r)]

    if col_date is None and sample_rows:
        for i in range(len(headers)):
            vals = [r[i] for r in sample_rows if i < len(r) and r[i].strip()]
            if vals and all(_looks_like_date(v) for v in vals[:3]):
                col_date = i
                break

    if col_amount is None and col_debit is None and col_credit is None and sample_rows:
        # Find columns that look numeric (excluding the date column)
        numeric_cols = []
        for i in range(len(headers)):
            if i == col_date:
                continue
            vals = [r[i] for r in sample_rows if i < len(r) and r[i].strip()]
            if vals and sum(_looks_like_amount(v) for v in vals) >= len(vals) * 0.6:
                numeric_cols.append(i)
        if len(numeric_cols) == 1:
            col_amount = numeric_cols[0]
        elif len(numeric_cols) >= 2:
            # Assume last numeric column before balance is amount; last is balance
            col_amount = numeric_cols[-2]
            if col_balance is None:
                col_balance = numeric_cols[-1]

    if col_desc is None and sample_rows:
        # Longest text column that isn't date or amount
        skip = {col_date, col_amount, col_debit, col_credit, col_balance, col_type}
        text_cols = []
        for i in range(len(headers)):
            if i in skip:
                continue
            vals = [r[i] for r in sample_rows if i < len(r) and r[i].strip()]
            avg_len = sum(len(v) for v in vals) / max(len(vals), 1)
            if avg_len > 3:
                text_cols.append((avg_len, i))
        if text_cols:
            col_desc = max(text_cols)[1]

    if col_date is None or (col_amount is None and col_debit is None and col_credit is None):
        return []  # cannot parse — no date or no amount

    results: list[dict] = []
    for row in rows[header_idx + 1:]:
        if not any(c.strip() for c in row):
            continue  # blank row

        def get(idx: Optional[int]) -> str:
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        date = get(col_date)
        if not date:
            continue

        description = get(col_desc) if col_desc is not None else ""

        if col_amount is not None:
            raw = get(col_amount)
            if not raw:
                continue
            amount = _parse_amount(raw)
            tx_type = get(col_type) if col_type is not None else ("Credit" if amount >= 0 else "Debit")
        elif col_debit is not None or col_credit is not None:
            debit = _parse_amount(get(col_debit)) if col_debit is not None else 0.0
            credit = _parse_amount(get(col_credit)) if col_credit is not None else 0.0
            if debit == 0.0 and credit == 0.0:
                continue
            amount = credit - debit
            tx_type = get(col_type) if col_type is not None else ("Credit" if credit > 0 else "Debit")
        else:
            continue

        balance_raw = get(col_balance)
        balance: Optional[float] = None
        if balance_raw:
            try:
                balance = _parse_amount(balance_raw)
            except ValueError:
                pass

        results.append({
            "date": date,
            "description": description,
            "amount": amount,
            "transaction_type": tx_type,
            "balance": balance,
            "category": "",
        })

    return results


# ── PDF parser ─────────────────────────────────────────────────────────────────

def parse_pdf(content: bytes) -> list[dict]:
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber is required for PDF parsing. Add it to requirements.txt.")

    results: list[dict] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                rows = _parse_pdf_table(table)
                results.extend(rows)

        # Fallback: if no tables found, try text-based line extraction
        if not results:
            for page in pdf.pages:
                text = page.extract_text() or ""
                rows = _parse_pdf_text(text)
                results.extend(rows)

    return results


def _score_headers(headers: list[str]) -> int:
    normed = {_norm(h) for h in headers if h}
    score = 0
    if normed & _DATE_ALIASES:
        score += 3
    if normed & _DESC_ALIASES:
        score += 3
    if normed & (_AMOUNT_ALIASES | _DEBIT_ALIASES | _CREDIT_ALIASES):
        score += 2
    if normed & _BALANCE_ALIASES:
        score += 1
    return score


def _parse_pdf_table(table: list[list]) -> list[dict]:
    header_row_idx = 0
    best_score = 0
    for i, row in enumerate(table[:5]):
        score = _score_headers([c or "" for c in row])
        if score > best_score:
            best_score = score
            header_row_idx = i

    if best_score < 2:
        return []

    headers = [c or "" for c in table[header_row_idx]]
    col_date = _find_col(headers, _DATE_ALIASES)
    col_desc = _find_col(headers, _DESC_ALIASES)
    col_amount = _find_col(headers, _AMOUNT_ALIASES)
    col_debit = _find_col(headers, _DEBIT_ALIASES)
    col_credit = _find_col(headers, _CREDIT_ALIASES)
    col_balance = _find_col(headers, _BALANCE_ALIASES)
    col_type = _find_col(headers, _TYPE_ALIASES)

    if col_date is None or col_desc is None:
        return []

    results: list[dict] = []
    for row in table[header_row_idx + 1:]:
        cells = [c or "" for c in row]

        def get(idx: Optional[int]) -> str:
            if idx is None or idx >= len(cells):
                return ""
            return str(cells[idx]).strip()

        date = get(col_date)
        if not date or not re.search(r"\d", date):
            continue

        description = get(col_desc)

        if col_amount is not None:
            raw = get(col_amount)
            if not raw:
                continue
            amount = _parse_amount(raw)
            tx_type = get(col_type) if col_type is not None else ("Credit" if amount >= 0 else "Debit")
        elif col_debit is not None or col_credit is not None:
            debit = _parse_amount(get(col_debit)) if col_debit is not None else 0.0
            credit = _parse_amount(get(col_credit)) if col_credit is not None else 0.0
            if debit == 0.0 and credit == 0.0:
                continue
            amount = credit - debit
            tx_type = get(col_type) if col_type is not None else ("Credit" if credit > 0 else "Debit")
        else:
            continue

        balance_raw = get(col_balance)
        balance: Optional[float] = None
        if balance_raw:
            try:
                balance = _parse_amount(balance_raw)
            except ValueError:
                pass

        results.append({
            "date": date,
            "description": description,
            "amount": amount,
            "transaction_type": tx_type,
            "balance": balance,
            "category": "",
        })

    return results


_LINE_RE = re.compile(
    r"^(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})"
    r"\s+(.+?)\s+"
    r"([\-]?\$?[\d,]+\.\d{2})"
    r"(?:\s+([\-]?\$?[\d,]+\.\d{2}))?$"
)


def _parse_pdf_text(text: str) -> list[dict]:
    results: list[dict] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        date, description, amount_str, balance_str = m.groups()
        amount = _parse_amount(amount_str)
        balance: Optional[float] = None
        if balance_str:
            try:
                balance = _parse_amount(balance_str)
            except ValueError:
                pass
        results.append({
            "date": date,
            "description": description.strip(),
            "amount": amount,
            "transaction_type": "Credit" if amount >= 0 else "Debit",
            "balance": balance,
            "category": "",
        })
    return results
