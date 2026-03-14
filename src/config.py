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

# Seasons available for player projection training data (5 seasons).
# Note: 2025 uses nflverse stats_player tag (not legacy player_stats tag).
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

# NFL Team Divisions (32 teams, 8 divisions, 4 teams each)
TEAM_DIVISIONS = {
    "ARI": "NFC West", "ATL": "NFC South", "BAL": "AFC North", "BUF": "AFC East",
    "CAR": "NFC South", "CHI": "NFC North", "CIN": "AFC North", "CLE": "AFC North",
    "DAL": "NFC East", "DEN": "AFC West", "DET": "NFC North", "GB": "NFC North",
    "HOU": "AFC South", "IND": "AFC South", "JAX": "AFC South", "KC": "AFC West",
    "LA": "NFC West", "LAC": "AFC West", "LV": "AFC West", "MIA": "AFC East",
    "MIN": "NFC North", "NE": "AFC East", "NO": "NFC South", "NYG": "NFC East",
    "NYJ": "AFC East", "PHI": "NFC East", "PIT": "AFC North", "SEA": "NFC West",
    "SF": "NFC West", "TB": "NFC South", "TEN": "AFC South", "WAS": "NFC East",
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
    "advanced_profiles": "players/advanced/season={season}/advanced_profiles_{ts}.parquet",
}

# Files are written with a timestamp suffix to preserve full history.
# Readers MUST use download_latest_parquet() from src/utils.py to resolve
# the canonical (most recent) file for a given partition prefix.
# S3 key templates for Silver layer team analytics
SILVER_TEAM_S3_KEYS = {
    "pbp_metrics": "teams/pbp_metrics/season={season}/pbp_metrics_{ts}.parquet",
    "tendencies": "teams/tendencies/season={season}/tendencies_{ts}.parquet",
    "sos": "teams/sos/season={season}/sos_{ts}.parquet",
    "situational": "teams/situational/season={season}/situational_{ts}.parquet",
}

# Files are written with a timestamp suffix to preserve full history.
# Readers MUST use download_latest_parquet() from src/utils.py to resolve
# the canonical (most recent) file for a given partition prefix.
# S3 key templates for Gold layer projections
GOLD_PROJECTION_S3_KEYS = {
    "weekly_projections": "projections/season={season}/week={week}/projections_{ts}.parquet",
    "season_projections": "projections/preseason/season={season}/season_proj_{ts}.parquet",
}


# Curated PBP columns (~103) for game prediction models.
# Covers EPA, WPA, CPOE, air yards, success, player IDs, Vegas lines,
# play situation, and weather. Excludes participation merge columns.
PBP_COLUMNS = [
    # Game/play identifiers (10)
    "game_id", "play_id", "season", "week", "season_type", "game_date",
    "posteam", "defteam", "home_team", "away_team",
    # Score context (8)
    "home_score", "away_score", "posteam_score", "defteam_score",
    "posteam_score_post", "defteam_score_post",
    "score_differential", "score_differential_post",
    # Play situation (11)
    "down", "ydstogo", "yardline_100", "goal_to_go",
    "qtr", "quarter_seconds_remaining", "half_seconds_remaining",
    "game_seconds_remaining", "drive",
    "posteam_timeouts_remaining", "defteam_timeouts_remaining",
    # Play type and result (22)
    "play_type", "yards_gained", "shotgun", "no_huddle",
    "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike",
    "pass_attempt", "rush_attempt", "pass_length", "pass_location",
    "run_location", "run_gap",
    "complete_pass", "incomplete_pass", "interception", "sack",
    "fumble", "fumble_lost", "penalty",
    "first_down", "third_down_converted", "third_down_failed",
    "fourth_down_converted", "fourth_down_failed",
    "touchdown", "pass_touchdown", "rush_touchdown", "safety",
    # EPA metrics (7)
    "epa", "ep", "air_epa", "yac_epa", "comp_air_epa", "comp_yac_epa",
    "qb_epa",
    # WPA metrics (11)
    "wpa", "vegas_wpa", "air_wpa", "yac_wpa", "comp_air_wpa", "comp_yac_wpa",
    "wp", "def_wp", "home_wp", "away_wp",
    "home_wp_post", "away_wp_post",
    # Completion metrics (4)
    "cpoe", "cp", "xpass", "pass_oe",
    # Yardage (5)
    "air_yards", "yards_after_catch", "passing_yards", "receiving_yards",
    "rushing_yards",
    # Success (1)
    "success",
    # Player IDs (6)
    "passer_player_id", "passer_player_name",
    "receiver_player_id", "receiver_player_name",
    "rusher_player_id", "rusher_player_name",
    # Vegas lines (2)
    "spread_line", "total_line",
    # Series (3)
    "series", "series_success", "series_result",
    # Weather/venue (4)
    "temp", "wind", "roof", "surface",
]


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
    "injuries": (2009, lambda: 2024),  # nflverse discontinued injury data after 2024
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

# Season threshold for nflverse stats_player tag (replaces archived player_stats tag).
# Seasons >= this value are fetched directly from GitHub releases instead of via nfl-data-py.
STATS_PLAYER_MIN_SEASON = 2025

# Column renames: stats_player schema -> backward-compatible Bronze schema.
# The new tag renamed 5 columns; downstream code (scoring_calculator, player_analytics,
# projection_engine) expects the old names.
STATS_PLAYER_COLUMN_MAP = {
    "passing_interceptions": "interceptions",
    "sacks_suffered": "sacks",
    "sack_yards_lost": "sack_yards",
    "team": "recent_team",
    "passing_cpoe": "dakota",
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
