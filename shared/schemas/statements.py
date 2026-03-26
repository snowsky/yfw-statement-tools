"""
Pydantic schemas for statement-tools upload portal.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    success: bool
    message: str
    transaction_count: int
    file_count: int
    download_url: str
    expires_at: datetime
    errors: list[str] = []


class BatchUploadResponse(BaseModel):
    success: bool
    job_id: str
    status: str
    message: Optional[str] = None


class BatchFileStatus(BaseModel):
    id: int
    filename: str
    status: str
    error_message: Optional[str] = None
    extracted_data: Optional[dict] = None


class BatchJobStatus(BaseModel):
    job_id: str
    status: str
    processed_files: int
    total_files: int
    successful_files: int
    failed_files: int
    progress_percentage: float
    files: list[BatchFileStatus] = []
    completed_at: Optional[datetime] = None
