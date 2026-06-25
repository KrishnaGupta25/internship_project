import os
import shutil
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.database.session import get_async_session
from backend.crud.job import JobCRUD
from backend.crud.transaction import TransactionCRUD
from backend.crud.job_summary import JobSummaryCRUD
from backend.api.schemas.job import (
    JobCreateResponse,
    JobStatusResponse,
    JobSummaryOut,
    JobListItem,
    PaginatedJobList,
)
from backend.api.schemas.transaction import (
    AnomalyOut,
    CategorySpend,
    JobResultsResponse,
    TransactionOut,
)
from backend.models.job import JobStatus
from backend.workers.tasks import process_transaction_job
from datetime import datetime, timezone
import math

router = APIRouter(prefix="/jobs", tags=["Jobs"])
logger = get_logger(__name__)


@router.post(
    "/upload",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload CSV file to create a processing job",
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file containing transaction data"),
    session: AsyncSession = Depends(get_async_session),
):
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted.",
        )

    # Validate content type
    if file.content_type not in ("text/csv", "application/csv", "application/octet-stream", "text/plain"):
        logger.warning(f"Unexpected content type: {file.content_type}")

    # Check file size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Save file to disk
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{file.filename}"
    filepath = os.path.join(settings.UPLOAD_DIR, safe_name)
    with open(filepath, "wb") as f:
        f.write(contents)

    logger.info(f"CSV saved to {filepath} ({len(contents)} bytes)")

    # Create Job record in DB
    job_crud = JobCRUD(session)
    job = await job_crud.create(filename=file.filename)
    await session.commit()
    await session.refresh(job)

    # Dispatch Celery task
    process_transaction_job.apply_async(
        args=[str(job.id), filepath, file.filename],
        queue="default",
    )

    logger.info(f"Job {job.id} created and queued")
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get(
    "/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get the status and summary of a job",
)
async def get_job_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    job_crud = JobCRUD(session)
    job = await job_crud.get_by_id(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )

    processing_time = None
    if job.completed_at and job.created_at:
        processing_time = (job.completed_at - job.created_at).total_seconds()

    summary_out = None
    if job.status == JobStatus.COMPLETED and job.summary:
        summary_out = JobSummaryOut(
            total_spend_inr=job.summary.total_spend_inr,
            total_spend_usd=job.summary.total_spend_usd,
            top_merchants=job.summary.top_merchants,
            anomaly_count=job.summary.anomaly_count,
            narrative=job.summary.narrative,
            risk_level=job.summary.risk_level,
        )

    return JobStatusResponse(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        processing_time_seconds=processing_time,
        summary=summary_out,
    )


@router.get(
    "/{job_id}/results",
    response_model=JobResultsResponse,
    summary="Get processed results for a completed job",
)
async def get_job_results(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    job_crud = JobCRUD(session)
    job = await job_crud.get_by_id(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed yet. Current status: {job.status}",
        )

    txn_crud = TransactionCRUD(session)
    summary_crud = JobSummaryCRUD(session)

    transactions = await txn_crud.get_by_job_id(job_id)
    anomalies = await txn_crud.get_anomalies_by_job_id(job_id)
    category_spend_raw = await txn_crud.get_category_spend(job_id)
    summary = await summary_crud.get_by_job_id(job_id)

    return JobResultsResponse(
        job_id=job_id,
        transactions=[TransactionOut.model_validate(t) for t in transactions],
        anomalies=[AnomalyOut.model_validate(t) for t in anomalies],
        category_spend=[CategorySpend(**cs) for cs in category_spend_raw],
        llm_summary={
            "total_spend_inr": summary.total_spend_inr,
            "total_spend_usd": summary.total_spend_usd,
            "top_merchants": summary.top_merchants,
            "anomaly_count": summary.anomaly_count,
            "narrative": summary.narrative,
            "risk_level": summary.risk_level,
        } if summary else None,
        narrative=summary.narrative if summary else None,
        risk_level=summary.risk_level if summary else None,
    )


@router.get(
    "",
    response_model=PaginatedJobList,
    summary="List all jobs with optional status filter and pagination",
)
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by job status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(
        settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Items per page",
    ),
    session: AsyncSession = Depends(get_async_session),
):
    # Validate status filter
    valid_statuses = {s.value for s in JobStatus}
    if status_filter and status_filter not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    job_crud = JobCRUD(session)
    jobs, total = await job_crud.list_jobs(
        status=status_filter, page=page, page_size=page_size
    )

    items = [
        JobListItem(
            job_id=j.id,
            filename=j.filename,
            status=j.status,
            row_count_raw=j.row_count_raw,
            row_count_clean=j.row_count_clean,
            created_at=j.created_at,
            completed_at=j.completed_at,
        )
        for j in jobs
    ]

    return PaginatedJobList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )
