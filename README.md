# AI-Powered Transaction Processing Pipeline

A production-grade backend system that ingests CSV transaction files, cleans and validates them, detects anomalies, classifies transactions using Google Gemini Flash, and returns AI-generated spending narratives and risk assessments.

---

## Architecture

```
┌─────────────┐     POST /jobs/upload      ┌──────────────────┐
│   Client    │ ─────────────────────────► │   FastAPI        │
│  (cURL/UI)  │ ◄───────────────────────── │   Backend        │
└─────────────┘     {job_id, status}       │   :8000          │
                                           └────────┬─────────┘
                                                    │ push task
                                                    ▼
                                           ┌──────────────────┐
                                           │   Redis          │
                                           │   (Broker)       │
                                           │   :6379          │
                                           └────────┬─────────┘
                                                    │ consume
                                                    ▼
                                           ┌──────────────────┐
                                           │  Celery Worker   │
                                           │                  │
                                           │  1. Load CSV     │
                                           │  2. Clean Data   │
                                           │  3. Anomalies    │
                                           │  4. LLM Classify │
                                           │  5. LLM Summary  │
                                           │  6. Save to DB   │
                                           └────────┬─────────┘
                                                    │ write
                                                    ▼
                                           ┌──────────────────┐
                                           │   PostgreSQL     │
                                           │   (jobs,         │
                                           │  transactions,   │
                                           │  job_summaries)  │
                                           │   :5432          │
                                           └──────────────────┘
```

---

## Folder Structure

```
intern_project/
├── backend/
│   ├── api/
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── jobs.py          # Job endpoints
│   │   │   └── health.py        # Health check
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── job.py           # Job Pydantic models
│   │       ├── transaction.py   # Transaction Pydantic models
│   │       └── health.py        # Health schema
│   ├── alembic/
│   │   ├── versions/
│   │   │   └── 001_initial_tables.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic Settings config
│   │   └── logging.py           # Structured JSON logging
│   ├── crud/
│   │   ├── __init__.py
│   │   ├── job.py               # Job CRUD operations
│   │   ├── transaction.py       # Transaction CRUD operations
│   │   └── job_summary.py       # JobSummary CRUD operations
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py              # SQLAlchemy Base
│   │   └── session.py           # Async + Sync sessions
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py               # Job ORM model
│   │   ├── transaction.py       # Transaction ORM model
│   │   └── job_summary.py       # JobSummary ORM model
│   ├── services/
│   │   ├── __init__.py
│   │   └── gemini_service.py    # Gemini API integration
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── csv_processor.py     # CSV loading & cleaning
│   │   └── anomaly_detector.py  # Anomaly detection rules
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py        # Celery configuration
│   │   └── tasks.py             # Celery task definition
│   ├── __init__.py
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── main.py                  # FastAPI application
│   └── requirements.txt
├── .env
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## ER Diagram

```
jobs
─────────────────────────────────────────────────────
id              UUID        PK
filename        VARCHAR     NOT NULL
status          ENUM        pending|processing|completed|failed
row_count_raw   INTEGER
row_count_clean INTEGER
created_at      TIMESTAMPTZ NOT NULL
completed_at    TIMESTAMPTZ
error_message   TEXT

transactions
─────────────────────────────────────────────────────
id              UUID        PK
job_id          UUID        FK → jobs.id (CASCADE DELETE)
txn_id          VARCHAR
date            DATE
merchant        VARCHAR
amount          FLOAT
currency        VARCHAR
status          VARCHAR
category        VARCHAR
account_id      VARCHAR
notes           TEXT
is_anomaly      BOOLEAN     NOT NULL
anomaly_reason  VARCHAR
llm_category    VARCHAR
llm_failed      BOOLEAN     NOT NULL

job_summaries
─────────────────────────────────────────────────────
id              UUID        PK
job_id          UUID        FK → jobs.id (CASCADE DELETE) UNIQUE
total_spend_inr FLOAT
total_spend_usd FLOAT
top_merchants   JSONB
anomaly_count   INTEGER     NOT NULL
narrative       TEXT
risk_level      VARCHAR
```

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) >= 24.0
- [Docker Compose](https://docs.docker.com/compose/) >= 2.0
- A [Google AI Studio](https://aistudio.google.com/) API key (Gemini Flash)

---

## Quick Start

### 1. Clone and Configure

```bash
git clone <your-repo-url>
cd intern_project

# Copy environment template and add your Gemini API key
cp .env.example .env
nano .env   # Set GEMINI_API_KEY=your_actual_key
```

### 2. Start All Services

```bash
docker compose up --build
```

This command will:
1. Build the Docker images for `backend` and `worker`
2. Start PostgreSQL, Redis, FastAPI backend, and Celery worker
3. Run Alembic migrations automatically
4. Expose the API at `http://localhost:8000`

### 3. Verify Everything Is Running

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "app": "AI Transaction Processing Pipeline",
  "version": "1.0.0",
  "environment": "production"
}
```

---

## API Documentation

Interactive Swagger UI available at: **http://localhost:8000/docs**

ReDoc documentation at: **http://localhost:8000/redoc**

---

## API Endpoints

### `POST /jobs/upload`
Upload a CSV file containing transaction data to create a processing job.

**Request:**
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv"
```

**Sample Response (202 Accepted):**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "message": "Job created and queued for processing"
}
```

---

### `GET /jobs/{job_id}/status`
Poll the status of a processing job.

**Request:**
```bash
curl http://localhost:8000/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/status
```

**Sample Response (completed):**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "filename": "transactions.csv",
  "status": "completed",
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:30:45Z",
  "row_count_raw": 500,
  "row_count_clean": 487,
  "processing_time_seconds": 45.2,
  "summary": {
    "total_spend_inr": 125000.50,
    "total_spend_usd": 1500.00,
    "top_merchants": {
      "Amazon": 25000.00,
      "Swiggy": 8500.00,
      "IRCTC": 6200.00
    },
    "anomaly_count": 12,
    "narrative": "The account shows high spending on e-commerce platforms with 12 flagged anomalies. Several transactions indicate potential unauthorized USD charges from domestic merchants.",
    "risk_level": "medium"
  }
}
```

---

### `GET /jobs/{job_id}/results`
Get the full results for a completed job.

**Request:**
```bash
curl http://localhost:8000/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/results
```

**Sample Response:**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "transactions": [
    {
      "id": "a1b2c3d4-...",
      "txn_id": "TXN001",
      "date": "2024-01-10",
      "merchant": "Amazon",
      "amount": 2500.00,
      "currency": "INR",
      "status": "COMPLETED",
      "category": "Shopping",
      "account_id": "ACC001",
      "notes": "Electronics purchase",
      "is_anomaly": false,
      "anomaly_reason": null,
      "llm_category": "Shopping",
      "llm_failed": false
    }
  ],
  "anomalies": [
    {
      "id": "b2c3d4e5-...",
      "txn_id": "TXN042",
      "merchant": "Swiggy",
      "amount": 150.00,
      "currency": "USD",
      "anomaly_reason": "Domestic Merchant Using USD"
    }
  ],
  "category_spend": [
    {"category": "Shopping", "total_amount": 45000.00, "transaction_count": 23},
    {"category": "Food", "total_amount": 12500.00, "transaction_count": 67},
    {"category": "Transport", "total_amount": 8200.00, "transaction_count": 34}
  ],
  "narrative": "Spending is concentrated in shopping and food categories with elevated anomaly count suggesting review.",
  "risk_level": "medium"
}
```

---

### `GET /jobs`
List all jobs with optional filtering and pagination.

**Request:**
```bash
# List all jobs
curl "http://localhost:8000/jobs"

# Filter by status
curl "http://localhost:8000/jobs?status=completed"

# With pagination
curl "http://localhost:8000/jobs?page=1&page_size=10&status=completed"
```

**Sample Response:**
```json
{
  "items": [
    {
      "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "filename": "transactions.csv",
      "status": "completed",
      "row_count_raw": 500,
      "row_count_clean": 487,
      "created_at": "2024-01-15T10:30:00Z",
      "completed_at": "2024-01-15T10:30:45Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

---

### `GET /health`
Service health check.

```bash
curl http://localhost:8000/health
```

---

## CSV Format

The system accepts CSV files with the following columns (column names are case-insensitive and flexible):

| Column | Required | Description |
|--------|----------|-------------|
| `txn_id` / `transaction_id` | No | Transaction ID (auto-generated if missing) |
| `date` / `transaction_date` | Yes | Date in DD-MM-YYYY, YYYY/MM/DD, or YYYY-MM-DD |
| `merchant` / `vendor` | Yes | Merchant name |
| `amount` / `amt` | Yes | Amount ($ prefix is stripped automatically) |
| `currency` / `curr` | Yes | Currency code (INR, USD, etc.) |
| `status` | No | Transaction status |
| `category` | No | Category (filled as 'Uncategorised' if blank) |
| `account_id` / `account` | No | Account identifier |
| `notes` | No | Additional notes |

**Sample CSV:**
```csv
txn_id,date,merchant,amount,currency,status,category,account_id,notes
TXN001,15-01-2024,Amazon,$2500.00,INR,completed,Shopping,ACC001,Electronics
TXN002,2024/01/16,Swiggy,450,INR,completed,,ACC001,Food delivery
TXN003,17-01-2024,Swiggy,$150.00,USD,completed,Food,ACC001,Suspicious charge
```

---

## Docker Commands

```bash
# Start all services
docker compose up --build

# Start in background
docker compose up --build -d

# Stop all services
docker compose down

# Stop and remove volumes (clean slate)
docker compose down -v

# View logs
docker compose logs -f
docker compose logs -f backend
docker compose logs -f worker

# Scale workers
docker compose up --scale worker=3 -d

# Run migrations manually
docker compose exec backend alembic upgrade head

# Check service health
docker compose ps
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `postgres` | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `transactions_db` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | *(blank for local Docker Compose)* | Database password |
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Celery result backend |
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model to use |
| `GEMINI_BATCH_SIZE` | `20` | Rows per LLM batch |
| `GEMINI_MAX_RETRIES` | `3` | LLM retry attempts |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max CSV upload size |
| `DEBUG` | `false` | Enable debug mode |

---

## Processing Pipeline

```
CSV Upload
    │
    ▼
Validation (extension, size, content)
    │
    ▼
Job created in PostgreSQL (status=pending)
    │
    ▼
Celery task dispatched → Redis queue
    │
    ▼
┌─────────────────────────────────────┐
│          Celery Worker              │
│                                     │
│  1. Load CSV with Pandas            │
│  2. Normalize dates (multi-format)  │
│  3. Strip $ from amounts            │
│  4. Uppercase status/currency       │
│  5. Fill blank categories           │
│  6. Generate UUID for blank IDs     │
│  7. Remove duplicates               │
│                                     │
│  Anomaly Detection:                 │
│  ├── Rule 1: >3× account median     │
│  └── Rule 2: Domestic USD charges   │
│                                     │
│  LLM Categorisation (Gemini):       │
│  ├── Batch uncategorised rows (×20) │
│  ├── Exponential backoff (3 tries)  │
│  └── Mark llm_failed if all fail    │
│                                     │
│  LLM Summary (Gemini):              │
│  ├── Total spend per currency       │
│  ├── Top 3 merchants                │
│  ├── Anomaly count                  │
│  ├── 2-sentence narrative           │
│  └── Risk level (low/medium/high)   │
│                                     │
│  Persist to PostgreSQL              │
│  Update job status=completed        │
└─────────────────────────────────────┘
```

---

## Project Assumptions

1. **CSV Flexibility**: The system handles multiple common column names and date formats without requiring a rigid schema.
2. **Duplicate Handling**: Rows with duplicate `txn_id` values are deduplicated (first occurrence kept).
3. **LLM Batching**: Gemini API is called in batches of 20 rows — never per-row — to minimise latency and cost.
4. **Graceful Degradation**: If the Gemini API fails after 3 retries, the pipeline continues with `llm_failed=True` rather than failing the entire job.
5. **Currency Handling**: Amounts are stored as raw floats. The system tracks INR and USD separately in the summary.
6. **Anomaly Rules**: Both rules can fire simultaneously; the reasons are concatenated.
7. **File Storage**: Uploaded files are stored temporarily and deleted after processing.
8. **No Authentication**: The API is unauthenticated by design for this project. In production, add OAuth2/JWT.
9. **Celery Concurrency**: The worker runs with 4 concurrent processes by default. Adjust via `--concurrency` flag.
10. **Migration Safety**: Alembic migrations run on startup with `alembic upgrade head`, which is idempotent.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Database | PostgreSQL 15 |
| Cache/Broker | Redis 7 |
| Task Queue | Celery 5.4 |
| Data Processing | Pandas 2.2 |
| AI/LLM | Google Gemini Flash |
| Validation | Pydantic v2 |
| Containerisation | Docker + Docker Compose |
| Logging | Structured JSON |

---

## License

MIT License — built for demonstration and educational purposes.
```
