"""initial_tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely create enum type for job status
    bind = op.get_bind()
    type_exists = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'jobstatus')")
    ).scalar()
    if not type_exists:
        bind.execute(
            sa.text("CREATE TYPE jobstatus AS ENUM ('pending', 'processing', 'completed', 'failed')")
        )

    # Create jobs table
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", postgresql.ENUM("pending", "processing", "completed", "failed", name="jobstatus", create_type=False), nullable=False, server_default="pending"),
        sa.Column("row_count_raw", sa.Integer, nullable=True),
        sa.Column("row_count_clean", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_jobs_id", "jobs", ["id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    # Create transactions table
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("txn_id", sa.String(100), nullable=True),
        sa.Column("date", sa.Date, nullable=True),
        sa.Column("merchant", sa.String(255), nullable=True),
        sa.Column("amount", sa.Float, nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("account_id", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_anomaly", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("anomaly_reason", sa.String(255), nullable=True),
        sa.Column("llm_category", sa.String(100), nullable=True),
        sa.Column("llm_raw_response", sa.Text, nullable=True),
        sa.Column("llm_failed", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_transactions_id", "transactions", ["id"])
    op.create_index("ix_transactions_job_id", "transactions", ["job_id"])
    op.create_index("ix_transactions_txn_id", "transactions", ["txn_id"])

    # Create job_summaries table
    op.create_table(
        "job_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("total_spend_inr", sa.Float, nullable=True),
        sa.Column("total_spend_usd", sa.Float, nullable=True),
        sa.Column("top_merchants", postgresql.JSONB, nullable=True),
        sa.Column("anomaly_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("narrative", sa.Text, nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=True),
    )
    op.create_index("ix_job_summaries_job_id", "job_summaries", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_summaries")
    op.drop_table("transactions")
    op.drop_table("jobs")
    
    bind = op.get_bind()
    type_exists = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'jobstatus')")
    ).scalar()
    if type_exists:
        bind.execute(sa.text("DROP TYPE jobstatus"))
