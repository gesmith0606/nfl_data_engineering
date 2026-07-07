"""Data freshness monitoring endpoint.

Scans local data directories for newest artifacts and reports age in hours.
Supports pytest fixture override for testability.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

# Allow tests to override the data root via environment variable or fixture
_DATA_ROOT: Optional[Path] = None


def set_data_root(root: Optional[Path]) -> None:
    """Override data root for testing."""
    global _DATA_ROOT
    _DATA_ROOT = root


def get_data_root() -> Path:
    """Get the data root directory, with test override support."""
    if _DATA_ROOT:
        return _DATA_ROOT
    return Path("data")


def find_newest_file(pattern_dir: Path) -> Optional[Path]:
    """Find the newest file in a directory pattern (e.g. data/gold/projections/**/*.parquet).

    Args:
        pattern_dir: Directory to search recursively.

    Returns:
        Path of the newest file by modification time, or None if no files found.
    """
    if not pattern_dir.exists():
        return None

    files = list(pattern_dir.rglob("*.parquet"))
    if not files:
        return None

    return max(files, key=lambda f: f.stat().st_mtime)


def file_mtime(path: Path) -> datetime:
    """Return a file's modification time as a UTC datetime."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def extract_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extract YYYYMMDD_HHMMSS timestamp from filename.

    Pattern: *_YYYYMMDD_HHMMSS.parquet

    Args:
        filename: The filename to parse.

    Returns:
        Parsed datetime, or None if pattern not found.
    """
    import re

    match = re.search(r"_(\d{8})_(\d{6})\.parquet$", filename)
    if not match:
        return None

    date_str, time_str = match.groups()
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H%M%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def age_in_hours(dt: datetime) -> float:
    """Calculate age of a datetime in hours from now."""
    now = datetime.now(tz=timezone.utc)
    delta = now - dt
    return delta.total_seconds() / 3600


class FreshDataset(BaseModel):
    """Freshness status of a single dataset."""

    age_hours: Optional[float] = Field(
        None, description="Hours since newest artifact. None if no data."
    )
    stale: bool = Field(
        description="True if age exceeds threshold or no data exists."
    )
    newest_file: Optional[str] = Field(None, description="Path/name of newest file.")


class FreshnessResponse(BaseModel):
    """Data freshness status across all datasets."""

    projections: FreshDataset = Field(description="Fantasy projections freshness.")
    predictions: FreshDataset = Field(description="Game predictions freshness.")
    rankings: FreshDataset = Field(description="External rankings freshness.")
    odds: FreshDataset = Field(description="Live odds captures freshness.")
    sentiment: FreshDataset = Field(description="Sentiment signals freshness.")
    overall_stale: bool = Field(
        description="True if any BLOCKING dataset is stale."
    )
    generated_at: str = Field(description="ISO 8601 timestamp of this report.")


def is_in_season() -> bool:
    """Check if we are currently in NFL season.

    NFL season runs September 1 - February 15 (roughly).
    """
    now = datetime.now()
    if now.month >= 9 or now.month == 1:
        return True
    return now.month == 2 and now.day <= 15


def get_freshness() -> FreshnessResponse:
    """Scan data/ and return freshness status."""
    data_root = get_data_root()
    now = datetime.now(tz=timezone.utc)

    # Thresholds (hours)
    preseason_threshold = 168  # 7 days
    in_season_threshold = 26  # ~1 day + buffer
    in_season = is_in_season()

    # Determine thresholds for each dataset
    proj_threshold = in_season_threshold if in_season else preseason_threshold
    pred_threshold = in_season_threshold if in_season else preseason_threshold
    rankings_threshold = preseason_threshold  # Always weekly
    odds_threshold = in_season_threshold if in_season else None  # None = non-blocking
    sentiment_threshold = in_season_threshold if in_season else None  # None = non-blocking

    # Scan projections: data/gold/projections/season=*/week=*/*.parquet
    proj_newest = find_newest_file(data_root / "gold" / "projections")
    proj_age = age_in_hours(file_mtime(proj_newest)) if proj_newest else None
    proj_stale = (
        proj_age is None
        or proj_age > proj_threshold
        if proj_threshold
        else False
    )

    # Scan predictions: data/gold/predictions/season=*/week=*/*.parquet
    pred_newest = find_newest_file(data_root / "gold" / "predictions")
    pred_age = age_in_hours(file_mtime(pred_newest)) if pred_newest else None
    pred_stale = (
        pred_age is None or pred_age > pred_threshold
        if pred_threshold
        else False
    )

    # Scan rankings: data/external/*_rankings.json
    rankings_dir = data_root / "external"
    rankings_newest = None
    if rankings_dir.exists():
        ranking_files = [
            f
            for f in rankings_dir.glob("*_rankings.json")
            if f.is_file()
        ]
        if ranking_files:
            rankings_newest = max(ranking_files, key=lambda f: f.stat().st_mtime)

    rankings_age = age_in_hours(file_mtime(rankings_newest)) if rankings_newest else None
    rankings_stale = rankings_age is None or rankings_age > rankings_threshold

    # Scan odds: data/bronze/odds_api/snapshots/odds_*.parquet
    odds_newest = find_newest_file(
        data_root / "bronze" / "odds_api" / "snapshots"
    )
    odds_age = age_in_hours(file_mtime(odds_newest)) if odds_newest else None
    odds_stale = False
    if odds_threshold is not None:
        odds_stale = odds_age is None or odds_age > odds_threshold

    # Scan sentiment: data/gold/sentiment/season=*/week=*/*.parquet
    sentiment_newest = find_newest_file(data_root / "gold" / "sentiment")
    sentiment_age = (
        age_in_hours(file_mtime(sentiment_newest)) if sentiment_newest else None
    )
    sentiment_stale = False
    if sentiment_threshold is not None:
        sentiment_stale = sentiment_age is None or sentiment_age > sentiment_threshold

    # Overall stale = any BLOCKING dataset stale
    # Non-blocking (None threshold) = always False
    overall_stale = proj_stale or pred_stale or rankings_stale

    return FreshnessResponse(
        projections=FreshDataset(
            age_hours=proj_age,
            stale=proj_stale,
            newest_file=(
                proj_newest.name
                if proj_newest
                else None
            ),
        ),
        predictions=FreshDataset(
            age_hours=pred_age,
            stale=pred_stale,
            newest_file=(
                pred_newest.name
                if pred_newest
                else None
            ),
        ),
        rankings=FreshDataset(
            age_hours=rankings_age,
            stale=rankings_stale,
            newest_file=(
                rankings_newest.name
                if rankings_newest
                else None
            ),
        ),
        odds=FreshDataset(
            age_hours=odds_age,
            stale=odds_stale,
            newest_file=(
                odds_newest.name
                if odds_newest
                else None
            ),
        ),
        sentiment=FreshDataset(
            age_hours=sentiment_age,
            stale=sentiment_stale,
            newest_file=(
                sentiment_newest.name
                if sentiment_newest
                else None
            ),
        ),
        overall_stale=overall_stale,
        generated_at=now.isoformat(),
    )


@router.get("/health/freshness", response_model=FreshnessResponse, tags=["health"])
def freshness_check() -> FreshnessResponse:
    """Data freshness monitoring endpoint.

    Returns age (in hours) and staleness status for:
    - Fantasy projections (threshold: 7d preseason, 26h in-season)
    - Game predictions (threshold: 7d preseason, 26h in-season)
    - External rankings (threshold: 7d always)
    - Live odds (threshold: 26h in-season; non-blocking off-season)
    - Sentiment signals (threshold: 26h in-season; non-blocking off-season)

    ``overall_stale`` is True if any BLOCKING dataset exceeds its threshold.

    In-season = September 1 - February 15.
    """
    return get_freshness()
