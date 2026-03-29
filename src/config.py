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

# Stadium coordinates for travel distance computation (Phase 22).
# Each entry: team_abbr -> (latitude, longitude, timezone, venue_name)
# Shared stadiums: NYG/NYJ (MetLife), LA/LAC (SoFi).
STADIUM_COORDINATES = {
    "ARI": (33.5277, -112.2626, "America/Phoenix", "State Farm Stadium"),
    "ATL": (33.7554, -84.4010, "America/New_York", "Mercedes-Benz Stadium"),
    "BAL": (39.2780, -76.6228, "America/New_York", "M&T Bank Stadium"),
    "BUF": (42.7738, -78.7870, "America/New_York", "Highmark Stadium"),
    "CAR": (35.2258, -80.8528, "America/New_York", "Bank of America Stadium"),
    "CHI": (41.8623, -87.6167, "America/Chicago", "Soldier Field"),
    "CIN": (39.0955, -84.5161, "America/New_York", "Paycor Stadium"),
    "CLE": (41.5061, -81.6995, "America/New_York", "Huntington Bank Field"),
    "DAL": (32.7473, -97.0945, "America/Chicago", "AT&T Stadium"),
    "DEN": (39.7439, -105.0201, "America/Denver", "Empower Field at Mile High"),
    "DET": (42.3400, -83.0456, "America/New_York", "Ford Field"),
    "GB": (44.5013, -88.0622, "America/Chicago", "Lambeau Field"),
    "HOU": (29.6847, -95.4107, "America/Chicago", "NRG Stadium"),
    "IND": (39.7601, -86.1639, "America/New_York", "Lucas Oil Stadium"),
    "JAX": (30.3239, -81.6373, "America/New_York", "EverBank Stadium"),
    "KC": (39.0489, -94.4839, "America/Chicago", "GEHA Field at Arrowhead Stadium"),
    "LA": (33.9534, -118.3390, "America/Los_Angeles", "SoFi Stadium"),
    "LAC": (33.9534, -118.3390, "America/Los_Angeles", "SoFi Stadium"),
    "LV": (36.0909, -115.1833, "America/Los_Angeles", "Allegiant Stadium"),
    "MIA": (25.9580, -80.2389, "America/New_York", "Hard Rock Stadium"),
    "MIN": (44.9736, -93.2575, "America/Chicago", "U.S. Bank Stadium"),
    "NE": (42.0909, -71.2643, "America/New_York", "Gillette Stadium"),
    "NO": (29.9511, -90.0812, "America/Chicago", "Caesars Superdome"),
    "NYG": (40.8128, -74.0742, "America/New_York", "MetLife Stadium"),
    "NYJ": (40.8128, -74.0742, "America/New_York", "MetLife Stadium"),
    "PHI": (39.9008, -75.1675, "America/New_York", "Lincoln Financial Field"),
    "PIT": (40.4468, -80.0158, "America/New_York", "Acrisure Stadium"),
    "SEA": (47.5952, -122.3316, "America/Los_Angeles", "Lumen Field"),
    "SF": (37.4033, -121.9694, "America/Los_Angeles", "Levi's Stadium"),
    "TB": (27.9759, -82.5033, "America/New_York", "Raymond James Stadium"),
    "TEN": (36.1665, -86.7713, "America/Chicago", "Nissan Stadium"),
    "WAS": (38.9076, -76.8645, "America/New_York", "Northwest Stadium"),
    # International venues
    "LON_TOT": (51.6043, -0.0662, "Europe/London", "Tottenham Hotspur Stadium"),
    "LON_WEM": (51.5560, -0.2795, "Europe/London", "Wembley Stadium"),
    "MUN": (48.2188, 11.6247, "Europe/Berlin", "Allianz Arena"),
    "MEX": (19.3029, -99.1505, "America/Mexico_City", "Estadio Azteca"),
    "SAO": (-23.5275, -46.6780, "America/Sao_Paulo", "Neo Quimica Arena"),
    "MAD": (40.4530, -3.6883, "Europe/Madrid", "Santiago Bernabeu"),
}

# Maps nflverse stadium_id codes to (latitude, longitude, timezone).
# Used by game_context.py for travel distance and timezone differential.
# Covers all 42 unique stadium_ids found in Bronze schedules data (2016-2025).
STADIUM_ID_COORDS: Dict[str, Tuple[float, float, str]] = {
    # Current NFL stadiums
    "PHO00": (33.5277, -112.2626, "America/Phoenix"),       # ARI - State Farm Stadium
    "ATL97": (33.7554, -84.4010, "America/New_York"),        # ATL - Mercedes-Benz Stadium
    "BAL00": (39.2780, -76.6228, "America/New_York"),        # BAL - M&T Bank Stadium
    "BOS00": (42.0909, -71.2643, "America/New_York"),        # NE - Gillette Stadium
    "BUF00": (42.7738, -78.7870, "America/New_York"),        # BUF - Highmark Stadium
    "CAR00": (35.2258, -80.8528, "America/New_York"),        # CAR - Bank of America Stadium
    "CHI98": (41.8623, -87.6167, "America/Chicago"),         # CHI - Soldier Field
    "CIN00": (39.0955, -84.5161, "America/New_York"),        # CIN - Paycor Stadium
    "CLE00": (41.5061, -81.6995, "America/New_York"),        # CLE - Huntington Bank Field
    "DAL00": (32.7473, -97.0945, "America/Chicago"),         # DAL - AT&T Stadium
    "DEN00": (39.7439, -105.0201, "America/Denver"),         # DEN - Empower Field
    "DET00": (42.3400, -83.0456, "America/New_York"),        # DET - Ford Field
    "GNB00": (44.5013, -88.0622, "America/Chicago"),         # GB - Lambeau Field
    "HOU00": (29.6847, -95.4107, "America/Chicago"),         # HOU - NRG Stadium
    "IND00": (39.7601, -86.1639, "America/New_York"),        # IND - Lucas Oil Stadium
    "JAX00": (30.3239, -81.6373, "America/New_York"),        # JAX - EverBank Stadium
    "KAN00": (39.0489, -94.4839, "America/Chicago"),         # KC - Arrowhead Stadium
    "LAX01": (33.9534, -118.3390, "America/Los_Angeles"),    # LA/LAC - SoFi Stadium
    "VEG00": (36.0909, -115.1833, "America/Los_Angeles"),    # LV - Allegiant Stadium
    "MIA00": (25.9580, -80.2389, "America/New_York"),        # MIA - Hard Rock Stadium
    "MIN01": (44.9736, -93.2575, "America/Chicago"),         # MIN - U.S. Bank Stadium
    "NAS00": (36.1665, -86.7713, "America/Chicago"),         # TEN - Nissan Stadium
    "NOR00": (29.9511, -90.0812, "America/Chicago"),         # NO - Caesars Superdome
    "NYC01": (40.8128, -74.0742, "America/New_York"),        # NYG/NYJ - MetLife Stadium
    "PHI00": (39.9008, -75.1675, "America/New_York"),        # PHI - Lincoln Financial Field
    "PIT00": (40.4468, -80.0158, "America/New_York"),        # PIT - Acrisure Stadium
    "SEA00": (47.5952, -122.3316, "America/Los_Angeles"),    # SEA - Lumen Field
    "SFO01": (37.4033, -121.9694, "America/Los_Angeles"),    # SF - Levi's Stadium
    "TAM00": (27.9759, -82.5033, "America/New_York"),        # TB - Raymond James Stadium
    "WAS00": (38.9076, -76.8645, "America/New_York"),        # WAS - Northwest Stadium
    # Legacy stadiums (relocated/demolished)
    "ATL00": (33.7573, -84.4009, "America/New_York"),        # Georgia Dome (ATL, pre-2017)
    "OAK00": (37.7516, -122.2006, "America/Los_Angeles"),    # Oakland Coliseum (OAK -> LV 2020)
    "SDG00": (32.7831, -117.1196, "America/Los_Angeles"),    # Qualcomm Stadium (SD -> LAC 2017)
    "LAX97": (33.8644, -118.2611, "America/Los_Angeles"),    # StubHub Center (LAC temp 2017-2019)
    "LAX99": (33.8644, -118.2611, "America/Los_Angeles"),    # LA Memorial Coliseum (LA 2016-2019)
    # International venues
    "LON00": (51.5560, -0.2795, "Europe/London"),            # Wembley Stadium
    "LON01": (51.4560, -0.3416, "Europe/London"),            # Twickenham Stadium
    "LON02": (51.6043, -0.0662, "Europe/London"),            # Tottenham Hotspur Stadium
    "GER00": (48.2188, 11.6247, "Europe/Berlin"),            # Allianz Arena (Munich)
    "MEX00": (19.3029, -99.1505, "America/Mexico_City"),     # Estadio Azteca
    "SAO00": (-23.5275, -46.6780, "America/Sao_Paulo"),      # Neo Quimica Arena (Sao Paulo)
    "FRA00": (50.0688, 8.6453, "Europe/Berlin"),             # Deutsche Bank Park (Frankfurt)
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
    "historical_profiles": "players/historical/combine_draft_profiles_{ts}.parquet",
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
    "pbp_derived": "teams/pbp_derived/season={season}/pbp_derived_{ts}.parquet",
    "game_context": "teams/game_context/season={season}/game_context_{ts}.parquet",
    "referee_tendencies": "teams/referee_tendencies/season={season}/referee_tendencies_{ts}.parquet",
    "playoff_context": "teams/playoff_context/season={season}/playoff_context_{ts}.parquet",
    "market_data": "teams/market_data/season={season}/market_data_{ts}.parquet",
}

# Files are written with a timestamp suffix to preserve full history.
# Readers MUST use download_latest_parquet() from src/utils.py to resolve
# the canonical (most recent) file for a given partition prefix.
# S3 key templates for Gold layer projections
GOLD_PROJECTION_S3_KEYS = {
    "weekly_projections": "projections/season={season}/week={week}/projections_{ts}.parquet",
    "season_projections": "projections/preseason/season={season}/season_proj_{ts}.parquet",
}


# Curated PBP columns (~140) for game prediction models.
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
    # Penalty detail (5)
    "penalty_type", "penalty_yards", "penalty_team",
    "penalty_player_id", "penalty_player_name",
    # Special teams flags (4)
    "special_teams_play", "st_play_type",
    "kickoff_attempt", "punt_attempt",
    # Special teams results (6)
    "kick_distance", "return_yards",
    "field_goal_result", "field_goal_attempt",
    "extra_point_result", "extra_point_attempt",
    # Special teams detail (5)
    "punt_blocked",
    "kickoff_returner_player_id", "punt_returner_player_id",
    "kicker_player_id", "kicker_player_name",
    # Punt detail (5)
    "punt_inside_twenty", "punt_in_endzone",
    "punt_out_of_bounds", "punt_downed", "punt_fair_catch",
    # Kickoff detail (5)
    "kickoff_inside_twenty", "kickoff_in_endzone",
    "kickoff_out_of_bounds", "kickoff_downed", "kickoff_fair_catch",
    # Fumble recovery (5)
    "fumble_forced", "fumble_not_forced",
    "fumble_recovery_1_team", "fumble_recovery_1_yards",
    "fumble_recovery_1_player_id",
    # Drive detail (2)
    "drive_play_count", "drive_time_of_possession",
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
    "officials": (2015, get_max_season),
    "odds": (2016, get_max_season),
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


# ── Prediction Model Configuration ──────────────────────────────────────

HOLDOUT_SEASON = 2025  # Sealed — never used during tuning
PREDICTION_SEASONS = list(range(2016, HOLDOUT_SEASON + 1))  # 2016 through holdout (inclusive)
TRAINING_SEASONS = list(range(2016, HOLDOUT_SEASON))  # 2016 through holdout-1
VALIDATION_SEASONS = [s for s in range(2019, HOLDOUT_SEASON)]  # Walk-forward folds

# Model output directory
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

# Conservative XGBoost defaults — shallow trees, strong regularization
CONSERVATIVE_PARAMS = {
    "objective": "reg:squarederror",
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "early_stopping_rounds": 50,
    "random_state": 42,
    "verbosity": 0,
}

# LightGBM conservative defaults — analogous to XGBoost CONSERVATIVE_PARAMS
LGB_CONSERVATIVE_PARAMS = {
    "objective": "regression",
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "random_state": 42,
    "verbose": -1,
    "force_col_wise": True,
}

# CatBoost conservative defaults — analogous to XGBoost CONSERVATIVE_PARAMS
CB_CONSERVATIVE_PARAMS = {
    "loss_function": "RMSE",
    "depth": 4,
    "learning_rate": 0.05,
    "iterations": 500,
    "l2_leaf_reg": 5.0,
    "min_data_in_leaf": 20,
    "subsample": 0.8,
    "bootstrap_type": "Bernoulli",
    "rsm": 0.7,
    "random_seed": 42,
    "verbose": 0,
    "early_stopping_rounds": 50,
    "allow_writing_files": False,
}

# Ensemble model directory (flat structure under models/)
ENSEMBLE_DIR = os.path.join(MODEL_DIR, "ensemble")

# EWM target columns -- subset of PBP metrics for exponentially weighted windows.
# Restricted to core efficiency metrics to avoid feature explosion (D-09).
EWM_TARGET_COLS = [
    "off_epa_per_play", "def_epa_per_play",
    "off_success_rate", "def_success_rate",
    "cpoe",
    "rz_td_rate", "def_rz_td_rate",
]

# Feature selection result -- populated by scripts/run_feature_selection.py
# When None, model training uses all features from get_feature_columns().
# When populated, model training uses only these features.
SELECTED_FEATURES = None

# Label columns that must NEVER appear in feature set
LABEL_COLUMNS = [
    "home_score", "away_score", "actual_margin", "actual_total",
    "result", "spread_line", "total_line", "team_score", "opp_score",
]

# Silver team source subdirectories (local path pattern)
SILVER_TEAM_LOCAL_DIRS = {
    "pbp_metrics": "teams/pbp_metrics",
    "tendencies": "teams/tendencies",
    "sos": "teams/sos",
    "situational": "teams/situational",
    "pbp_derived": "teams/pbp_derived",
    "game_context": "teams/game_context",
    "referee_tendencies": "teams/referee_tendencies",
    "playoff_context": "teams/playoff_context",
    "player_quality": "teams/player_quality",  # Phase 28: player quality features
    "market_data": "teams/market_data",  # Phase 33: line movement features
}

# Silver player source subdirectories (local path pattern)
SILVER_PLAYER_LOCAL_DIRS = {
    "usage": "players/usage",
    "advanced": "players/advanced",
    "historical": "players/historical",
}

# Silver team sources used for player feature assembly (subset of SILVER_TEAM_LOCAL_DIRS)
SILVER_PLAYER_TEAM_SOURCES = {
    "player_quality": "teams/player_quality",
    "game_context": "teams/game_context",
    "market_data": "teams/market_data",
    "pbp_metrics": "teams/pbp_metrics",
    "tendencies": "teams/tendencies",
}

# Target label columns for player prediction (same-week actuals, NOT features)
PLAYER_LABEL_COLUMNS = [
    "passing_yards", "passing_tds", "interceptions",
    "rushing_yards", "rushing_tds", "carries",
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "fantasy_points_ppr",
]


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
