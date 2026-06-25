import uuid
import datetime as dt
from typing import Optional, List
from pydantic import BaseModel


class TransactionOut(BaseModel):
    id: uuid.UUID
    txn_id: Optional[str] = None
    date: Optional[dt.date] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_raw_response: Optional[str] = None
    llm_failed: bool

    class Config:
        from_attributes = True


class AnomalyOut(BaseModel):
    id: uuid.UUID
    txn_id: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    anomaly_reason: Optional[str] = None

    class Config:
        from_attributes = True


class CategorySpend(BaseModel):
    category: str
    total_amount: float
    transaction_count: int


class JobResultsResponse(BaseModel):
    job_id: uuid.UUID
    transactions: List[TransactionOut]
    anomalies: List[AnomalyOut]
    category_spend: List[CategorySpend]
    llm_summary: Optional[dict] = None
    narrative: Optional[str] = None
    risk_level: Optional[str] = None
