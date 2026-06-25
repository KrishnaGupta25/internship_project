# System Design Diagram

```mermaid
flowchart LR
    Client["Client / Reviewer<br/>curl or Swagger UI"]
    API["FastAPI Backend<br/>POST /jobs/upload<br/>GET /jobs/{id}/status<br/>GET /jobs/{id}/results<br/>GET /jobs"]
    DB[("PostgreSQL<br/>jobs<br/>transactions<br/>job_summaries")]
    Redis[("Redis<br/>Celery broker<br/>result backend")]
    Worker["Celery Worker<br/>CSV cleaning<br/>anomaly detection<br/>LLM classification<br/>summary generation"]
    Gemini["Google Gemini API<br/>batched classification<br/>narrative summary"]
    Volume[("Shared upload volume<br/>/tmp/uploads")]

    Client -->|"1. Upload CSV"| API
    API -->|"2. Create Job: pending"| DB
    API -->|"3. Save temporary CSV"| Volume
    API -->|"4. Enqueue job_id + file path"| Redis
    API -->|"5. Return job_id immediately"| Client

    Redis -->|"6. Dequeue task"| Worker
    Volume -->|"7. Read CSV"| Worker
    Worker -->|"8. Update status: processing"| DB
    Worker -->|"9. Clean rows, normalize dates/status/currency, remove duplicates"| Worker
    Worker -->|"10. Detect anomalies"| Worker
    Worker -->|"11. Batch uncategorised rows"| Gemini
    Gemini -->|"12. Categories / summary JSON"| Worker
    Worker -->|"13. Persist cleaned data + summary"| DB
    Worker -->|"14. Update status: completed or failed"| DB

    Client -->|"15. Poll status / fetch results"| API
    API -->|"16. Read job, transactions, summary"| DB
    API -->|"17. Return structured output"| Client
```

## Request Lifecycle

1. The reviewer uploads `transactions.csv` to `POST /jobs/upload`.
2. FastAPI validates the file, stores it temporarily, creates a `jobs` row with `pending` status, and pushes a Celery task to Redis.
3. The Celery worker dequeues the job, marks it `processing`, loads the CSV, cleans dirty values, removes duplicates, and detects anomalies.
4. Missing categories are sent to Gemini in batches, not one request per row.
5. The worker asks Gemini for a summary JSON, then persists cleaned transactions and the job summary in PostgreSQL.
6. The reviewer polls `/jobs/{job_id}/status` and retrieves `/jobs/{job_id}/results` once completed.

## Scale Notes

- At 100x traffic, pressure points are upload disk I/O, Celery queue depth, PostgreSQL connection pool limits, and Gemini API rate limits.
- Next iteration: object storage for uploads, horizontally scaled workers, managed Redis/PostgreSQL, idempotent task retries, LLM rate-limit backoff queues, and API authentication.
