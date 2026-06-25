import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from backend.models.job import Job, JobStatus
from backend.models.job_summary import JobSummary


class JobCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, filename: str) -> Job:
        job = Job(filename=filename, status=JobStatus.PENDING)
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Optional[Job]:
        result = await self.session.execute(
            select(Job)
            .options(selectinload(Job.summary))
            .where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> None:
        values = {"status": status}
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            values["completed_at"] = datetime.now(timezone.utc)
        if error_message:
            values["error_message"] = error_message
        await self.session.execute(
            update(Job).where(Job.id == job_id).values(**values)
        )
        await self.session.flush()

    async def update_row_counts(
        self, job_id: uuid.UUID, raw: int, clean: int
    ) -> None:
        await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(row_count_raw=raw, row_count_clean=clean)
        )
        await self.session.flush()

    async def list_jobs(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Job], int]:
        query = select(Job)
        count_query = select(func.count(Job.id))

        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        query = query.order_by(Job.created_at.desc()).offset(offset).limit(page_size)
        result = await self.session.execute(query)
        jobs = result.scalars().all()

        return list(jobs), total
