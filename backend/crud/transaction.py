import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models.transaction import Transaction


class TransactionCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_insert(self, transactions: List[Transaction]) -> None:
        self.session.add_all(transactions)
        await self.session.flush()

    async def get_by_job_id(self, job_id: uuid.UUID) -> List[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.job_id == job_id)
        )
        return list(result.scalars().all())

    async def get_anomalies_by_job_id(self, job_id: uuid.UUID) -> List[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(
                Transaction.job_id == job_id,
                Transaction.is_anomaly == True,
            )
        )
        return list(result.scalars().all())

    async def get_category_spend(self, job_id: uuid.UUID) -> List[dict]:
        result = await self.session.execute(
            select(
                Transaction.category,
                func.sum(Transaction.amount).label("total_amount"),
                func.count(Transaction.id).label("transaction_count"),
            )
            .where(Transaction.job_id == job_id)
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
        )
        rows = result.all()
        return [
            {
                "category": row.category or "Uncategorised",
                "total_amount": float(row.total_amount or 0),
                "transaction_count": row.transaction_count,
            }
            for row in rows
        ]
