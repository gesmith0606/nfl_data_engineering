"""
NFL Data Engineering API -- FastAPI application entry point.

Run locally with:
    uvicorn web.api.main:app --reload --host 0.0.0.0 --port 8000
"""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import API_TITLE, API_VERSION, CORS_ORIGINS
from .db import check_health as db_health, is_db_enabled
from .models.schemas import HealthResponse
from .routers import lineups, players, predictions, projections

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS -- allow Next.js dev server and any configured origins
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Key Authentication Middleware
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "")

# Paths that skip authentication
_AUTH_EXEMPT_PATHS = {"/api/health", "/api/docs", "/api/openapi.json"}


@app.middleware("http")
async def api_key_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Validate X-API-Key header when API_KEY env var is set.

    - If API_KEY is not set (empty), all requests pass through (dev mode).
    - Health, docs, and OpenAPI endpoints are always exempt.
    """
    if API_KEY and request.url.path not in _AUTH_EXEMPT_PATHS:
        provided = request.headers.get("X-API-Key", "")
        if provided != API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(projections.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(lineups.router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Liveness probe.  Reports database status when DATABASE_URL is set."""
    db_status = "connected" if is_db_enabled() and db_health() else "parquet_fallback"
    return HealthResponse(status="ok", version=API_VERSION, db_status=db_status)
