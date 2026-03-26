"""
Pydantic schemas for statement-tools.

Field names match the YFW external developer API (ExternalStatementResponse):
  id, statement_date, account_name, total_transactions, transactions
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class StatementTransaction(BaseModel):
    id: int
    date: str
    description: str
    amount: float
    transaction_type: str
    balance: Optional[float] = None
    category: Optional[str] = None


class StatementSummary(BaseModel):
    id: int
    account_name: str          # original_filename in YFW
    statement_date: datetime
    total_transactions: int


class StatementDetail(StatementSummary):
    transactions: list[StatementTransaction] = []


class StatementListResponse(BaseModel):
    statements: list[StatementSummary]
    total: int


class MergeRequest(BaseModel):
    ids: list[int]


class MergeResponse(BaseModel):
    success: bool
    message: str
    transaction_count: int
    # Cloud storage mode
    download_url: Optional[str] = None
    download_expires_at: Optional[datetime] = None
    # Stateless mode — frontend POSTs to /download-merged with the token
    download_token: Optional[str] = None


class UploadToYFWResponse(BaseModel):
    success: bool
    message: str
    created_count: int
    failed_count: int
    errors: list[str] = []
