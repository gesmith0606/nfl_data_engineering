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
from .models.schemas import HealthResponse, VersionResponse
from .routers import (
    draft,
    games,
    lineups,
    news,
    players,
    predictions,
    projections,
    rankings,
    sleeper_user,
    teams,
    teams_defense,
)

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
app.include_router(games.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(draft.router, prefix="/api")
app.include_router(rankings.router, prefix="/api")
app.include_router(sleeper_user.router, prefix="/api")
app.include_router(teams.router, prefix="/api")
app.include_router(teams_defense.router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Liveness probe.  Reports database status when DATABASE_URL is set.

    ``llm_enrichment_ready`` reflects whether ``ANTHROPIC_API_KEY`` is set in
    the runtime environment so the news extractor can run. The value is a
    bool; the key itself is never returned or logged (phase 66 / HOTFIX-01).
    """
    db_status = "connected" if is_db_enabled() and db_health() else "parquet_fallback"
    llm_ready = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        db_status=db_status,
        llm_enrichment_ready=llm_ready,
    )


@app.get("/api/version", response_model=VersionResponse, tags=["health"])
def version_info() -> VersionResponse:
    """Build and git metadata -- proves which code is actually deployed.

    ``git_sha`` is the FULL 40-character RAILWAY_GIT_COMMIT_SHA (no
    truncation) so Phase 84's asymmetry probe can do a clean equality
    check against the 40-char GITHUB_SHA from GitHub Actions
    (Phase 79 D-04).

    ``llm_enrichment_ready`` mirrors /api/health -- True when
    ANTHROPIC_API_KEY is set in the runtime environment. The value is
    a bool; the key itself is never returned or logged
    (Phase 66 / HOTFIX-01, applied here per Phase 79 D-05).

    The two diagnostic route flags
    (``has_team_events_route``, ``has_player_badges_route``) are
    retained from Phase 66 -- they proved their worth catching the
    v7.1 silent-freeze.
    """
    llm_ready = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return VersionResponse(
        version=API_VERSION,
        git_sha=os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown"),
        build_id=os.environ.get("RAILWAY_DEPLOYMENT_ID", "unknown"),
        deployed_at=os.environ.get("RAILWAY_GIT_COMMIT_TIMESTAMP", "unknown"),
        llm_enrichment_ready=llm_ready,
        has_team_events_route=any(
            getattr(r, "path", "") == "/team-events" for r in news.router.routes
        ),
        has_player_badges_route=any(
            "player-badges" in getattr(r, "path", "") for r in news.router.routes
        ),
    )
