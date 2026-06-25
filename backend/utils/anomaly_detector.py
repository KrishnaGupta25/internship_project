import pandas as pd
from backend.core.logging import get_logger

logger = get_logger(__name__)

DOMESTIC_MERCHANTS = {"swiggy", "ola", "irctc"}


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect anomalies in the cleaned transactions DataFrame.
    Adds 'is_anomaly' and 'anomaly_reason' columns.
    """
    df = df.copy()
    df["is_anomaly"] = False
    df["anomaly_reason"] = None

    # Rule 1: Statistical Outlier per account
    if "account_id" in df.columns and "amount" in df.columns:
        for account_id, group in df.groupby("account_id"):
            median = group["amount"].median()
            threshold = 3 * median
            outlier_mask = group["amount"] > threshold
            outlier_indices = group[outlier_mask].index
            df.loc[outlier_indices, "is_anomaly"] = True
            df.loc[outlier_indices, "anomaly_reason"] = "Statistical Outlier"
            if outlier_mask.any():
                logger.info(
                    f"Account {account_id}: median={median:.2f}, threshold={threshold:.2f}, "
                    f"outliers={outlier_mask.sum()}"
                )

    # Rule 2: Domestic Merchant Using USD
    if "merchant" in df.columns and "currency" in df.columns:
        domestic_usd_mask = (
            df["merchant"].str.lower().isin(DOMESTIC_MERCHANTS)
            & (df["currency"] == "USD")
        )
        # Update row by row for matching transactions to prevent NaN string combination issues
        for idx in df[domestic_usd_mask].index:
            df.loc[idx, "is_anomaly"] = True
            existing_reason = df.loc[idx, "anomaly_reason"]
            if existing_reason:
                if "Domestic Merchant Using USD" not in str(existing_reason):
                    df.loc[idx, "anomaly_reason"] = f"{existing_reason}; Domestic Merchant Using USD"
            else:
                df.loc[idx, "anomaly_reason"] = "Domestic Merchant Using USD"

    total_anomalies = df["is_anomaly"].sum()
    logger.info(f"Anomaly detection complete: {total_anomalies} anomalies found")
    return df
