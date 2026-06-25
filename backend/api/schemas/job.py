import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from backend.models.job import JobStatus


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str = "Job created and queued for processing"


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    filename: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    # Populated only on completed
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    summary: Optional["JobSummaryOut"] = None

    class Config:
        from_attributes = True


class JobSummaryOut(BaseModel):
    total_spend_inr: Optional[float] = None
    total_spend_usd: Optional[float] = None
    top_merchants: Optional[dict] = None
    anomaly_count: Optional[int] = None
    narrative: Optional[str] = None
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True


class JobListItem(BaseModel):
    job_id: uuid.UUID
    filename: str
    status: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginatedJobList(BaseModel):
    items: List[JobListItem]
    total: int
    page: int
    page_size: int
    pages: int


JobStatusResponse.model_rebuild()
