"""
API configuration for the NFL Data Engineering web platform.

Data paths, CORS origins, and versioning are configurable via
environment variables with sensible defaults for local development.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
API_VERSION = "0.1.0"
API_TITLE = "NFL Data Engineering API"

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
# Root of the project (two levels up from this file: web/api/config.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = Path(os.getenv("NFL_DATA_DIR", str(_PROJECT_ROOT / "data")))
GOLD_PROJECTIONS_DIR = DATA_DIR / "gold" / "projections"
GOLD_PREDICTIONS_DIR = DATA_DIR / "gold" / "predictions"
GOLD_SENTIMENT_DIR = DATA_DIR / "gold" / "sentiment"
SILVER_SENTIMENT_DIR = DATA_DIR / "silver" / "sentiment"
BRONZE_SENTIMENT_DIR = DATA_DIR / "bronze" / "sentiment"

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8000",
).split(",")

# ---------------------------------------------------------------------------
# Valid parameter values
# ---------------------------------------------------------------------------
VALID_SCORING_FORMATS = {"ppr", "half_ppr", "standard"}
VALID_POSITIONS = {"QB", "RB", "WR", "TE", "K"}

# ---------------------------------------------------------------------------
# Preseason fallback freshness threshold
# ---------------------------------------------------------------------------
# When a weekly projection parquet for a *current or future* season is missing
# or older than this many days, the weekly endpoint falls back to the preseason
# projections for that season.  Historical seasons (season < current year) are
# never subject to this check — their stale data is intentionally frozen.
#
# 14 days covers a typical bye week + one extra day of buffer.  Adjust here if
# the production publish cadence changes.
WEEKLY_STALENESS_THRESHOLD_DAYS: int = 14
