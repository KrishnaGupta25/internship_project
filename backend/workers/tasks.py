import os
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from backend.core.logging import get_logger, setup_logging
from backend.core.config import settings
from backend.workers.celery_app import celery_app
from backend.database.session import SyncSessionLocal
from backend.models.job import Job, JobStatus
from backend.models.transaction import Transaction
from backend.models.job_summary import JobSummary
from backend.utils.csv_processor import process_csv
from backend.utils.anomaly_detector import detect_anomalies
from backend.services.gemini_service import (
    categorize_transactions_batch,
    generate_job_summary,
)
import pandas as pd

setup_logging()
logger = get_logger(__name__)


def _clean_optional(value):
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    if not value or value.lower() == "nan":
        return None
    return value


@contextmanager
def get_session():
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _update_job_status(job_id: str, status: JobStatus, error: str = None):
    with get_session() as session:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if job:
            job.status = status
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.completed_at = datetime.now(timezone.utc)
            if error:
                job.error_message = error


@celery_app.task(
    name="backend.workers.tasks.process_transaction_job",
    bind=True,
    max_retries=0,
)
def process_transaction_job(self, job_id: str, filepath: str, filename: str):
    """
    Main Celery task: load CSV, clean, detect anomalies,
    LLM categorise, generate summary, persist to DB.
    """
    logger.info(f"Starting processing for job_id={job_id}")
    start_time = datetime.now(timezone.utc)

    try:
        # Mark as processing
        _update_job_status(job_id, JobStatus.PROCESSING)

        # Step 1: Load and clean CSV
        logger.info(f"Processing CSV file: {filepath}")
        df, raw_count, clean_count = process_csv(filepath)

        # Ensure llm_raw_response column exists in DataFrame
        df["llm_raw_response"] = None

        # Step 2: Anomaly detection
        logger.info("Running anomaly detection...")
        df = detect_anomalies(df)

        # Step 3: LLM categorisation for missing categories
        uncategorised_mask = df["category"].isin(["Uncategorised", "", None])
        uncategorised = df[uncategorised_mask]
        llm_failed_ids = set()

        if not uncategorised.empty:
            logger.info(f"Running LLM categorisation for {len(uncategorised)} rows...")
            batch_input = [
                {
                    "txn_id": row["txn_id"],
                    "merchant": row.get("merchant"),
                    "amount": row.get("amount"),
                    "currency": row.get("currency"),
                    "notes": row.get("notes"),
                }
                for _, row in uncategorised.iterrows()
            ]
            categorisation_results = categorize_transactions_batch(batch_input)

            for txn_id, res in categorisation_results.items():
                category = res.get("category")
                raw_response = res.get("raw_response")
                if category is None:
                    llm_failed_ids.add(txn_id)
                else:
                    df.loc[df["txn_id"] == txn_id, "llm_category"] = category
                    df.loc[df["txn_id"] == txn_id, "category"] = category
                    df.loc[df["txn_id"] == txn_id, "llm_raw_response"] = raw_response
                    if res.get("llm_failed"):
                        llm_failed_ids.add(txn_id)

        # Step 4: Persist transactions to DB
        logger.info(f"Persisting {clean_count} transactions to database...")
        transactions_to_insert = []
        for _, row in df.iterrows():
            t = Transaction(
                job_id=uuid.UUID(job_id),
                txn_id=_clean_optional(row.get("txn_id")),
                date=row.get("date") if pd.notna(row.get("date")) else None,
                merchant=_clean_optional(row.get("merchant")),
                amount=float(row["amount"]) if pd.notna(row.get("amount")) else None,
                currency=_clean_optional(row.get("currency")),
                status=_clean_optional(row.get("status")),
                category=_clean_optional(row.get("category")) or "Uncategorised",
                account_id=_clean_optional(row.get("account_id")),
                notes=_clean_optional(row.get("notes")),
                is_anomaly=bool(row.get("is_anomaly", False)),
                anomaly_reason=_clean_optional(row.get("anomaly_reason")),
                llm_category=_clean_optional(row.get("llm_category")),
                llm_raw_response=_clean_optional(row.get("llm_raw_response")),
                llm_failed=row["txn_id"] in llm_failed_ids,
            )
            transactions_to_insert.append(t)

        with get_session() as session:
            session.bulk_save_objects(transactions_to_insert)

        # Step 5: Update row counts
        with get_session() as session:
            job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
            if job:
                job.row_count_raw = raw_count
                job.row_count_clean = clean_count

        # Step 6: Generate LLM job summary
        logger.info("Generating LLM job summary...")
        spend_by_currency = (
            df.groupby("currency")["amount"].sum().to_dict() if "currency" in df.columns else {}
        )
        merchant_spend = (
            df.groupby("merchant")["amount"].sum().sort_values(ascending=False)
            if "merchant" in df.columns
            else pd.Series(dtype=float)
        )
        top_merchants = merchant_spend.head(3).to_dict() if not merchant_spend.empty else {}
        anomaly_count = int(df["is_anomaly"].sum())

        summary_input = {
            "total_transactions": clean_count,
            "spend_by_currency": {k: float(v) for k, v in spend_by_currency.items()},
            "top_merchants": list(top_merchants.keys()),
            "anomaly_count": anomaly_count,
            "filename": filename,
        }

        llm_result = generate_job_summary(summary_input)

        # Step 7: Persist JobSummary
        with get_session() as session:
            existing = session.query(JobSummary).filter(
                JobSummary.job_id == uuid.UUID(job_id)
            ).first()

            spend_per_currency = llm_result.get("total_spend_per_currency")
            if not isinstance(spend_per_currency, dict):
                spend_per_currency = {}

            def get_spend_safe(curr, default_val):
                val = spend_per_currency.get(curr)
                if val is None:
                    return default_val
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default_val

            total_spend_inr = get_spend_safe("INR", spend_by_currency.get("INR", 0.0))
            total_spend_usd = get_spend_safe("USD", spend_by_currency.get("USD", 0.0))

            summary_obj = JobSummary(
                job_id=uuid.UUID(job_id),
                total_spend_inr=total_spend_inr,
                total_spend_usd=total_spend_usd,
                top_merchants={
                    str(name): float(amt)
                    for name, amt in list(top_merchants.items())[:3]
                    if pd.notna(name) and pd.notna(amt)
                },
                anomaly_count=anomaly_count,
                narrative=llm_result.get("narrative", ""),
                risk_level=llm_result.get("risk_level", "low"),
            )
            if existing:
                session.delete(existing)
                session.flush()
            session.add(summary_obj)

        # Step 8: Mark job completed
        _update_job_status(job_id, JobStatus.COMPLETED)
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"Job {job_id} completed in {elapsed:.2f}s")

    except Exception as exc:
        logger.error(f"Job {job_id} failed: {exc}", exc_info=True)
        _update_job_status(job_id, JobStatus.FAILED, error=str(exc))
        raise
    finally:
        # Clean up temp file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
