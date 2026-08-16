"""Weather feature table -- Open-Meteo Bronze weather -> per-team (season, week, team) features.

STANDALONE module, not wired into src/player_feature_engineering.py or
src/feature_engineering.py (integration is documented, not applied -- see
.planning/WEATHER_DATA_2026_08_16.md for the exact patch).

Consumes data/bronze/weather/ (built by scripts/bronze_weather_ingestion.py)
and data/bronze/schedules/ (for the home/away -> team unpivot, same pattern
as src/game_context.py._unpivot_schedules). Produces four candidate features
per team-game:

    wind_speed_mph  -- Open-Meteo game-hour wind speed (0.0 for domes)
    is_high_wind    -- wind_speed_mph >= 15 (nflverse convention threshold,
                        matches game_context.compute_weather_features)
    precip_in       -- game-hour precipitation in inches (0.0 for domes) --
                        NOT available anywhere else in this repo
    is_dome         -- roof in {dome, closed}; duplicated here so this table
                        is self-contained and joinable without game_context

Deliberately does NOT duplicate temperature/is_cold -- those already exist
in game_context.compute_weather_features from nflverse's temp/wind columns
and are adequate outside 2022/2023 (see report for coverage numbers). This
table's wind/precip values come from Open-Meteo for every season uniformly,
including 2022/2023 where nflverse's own temp/wind are largely null.
"""

import glob
import logging

import pandas as pd

logger = logging.getLogger(__name__)

BRONZE_WEATHER_GLOB = "data/bronze/weather/season=*/**/*.parquet"
BRONZE_SCHEDULES_GLOB = "data/bronze/schedules/season=*/**/*.parquet"
HIGH_WIND_THRESHOLD_MPH = 15.0


def load_bronze_weather(seasons=None) -> pd.DataFrame:
    """Load game-level weather rows written by scripts/bronze_weather_ingestion.py."""
    files = glob.glob(BRONZE_WEATHER_GLOB, recursive=True)
    if not files:
        raise FileNotFoundError(
            f"No weather parquet found under {BRONZE_WEATHER_GLOB} -- "
            "run scripts/bronze_weather_ingestion.py first"
        )
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if seasons:
        df = df[df["season"].isin(seasons)]
    # Latest write wins if the script was rerun for the same game_id
    df = df.sort_values(["game_id"]).drop_duplicates(subset=["game_id"], keep="last")
    return df.reset_index(drop=True)


def _unpivot_schedules_teams(schedules_df: pd.DataFrame) -> pd.DataFrame:
    """Minimal home/away -> team unpivot, mirroring game_context._unpivot_schedules.

    Only carries the columns this module needs (game_id, season, week, team)
    to avoid coupling to game_context's private helper.
    """
    home = schedules_df.rename(columns={"home_team": "team"})[["game_id", "season", "week", "team"]]
    away = schedules_df.rename(columns={"away_team": "team"})[["game_id", "season", "week", "team"]]
    return pd.concat([home, away], ignore_index=True)


def compute_weather_features(seasons=None) -> pd.DataFrame:
    """Build the standalone weather feature table keyed (season, week, team).

    Returns:
        DataFrame with columns: season, week, team, game_id, wind_speed_mph,
        is_high_wind, precip_in, is_dome.
    """
    weather = load_bronze_weather(seasons)

    # Bronze weather only covers 2016-2025 (see scripts/bronze_weather_ingestion.py).
    # Restrict schedules to exactly the seasons weather has, even when the
    # caller doesn't pass `seasons` -- nflverse schedules go back to 1999, so
    # an unfiltered join would silently default is_dome/wind/precip to
    # False/0.0 for every out-of-range season instead of excluding those rows
    # (the join-key silent-degrade failure mode from
    # knowledge-vault/concepts/gated-experiment-coverage-check.md).
    weather_seasons = sorted(weather["season"].unique().tolist())

    sched_files = glob.glob(BRONZE_SCHEDULES_GLOB, recursive=True)
    schedules = pd.concat([pd.read_parquet(f) for f in sched_files], ignore_index=True)
    schedules = schedules[schedules["season"].isin(weather_seasons)]
    team_games = _unpivot_schedules_teams(schedules)

    merged = team_games.merge(
        weather[["game_id", "wind_mph", "wind_gust_mph", "precip_in", "is_dome"]],
        on="game_id",
        how="left",
    )

    n_unmatched = merged["is_dome"].isna().sum()
    if n_unmatched:
        logger.warning(
            "%d/%d team-games have no weather row after restricting to weather_seasons=%s "
            "-- game_id mismatch between schedules and weather bronze, investigate before trusting output",
            n_unmatched, len(merged), weather_seasons,
        )

    out = merged[["season", "week", "team", "game_id"]].copy()
    out["wind_speed_mph"] = merged["wind_mph"].fillna(0.0)
    out["is_high_wind"] = (out["wind_speed_mph"] >= HIGH_WIND_THRESHOLD_MPH).astype(bool)
    out["precip_in"] = merged["precip_in"].fillna(0.0)
    out["is_dome"] = merged["is_dome"].fillna(False).astype(bool)

    return out.sort_values(["team", "season", "week"]).reset_index(drop=True)
