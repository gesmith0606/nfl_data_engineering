"""Data freshness monitoring endpoint.

Scans local data directories for newest artifacts and reports age in hours.
Supports pytest fixture override for testability.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

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
        Path of the newest file by generation time (filename timestamp when
        present, else mtime), or None if no files found.
    """
    if not pattern_dir.exists():
        return None

    files = list(pattern_dir.rglob("*.parquet"))
    if not files:
        return None

    return max(files, key=lambda f: artifact_time(f).timestamp())


def file_mtime(path: Path) -> datetime:
    """Return a file's modification time as a UTC datetime."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def artifact_time(path: Path) -> datetime:
    """Return a file's generation time as a UTC datetime.

    Prefers the ``_YYYYMMDD_HHMMSS`` timestamp embedded in pipeline
    filenames — git checkouts reset mtimes to clone time, so mtime alone
    reports everything fresh right after any deploy. Falls back to mtime
    for files without an embedded timestamp.
    """
    embedded = extract_timestamp_from_filename(path.name)
    return embedded if embedded is not None else file_mtime(path)


def _rankings_time(path: Path) -> datetime:
    """Return a rankings JSON's generation time as a UTC datetime.

    External rankings snapshots have stable filenames (no embedded
    timestamp) but carry a ``fetched_at`` ISO field; prefer it over mtime
    for the same git-checkout reason as :func:`artifact_time`.
    """
    import json

    try:
        with open(path) as fh:
            fetched_at = json.load(fh).get("fetched_at")
        if fetched_at:
            dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, AttributeError):
        pass
    return file_mtime(path)


def extract_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extract YYYYMMDD_HHMMSS timestamp from filename.

    Pattern: *_YYYYMMDD_HHMMSS.<ext>

    Args:
        filename: The filename to parse.

    Returns:
        Parsed datetime, or None if pattern not found.
    """
    import re

    match = re.search(r"_(\d{8})_(\d{6})\.[A-Za-z0-9]+$", filename)
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


# ---------------------------------------------------------------------------
# Config-table driven freshness logic
# ---------------------------------------------------------------------------

_PRESEASON_H: float = 168.0  # 7 days
_IN_SEASON_H: float = 26.0   # ~1 day + buffer


class _DatasetConfig:
    """Descriptor for a single dataset's scan path and staleness rules.

    Args:
        name: Dataset name (matches FreshnessResponse field).
        rel_path: Path components relative to data root.
        kind: ``"parquet"`` (recursive parquet scan) or ``"rankings_json"``
            (glob ``*_rankings.json``, prefer ``fetched_at`` for age).
        in_season_threshold: Staleness threshold in hours during NFL season;
            ``None`` means non-blocking in-season.
        preseason_threshold: Staleness threshold in hours off-season;
            ``None`` means non-blocking off-season.
        blocking: When ``True`` this dataset's stale flag is included in
            ``overall_stale``.
    """

    __slots__ = (
        "name",
        "rel_path",
        "kind",
        "in_season_threshold",
        "preseason_threshold",
        "blocking",
    )

    def __init__(
        self,
        name: str,
        rel_path: Tuple[str, ...],
        kind: str,
        in_season_threshold: Optional[float],
        preseason_threshold: Optional[float],
        blocking: bool,
    ) -> None:
        self.name = name
        self.rel_path = rel_path
        self.kind = kind
        self.in_season_threshold = in_season_threshold
        self.preseason_threshold = preseason_threshold
        self.blocking = blocking


#: Ordered list of datasets to scan. Order matches FreshnessResponse fields.
_DATASET_CONFIGS: List[_DatasetConfig] = [
    _DatasetConfig(
        "projections",
        ("gold", "projections"),
        "parquet",
        _IN_SEASON_H,
        _PRESEASON_H,
        True,
    ),
    _DatasetConfig(
        "predictions",
        ("gold", "predictions"),
        "parquet",
        _IN_SEASON_H,
        None,  # non-blocking off-season
        True,
    ),
    _DatasetConfig(
        "rankings",
        ("external",),
        "rankings_json",
        _PRESEASON_H,  # always 7-day threshold (weekly cadence)
        _PRESEASON_H,
        True,
    ),
    _DatasetConfig(
        "odds",
        ("bronze", "odds_api", "snapshots"),
        "parquet",
        _IN_SEASON_H,
        None,  # non-blocking off-season
        False,
    ),
    _DatasetConfig(
        "sentiment",
        ("gold", "sentiment"),
        "parquet",
        _IN_SEASON_H,
        None,  # non-blocking off-season
        False,
    ),
]


def _is_stale(age: Optional[float], threshold: Optional[float]) -> bool:
    """Return True if the dataset is stale or absent.

    A ``None`` threshold means non-blocking — always returns ``False``
    regardless of age.

    Args:
        age: Age in hours of the newest artifact, or ``None`` when no data.
        threshold: Staleness threshold in hours, or ``None`` for non-blocking.

    Returns:
        ``True`` when stale or missing; ``False`` when fresh or non-blocking.
    """
    if threshold is None:
        return False
    return age is None or age > threshold


def _check_dataset(config: _DatasetConfig, data_root: Path, in_season: bool) -> FreshDataset:
    """Compute freshness for a single dataset from its config.

    Args:
        config: Dataset descriptor (path, kind, thresholds).
        data_root: Root of the local data directory tree.
        in_season: Whether the NFL season is currently active.

    Returns:
        ``FreshDataset`` with age, stale flag, and newest-file name.
    """
    threshold = config.in_season_threshold if in_season else config.preseason_threshold

    if config.kind == "rankings_json":
        rankings_dir = data_root.joinpath(*config.rel_path)
        newest: Optional[Path] = None
        if rankings_dir.exists():
            files = [f for f in rankings_dir.glob("*_rankings.json") if f.is_file()]
            if files:
                newest = max(files, key=lambda f: f.stat().st_mtime)
        age: Optional[float] = age_in_hours(_rankings_time(newest)) if newest else None
    else:
        path = data_root.joinpath(*config.rel_path)
        newest = find_newest_file(path)
        age = age_in_hours(artifact_time(newest)) if newest else None

    return FreshDataset(
        age_hours=age,
        stale=_is_stale(age, threshold),
        newest_file=newest.name if newest else None,
    )


def get_freshness() -> FreshnessResponse:
    """Scan data/ and return freshness status."""
    data_root = get_data_root()
    now = datetime.now(tz=timezone.utc)
    in_season = is_in_season()

    results = {
        cfg.name: _check_dataset(cfg, data_root, in_season)
        for cfg in _DATASET_CONFIGS
    }

    overall_stale = any(
        results[cfg.name].stale for cfg in _DATASET_CONFIGS if cfg.blocking
    )

    return FreshnessResponse(
        projections=results["projections"],
        predictions=results["predictions"],
        rankings=results["rankings"],
        odds=results["odds"],
        sentiment=results["sentiment"],
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
