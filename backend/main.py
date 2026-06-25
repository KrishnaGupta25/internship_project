import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.core.config import settings
from backend.core.logging import setup_logging, get_logger
from backend.api.routers.jobs import router as jobs_router
from backend.api.routers.health import router as health_router

setup_logging("DEBUG" if settings.DEBUG else "INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield
    logger.info("Shutting down application")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AI-Powered Transaction Processing Pipeline

This API provides an end-to-end pipeline for:
- **Uploading** transaction CSV files
- **Processing** and cleaning data using Pandas
- **Detecting anomalies** via statistical rules
- **Categorising** transactions using Google Gemini 1.5 Flash
- **Summarising** spending patterns with AI-generated narratives

### Key Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/jobs/upload` | Upload CSV and create processing job |
| `GET` | `/jobs/{job_id}/status` | Poll job status |
| `GET` | `/jobs/{job_id}/results` | Get full results |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/health` | Health check |
    """,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )


# Include routers
app.include_router(health_router)
app.include_router(jobs_router)
