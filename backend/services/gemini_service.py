import json
import time
import re
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

LLM_CATEGORIES = [
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Entertainment",
    "Cash Withdrawal",
    "Other",
]


def is_gemini_configured() -> bool:
    """Check if the Gemini API key is configured with a real value."""
    key = settings.GEMINI_API_KEY
    if not key or key.strip() == "" or "your_gemini_api" in key.lower():
        return False
    return True


def _get_client() -> genai.Client:
    """Create and return a Gemini client."""
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _call_gemini_with_retry(client: genai.Client, prompt: str) -> str:
    """
    Call Gemini with exponential backoff retry on failure.
    Raises the last exception if all retries fail.
    """
    last_exc = None
    for attempt in range(settings.GEMINI_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                ),
            )
            return response.text
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            logger.warning(
                f"Gemini call failed (attempt {attempt + 1}/{settings.GEMINI_MAX_RETRIES}): {exc}. "
                f"Retrying in {wait}s..."
            )
            time.sleep(wait)
    raise last_exc


def _mock_categorize_row(row: Dict[str, Any]) -> str:
    """Helper to mock categorisation based on merchant/notes when LLM is unavailable."""
    merchant = str(row.get("merchant") or "").lower()
    notes = str(row.get("notes") or "").lower()

    if any(k in merchant or k in notes for k in ["swiggy", "restaurant", "food", "zomato", "cafe", "diner"]):
        return "Food"
    if any(k in merchant or k in notes for k in ["amazon", "flipkart", "shopping", "store", "supermarket", "grocery"]):
        return "Shopping"
    if any(k in merchant or k in notes for k in ["irctc", "travel", "flight", "hotel", "makemytrip", "airline"]):
        return "Travel"
    if any(k in merchant or k in notes for k in ["ola", "uber", "transport", "cab", "taxi", "metro"]):
        return "Transport"
    if any(k in merchant or k in notes for k in ["electricity", "water", "gas", "utility", "bill", "power"]):
        return "Utilities"
    if any(k in merchant or k in notes for k in ["netflix", "cinema", "entertainment", "movie", "spotify", "show"]):
        return "Entertainment"
    if any(k in merchant or k in notes for k in ["atm", "withdrawal", "cash"]):
        return "Cash Withdrawal"
    return "Other"


def categorize_transactions_batch(
    transactions: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Categorize a batch of transactions using Gemini (or fallback rule-based matching if not configured).
    Returns a dict mapping txn_id -> {"category": str, "raw_response": str}.
    """
    if not transactions:
        return {}

    if not is_gemini_configured():
        logger.warning("GEMINI_API_KEY not configured. Falling back to rule-based mock categorisation.")
        return {
            t["txn_id"]: {
                "category": _mock_categorize_row(t),
                "raw_response": f"Mock Rule-Based Classification: {_mock_categorize_row(t)}",
            }
            for t in transactions
        }

    client = _get_client()
    results: Dict[str, Dict[str, Any]] = {}
    batch_size = settings.GEMINI_BATCH_SIZE
    batches = [transactions[i: i + batch_size] for i in range(0, len(transactions), batch_size)]

    categories_str = ", ".join(LLM_CATEGORIES)

    for batch_idx, batch in enumerate(batches):
        logger.info(f"LLM categorisation: batch {batch_idx + 1}/{len(batches)} ({len(batch)} rows)")
        rows_text = "\n".join(
            f"{i + 1}. txn_id={row['txn_id']} | merchant={row.get('merchant', 'N/A')} | "
            f"amount={row.get('amount', 'N/A')} {row.get('currency', '')} | notes={row.get('notes', 'N/A')}"
            for i, row in enumerate(batch)
        )
        prompt = (
            f"You are a financial transaction categoriser. "
            f"Classify each transaction into exactly one of these categories: {categories_str}.\n\n"
            f"Transactions:\n{rows_text}\n\n"
            f"Respond ONLY with a valid JSON object mapping txn_id to category. Example:\n"
            f'{{"txn_001": "Food", "txn_002": "Travel"}}\n'
            f"Do not add any explanation."
        )
        try:
            raw = _call_gemini_with_retry(client, prompt)
            # Strip markdown fences if present
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            batch_result = json.loads(raw)
            for txn in batch:
                tid = txn["txn_id"]
                cat = batch_result.get(tid)
                results[tid] = {
                    "category": cat if cat in LLM_CATEGORIES else "Other",
                    "raw_response": str(cat) if cat else "Other",
                }
        except Exception as exc:
            logger.error(f"Gemini batch {batch_idx + 1} failed after retries: {exc}")
            for txn in batch:
                fallback_category = _mock_categorize_row(txn)
                results[txn["txn_id"]] = {
                    "category": fallback_category,
                    "raw_response": f"Gemini categorisation failed; fallback={fallback_category}",
                    "llm_failed": True,
                }

    return results


def generate_job_summary(summary_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a final LLM-powered narrative and risk assessment for the processed job.
    Returns a dict with narrative and risk_level keys.
    """
    if not is_gemini_configured():
        logger.warning("GEMINI_API_KEY not configured. Returning default summary mock.")
        anomaly_count = summary_data.get("anomaly_count", 0)
        return {
            "total_spend_per_currency": summary_data.get("spend_by_currency", {}),
            "top_3_merchants": summary_data.get("top_merchants", [])[:3],
            "anomaly_count": anomaly_count,
            "narrative": f"Automated analysis processed {summary_data.get('total_transactions', 0)} transactions. "
                         f"Found {anomaly_count} potential anomalies in the spending patterns.",
            "risk_level": "high" if anomaly_count > 5 else ("medium" if anomaly_count > 0 else "low"),
        }

    client = _get_client()
    prompt = (
        f"You are a senior financial analyst AI. Analyse the following transaction data and provide a summary.\n\n"
        f"Transaction Data:\n{json.dumps(summary_data, indent=2, default=str)}\n\n"
        f"Respond ONLY with a valid JSON object with these exact fields:\n"
        f"{{\n"
        f'  "total_spend_per_currency": {{"INR": 0.0, "USD": 0.0}},\n'
        f'  "top_3_merchants": ["merchant1", "merchant2", "merchant3"],\n'
        f'  "anomaly_count": 0,\n'
        f'  "narrative": "2 sentence spending narrative here.",\n'
        f'  "risk_level": "low|medium|high"\n'
        f"}}\n"
        f"risk_level must be one of: low, medium, high based on anomaly count and spending patterns.\n"
        f"narrative must be exactly 2 sentences."
    )
    try:
        raw = _call_gemini_with_retry(client, prompt)
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        result = json.loads(raw)
        return result
    except Exception as exc:
        logger.error(f"Gemini job summary failed: {exc}")
        anomaly_count = summary_data.get("anomaly_count", 0)
        top_merchants = summary_data.get("top_merchants", [])[:3]
        top_text = ", ".join(top_merchants) if top_merchants else "available merchants"
        risk_level = "high" if anomaly_count > 5 else ("medium" if anomaly_count > 0 else "low")
        return {
            "total_spend_per_currency": summary_data.get("spend_by_currency", {}),
            "top_3_merchants": summary_data.get("top_merchants", [])[:3],
            "anomaly_count": anomaly_count,
            "narrative": f"Automated analysis processed {summary_data.get('total_transactions', 0)} transactions with highest spend around {top_text}. The job flagged {anomaly_count} potential anomalies, giving this file a {risk_level} risk level.",
            "risk_level": risk_level,
        }
