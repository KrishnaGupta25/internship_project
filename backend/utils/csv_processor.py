import uuid
import pandas as pd
from datetime import date
from typing import Tuple
from backend.core.logging import get_logger

logger = get_logger(__name__)

DOMESTIC_MERCHANTS = {"swiggy", "ola", "irctc"}


def _parse_date(val: str) -> date | None:
    """Try multiple date formats and return a date object or None."""
    if pd.isna(val) or str(val).strip() == "":
        return None
    val = str(val).strip()
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return pd.to_datetime(val, format=fmt).date()
        except (ValueError, TypeError):
            continue
    # Last resort: let pandas guess
    try:
        return pd.to_datetime(val, infer_datetime_format=True).date()
    except Exception:
        return None


def _clean_amount(val) -> float | None:
    """Strip currency symbols and convert to float."""
    if pd.isna(val):
        return None
    try:
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def process_csv(filepath: str) -> Tuple[pd.DataFrame, int, int]:
    """
    Load and clean a transaction CSV.
    Returns: (cleaned_df, raw_row_count, clean_row_count)
    """
    df = pd.read_csv(filepath, dtype=str)
    raw_count = len(df)
    logger.info(f"CSV loaded: {raw_count} raw rows")

    # Normalize column names to snake_case lowercase
    df.columns = (
        df.columns.str.strip().str.lower().str.replace(r"[\s]+", "_", regex=True)
    )

    # Map common column name variants
    col_map = {
        "transaction_id": "txn_id",
        "trans_id": "txn_id",
        "transaction_date": "date",
        "trans_date": "date",
        "vendor": "merchant",
        "amt": "amount",
        "curr": "currency",
        "acc_id": "account_id",
        "account": "account_id",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    # Ensure required columns exist
    required_cols = ["txn_id", "date", "merchant", "amount", "currency", "status", "category", "account_id", "notes"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # Parse dates
    df["date"] = df["date"].apply(_parse_date)

    # Clean amounts
    df["amount"] = df["amount"].apply(_clean_amount)

    # Uppercase status and currency
    df["status"] = df["status"].str.strip().str.upper()
    df["currency"] = df["currency"].str.strip().str.upper()

    # Fill blank category
    df["category"] = df["category"].fillna("Uncategorised").replace("", "Uncategorised")

    # Generate txn_id for blank rows
    def _ensure_txn_id(val):
        if pd.isna(val) or str(val).strip() == "":
            return str(uuid.uuid4())
        return str(val).strip()

    df["txn_id"] = df["txn_id"].apply(_ensure_txn_id)

    # Drop duplicates
    df.drop_duplicates(subset=["txn_id"], keep="first", inplace=True)

    # Drop rows where amount is None (unusable)
    df.dropna(subset=["amount"], inplace=True)

    clean_count = len(df)
    logger.info(f"CSV cleaned: {clean_count} clean rows (removed {raw_count - clean_count} rows)")
    return df, raw_count, clean_count
