"""
Configuration settings for the NFL Data Engineering Pipeline
"""
import datetime
import os
from typing import Callable, Dict, Any, Tuple

# AWS S3 Configuration - Updated with your specific buckets
S3_BUCKET_BRONZE = os.getenv("S3_BUCKET_BRONZE", "nfl-raw")
S3_BUCKET_SILVER = os.getenv("S3_BUCKET_SILVER", "nfl-refined")
S3_BUCKET_GOLD = os.getenv("S3_BUCKET_GOLD", "nfl-trusted")
S3_REGION = os.getenv("AWS_REGION", "us-east-2")

# S3 Paths following medallion architecture with separate buckets
S3_PATHS = {
    "bronze": f"s3://{S3_BUCKET_BRONZE}/",
    "silver": f"s3://{S3_BUCKET_SILVER}/",
    "gold": f"s3://{S3_BUCKET_GOLD}/"
}

# NFL Data Configuration
DEFAULT_SEASON = 2024
DEFAULT_WEEK = 1

# Seasons available for player projection training data (5 seasons)
PLAYER_DATA_SEASONS = list(range(2020, 2026))

# Databricks Configuration - Updated with your workspace
DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID")
DATABRICKS_WORKSPACE_URL = os.getenv("DATABRICKS_WORKSPACE_URL", "https://dbc-c9b1be11-c0c8.cloud.databricks.com")

# Data Quality Thresholds
DATA_QUALITY_THRESHOLDS = {
    "min_games_per_week": 16,  # NFL has 16-17 games per week typically
    "max_null_percentage": 0.1,  # Max 10% null values allowed
    "min_teams_per_game": 2  # Each game must have exactly 2 teams
}

# Fantasy Football Scoring Configurations
SCORING_CONFIGS: Dict[str, Dict[str, float]] = {
    "ppr": {
        "reception": 1.0,
        "rush_yd": 0.1,
        "rec_yd": 0.1,
        "rush_td": 6.0,
        "rec_td": 6.0,
        "pass_yd": 0.04,
        "pass_td": 4.0,
        "interception": -2.0,
        "fumble_lost": -2.0,
        "2pt_conversion": 2.0,
    },
    "half_ppr": {
        "reception": 0.5,
        "rush_yd": 0.1,
        "rec_yd": 0.1,
        "rush_td": 6.0,
        "rec_td": 6.0,
        "pass_yd": 0.04,
        "pass_td": 4.0,
        "interception": -2.0,
        "fumble_lost": -2.0,
        "2pt_conversion": 2.0,
    },
    "standard": {
        "reception": 0.0,
        "rush_yd": 0.1,
        "rec_yd": 0.1,
        "rush_td": 6.0,
        "rec_td": 6.0,
        "pass_yd": 0.04,
        "pass_td": 4.0,
        "interception": -2.0,
        "fumble_lost": -2.0,
        "2pt_conversion": 2.0,
    },
}

# Fantasy roster configurations by league format
ROSTER_CONFIGS: Dict[str, Dict[str, int]] = {
    "standard": {
        "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1,
        "BN": 6,
    },
    "superflex": {
        "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SFLEX": 1, "K": 1, "DST": 1,
        "BN": 6,
    },
    "2qb": {
        "QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1,
        "BN": 6,
    },
}

# Player positions tracked for fantasy
FANTASY_POSITIONS = ["QB", "RB", "WR", "TE"]

# S3 key templates for player data (Bronze layer)
PLAYER_S3_KEYS = {
    "player_weekly": "players/weekly/season={season}/week={week}/player_weekly_{ts}.parquet",
    "snap_counts": "players/snaps/season={season}/week={week}/snap_counts_{ts}.parquet",
    "injuries": "players/injuries/season={season}/week={week}/injuries_{ts}.parquet",
    "rosters": "players/rosters/season={season}/rosters_{ts}.parquet",
    "player_seasonal": "players/seasonal/season={season}/player_seasonal_{ts}.parquet",
}

# Files are written with a timestamp suffix to preserve full history.
# Readers MUST use download_latest_parquet() from src/utils.py to resolve
# the canonical (most recent) file for a given partition prefix.
# S3 key templates for Silver layer player analytics
SILVER_PLAYER_S3_KEYS = {
    "usage_metrics": "players/usage/season={season}/week={week}/usage_{ts}.parquet",
    "opponent_rankings": "defense/positional/season={season}/week={week}/opp_rankings_{ts}.parquet",
    "rolling_averages": "players/rolling/season={season}/week={week}/rolling_{ts}.parquet",
}

# Files are written with a timestamp suffix to preserve full history.
# Readers MUST use download_latest_parquet() from src/utils.py to resolve
# the canonical (most recent) file for a given partition prefix.
# S3 key templates for Gold layer projections
GOLD_PROJECTION_S3_KEYS = {
    "weekly_projections": "projections/season={season}/week={week}/projections_{ts}.parquet",
    "season_projections": "projections/preseason/season={season}/season_proj_{ts}.parquet",
}


def get_max_season() -> int:
    """Return the maximum valid NFL season year (current year + 1).

    This allows referencing next year's draft/combine data without
    hardcoding a specific year.

    Returns:
        The current calendar year plus one.
    """
    return datetime.date.today().year + 1


# Per-data-type valid season ranges.
# Each entry maps a data type name to (min_season, max_season_callable).
# The callable is deferred so the upper bound stays dynamic.
DATA_TYPE_SEASON_RANGES: Dict[str, Tuple[int, Callable[[], int]]] = {
    "schedules": (1999, get_max_season),
    "pbp": (1999, get_max_season),
    "player_weekly": (2002, get_max_season),
    "player_seasonal": (2002, get_max_season),
    "snap_counts": (2012, get_max_season),
    "injuries": (2009, get_max_season),
    "rosters": (2002, get_max_season),
    "teams": (1999, get_max_season),
    "ngs": (2016, get_max_season),
    "pfr_weekly": (2018, get_max_season),
    "pfr_seasonal": (2018, get_max_season),
    "qbr": (2006, get_max_season),
    "depth_charts": (2001, get_max_season),
    "draft_picks": (2000, get_max_season),
    "combine": (2000, get_max_season),
}


def validate_season_for_type(data_type: str, season: int) -> bool:
    """Check whether a season is within the valid range for a data type.

    Args:
        data_type: One of the keys in DATA_TYPE_SEASON_RANGES.
        season: The NFL season year to validate.

    Returns:
        True if the season is valid for the given data type, False otherwise.

    Raises:
        ValueError: If data_type is not recognized.
    """
    if data_type not in DATA_TYPE_SEASON_RANGES:
        raise ValueError(
            f"Unknown data type '{data_type}'. "
            f"Valid types: {sorted(DATA_TYPE_SEASON_RANGES.keys())}"
        )
    min_season, max_season_fn = DATA_TYPE_SEASON_RANGES[data_type]
    return min_season <= season <= max_season_fn()


def get_s3_path(layer: str, dataset: str = "", season: int = None, week: int = None) -> str:
    """
    Generate S3 path for a specific layer and dataset

    Args:
        layer: bronze, silver, or gold
        dataset: name of the dataset (e.g., 'games', 'players')
        season: NFL season year
        week: NFL week number

    Returns:
        Complete S3 path
    """
    base_path = S3_PATHS[layer]

    if dataset:
        base_path += f"{dataset}/"

    if season:
        base_path += f"season={season}/"

    if week:
        base_path += f"week={week}/"

    return base_path
