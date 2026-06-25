import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.job_summary import JobSummary


class JobSummaryCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_or_update(
        self,
        job_id: uuid.UUID,
        total_spend_inr: float,
        total_spend_usd: float,
        top_merchants: dict,
        anomaly_count: int,
        narrative: str,
        risk_level: str,
    ) -> JobSummary:
        result = await self.session.execute(
            select(JobSummary).where(JobSummary.job_id == job_id)
        )
        summary = result.scalar_one_or_none()
        if summary:
            summary.total_spend_inr = total_spend_inr
            summary.total_spend_usd = total_spend_usd
            summary.top_merchants = top_merchants
            summary.anomaly_count = anomaly_count
            summary.narrative = narrative
            summary.risk_level = risk_level
        else:
            summary = JobSummary(
                job_id=job_id,
                total_spend_inr=total_spend_inr,
                total_spend_usd=total_spend_usd,
                top_merchants=top_merchants,
                anomaly_count=anomaly_count,
                narrative=narrative,
                risk_level=risk_level,
            )
            self.session.add(summary)
        await self.session.flush()
        await self.session.refresh(summary)
        return summary

    async def get_by_job_id(self, job_id: uuid.UUID) -> Optional[JobSummary]:
        result = await self.session.execute(
            select(JobSummary).where(JobSummary.job_id == job_id)
        )
        return result.scalar_one_or_none()
