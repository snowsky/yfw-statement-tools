"""
Pydantic schemas for statement-tools.

These mirror the relevant fields from the YFW bank statement API so the
plugin works without importing YFW's own schemas directly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class StatementSummary(BaseModel):
    id: int
    original_filename: str
    status: str                      # uploaded | processing | processed | failed | merged
    extracted_count: int
    card_type: Optional[str] = None
    labels: Optional[list[str]] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by_username: Optional[str] = None


class StatementListResponse(BaseModel):
    statements: list[StatementSummary]
    total: int


class MergeRequest(BaseModel):
    ids: list[int]


class MergeResponse(BaseModel):
    success: bool
    message: str
    merged_id: int
    # Populated when STORAGE_BACKEND != "none"
    download_url: Optional[str] = None
    download_expires_at: Optional[datetime] = None
    # Populated when STORAGE_BACKEND == "none" (direct stream — frontend uses /download endpoint)
    direct_download_path: Optional[str] = None
