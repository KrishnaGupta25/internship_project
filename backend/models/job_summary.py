import uuid
from sqlalchemy import String, Float, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from backend.database.base import Base


class JobSummary(Base):
    __tablename__ = "job_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    total_spend_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=True)
    total_spend_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=True)
    top_merchants: Mapped[dict] = mapped_column(JSONB, nullable=True)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="summary")

    def __repr__(self) -> str:
        return f"<JobSummary job_id={self.job_id} risk_level={self.risk_level}>"
