import uuid
from datetime import date
from sqlalchemy import String, Float, Boolean, Date, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from backend.database.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    txn_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=True)
    merchant: Mapped[str] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    account_id: Mapped[str] = mapped_column(String(100), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anomaly_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    llm_category: Mapped[str] = mapped_column(String(100), nullable=True)
    llm_raw_response: Mapped[str] = mapped_column(Text, nullable=True)
    llm_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} txn_id={self.txn_id} amount={self.amount}>"
