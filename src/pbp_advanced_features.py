"""PBP-Derived Advanced Player Features — Silver Player-Week Computation.

Mines Bronze PBP (now local 2016-2025) for signals not already covered by the
existing usage/graph/route-participation feature families:

Receiver (WR/RB/TE) features (all _roll4 / _trail / _slope variants use
shift(1) before any window aggregation):
  - adot                    : mean air_yards on the player's targets
                               (depth of target — receiver role/skill signal)
  - deep_target_share       : player's targets with air_yards >= 20 as a
                               share of the TEAM's deep targets that week
  - intermediate_target_share : player's 10-19.99 air_yards targets as a
                               share of the team's intermediate targets
  - short_target_share      : player's < 10 air_yards targets as a share of
                               the team's short targets

QB features:
  - qb_sack_rate             : sacks / dropbacks — pressure/pocket-time proxy
  - qb_avg_intended_air_yards : mean air_yards on pass attempts — aggressiveness
                               / time-to-throw proxy (true TTT is only in NGS;
                               this is a PBP-derivable stand-in, not a
                               replacement)
  - qb_deep_ball_rate        : share of attempts with air_yards >= 20

Overlap check performed before building this module (see
.planning/PBP_FEATURES_2026_08_16.md): team-level PROE/pace already exist as
trailing features (`proe_roll3`/`pace_roll3` etc., src/team_analytics.py,
joined at player_feature_engineering.py step 6) — NOT duplicated here.
WR/TE slot-vs-wide alignment is NOT derivable: local `pbp_participation`
Bronze only carries `offense_players`/`defense_players` gsis-id lists, no
formation/personnel/alignment columns.

All raw (unlagged) columns above describe the week being predicted and must
never be used directly as model features — only the trailing variants below.

Exported trailing feature columns (the only columns that should flow into
`player_feature_engineering.py`):
  - {feat}_roll4  : shift(1) rolling 4-week mean within (player_id, season)
  - {feat}_trail  : shift(1) season-to-date mean within (player_id, season)
  - adot_slope    : OLS trend of the trailing 4 shifted adot values

Usage:
    from pbp_advanced_features import (
        compute_pbp_advanced_player_week,
        add_pbp_advanced_trailing_features,
        PBP_ADVANCED_FEATURE_COLUMNS,
    )
"""

import glob
import logging
import os
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature column registries
# ---------------------------------------------------------------------------

PBP_ADV_RECEIVER_RAW_FEATURES: List[str] = [
    "adot",
    "deep_target_share",
    "intermediate_target_share",
    "short_target_share",
]

PBP_ADV_QB_RAW_FEATURES: List[str] = [
    "qb_sack_rate",
    "qb_avg_intended_air_yards",
    "qb_deep_ball_rate",
]

PBP_ADV_ALL_RAW_FEATURES: List[str] = (
    PBP_ADV_RECEIVER_RAW_FEATURES + PBP_ADV_QB_RAW_FEATURES
)

# Trailing feature columns added by add_pbp_advanced_trailing_features().
# These are the ONLY pbp_advanced columns that should appear in the model
# feature vector.
PBP_ADVANCED_FEATURE_COLUMNS: List[str] = (
    [f"{feat}_roll4" for feat in PBP_ADV_ALL_RAW_FEATURES]
    + [f"{feat}_trail" for feat in PBP_ADV_ALL_RAW_FEATURES]
    + ["adot_slope"]
)

_TRAIL_WINDOW = 4
_MIN_GAMES = 2
_SLOPE_MIN_GAMES = 3
_DEEP_AY = 20.0
_INTERMEDIATE_AY = 10.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ols_slope(values: np.ndarray) -> float:
    """OLS slope of a 1-D array against 0..n-1. NaN if under-determined."""
    n = len(values)
    if n < _SLOPE_MIN_GAMES:
        return float("nan")
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = values.mean()
    den = ((x - x_mean) ** 2).sum()
    if den == 0:
        return float("nan")
    return float(((x - x_mean) * (values - y_mean)).sum() / den)


def _slope_for_window(sub: "pd.Series") -> float:
    valid = sub.dropna()
    if len(valid) < _SLOPE_MIN_GAMES:
        return float("nan")
    return _ols_slope(valid.values)


def _load_bronze_pbp(season: int, bronze_dir: str) -> pd.DataFrame:
    """Read latest Bronze PBP parquet for a season, retaining only needed cols."""
    pattern = os.path.join(bronze_dir, "pbp", f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        logger.warning("No Bronze PBP data for season %d", season)
        return pd.DataFrame()

    keep_cols = [
        "game_id",
        "season",
        "week",
        "posteam",
        "pass_attempt",
        "qb_dropback",
        "sack",
        "air_yards",
        "receiver_player_id",
        "passer_player_id",
    ]
    try:
        df = pd.read_parquet(files[-1])
        avail = [c for c in keep_cols if c in df.columns]
        return df[avail].copy()
    except Exception as exc:
        logger.warning("Failed to read Bronze PBP season %d: %s", season, exc)
        return pd.DataFrame()


def _zone(air_yards: pd.Series) -> pd.Series:
    """Bucket air_yards into 'deep' (>=20), 'intermediate' (10-19.99), 'short' (<10)."""
    return pd.cut(
        air_yards,
        bins=[-np.inf, _INTERMEDIATE_AY, _DEEP_AY, np.inf],
        labels=["short", "intermediate", "deep"],
        right=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_pbp_advanced_player_week(
    season: int,
    bronze_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Compute per-player-week raw (unlagged) PBP-advanced aggregates.

    Callers must apply add_pbp_advanced_trailing_features() before feeding
    into any model — raw columns describe the week being predicted.

    Args:
        season: NFL season year.
        bronze_dir: Root Bronze data directory. Defaults to
            {project_root}/data/bronze/.

    Returns:
        DataFrame with columns: player_id, season, week, position_type, plus
        PBP_ADV_ALL_RAW_FEATURES columns present for that position_type.
    """
    if bronze_dir is None:
        bronze_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "bronze"
        )

    pbp = _load_bronze_pbp(season, bronze_dir)
    if pbp.empty:
        return pd.DataFrame()

    parts = []

    # --- Receiver features: adot + target-share-by-zone ---------------------
    if {"receiver_player_id", "air_yards", "pass_attempt"}.issubset(pbp.columns):
        targets = pbp[
            pbp["pass_attempt"].fillna(0).astype(bool)
            & pbp["receiver_player_id"].notna()
            & pbp["air_yards"].notna()
        ].copy()

        if not targets.empty:
            targets["zone"] = _zone(targets["air_yards"])

            # adot: player-week mean air_yards over targets
            adot = (
                targets.groupby(["receiver_player_id", "season", "week"])["air_yards"]
                .mean()
                .rename("adot")
                .reset_index()
                .rename(columns={"receiver_player_id": "player_id"})
            )

            # Team zone totals (denominator)
            team_zone = (
                targets.groupby(["posteam", "season", "week", "zone"], observed=True)
                .size()
                .rename("team_zone_targets")
                .reset_index()
            )
            team_zone_wide = team_zone.pivot_table(
                index=["posteam", "season", "week"],
                columns="zone",
                values="team_zone_targets",
                fill_value=0,
                observed=True,
            ).reset_index()
            team_zone_wide.columns = [
                str(c) for c in team_zone_wide.columns
            ]
            for z in ("short", "intermediate", "deep"):
                if z not in team_zone_wide.columns:
                    team_zone_wide[z] = 0
            team_zone_wide = team_zone_wide.rename(
                columns={
                    "short": "team_short_targets",
                    "intermediate": "team_intermediate_targets",
                    "deep": "team_deep_targets",
                }
            )

            # Player zone counts (numerator)
            player_zone = (
                targets.groupby(
                    ["receiver_player_id", "posteam", "season", "week", "zone"],
                    observed=True,
                )
                .size()
                .rename("player_zone_targets")
                .reset_index()
            )
            player_zone_wide = player_zone.pivot_table(
                index=["receiver_player_id", "posteam", "season", "week"],
                columns="zone",
                values="player_zone_targets",
                fill_value=0,
                observed=True,
            ).reset_index()
            player_zone_wide.columns = [
                str(c) for c in player_zone_wide.columns
            ]
            for z in ("short", "intermediate", "deep"):
                if z not in player_zone_wide.columns:
                    player_zone_wide[z] = 0
            player_zone_wide = player_zone_wide.rename(
                columns={
                    "short": "player_short_targets",
                    "intermediate": "player_intermediate_targets",
                    "deep": "player_deep_targets",
                    "receiver_player_id": "player_id",
                }
            )

            shares = player_zone_wide.merge(
                team_zone_wide, on=["posteam", "season", "week"], how="left"
            )
            shares["deep_target_share"] = shares["player_deep_targets"] / shares[
                "team_deep_targets"
            ].replace(0, np.nan)
            shares["intermediate_target_share"] = shares[
                "player_intermediate_targets"
            ] / shares["team_intermediate_targets"].replace(0, np.nan)
            shares["short_target_share"] = shares["player_short_targets"] / shares[
                "team_short_targets"
            ].replace(0, np.nan)

            recv = adot.merge(
                shares[
                    [
                        "player_id",
                        "season",
                        "week",
                        "deep_target_share",
                        "intermediate_target_share",
                        "short_target_share",
                    ]
                ],
                on=["player_id", "season", "week"],
                how="left",
            )
            for col in PBP_ADV_RECEIVER_RAW_FEATURES:
                if col in recv.columns:
                    recv[col] = recv[col].clip(lower=0.0) if col == "adot" else recv[
                        col
                    ].clip(0.0, 1.0)
            recv["position_type"] = "receiver"
            parts.append(recv)

    # --- QB features: sack rate, intended air yards, deep-ball rate ---------
    required_qb = {"passer_player_id", "qb_dropback"}
    if required_qb.issubset(pbp.columns):
        dropbacks = pbp[
            pbp["qb_dropback"].fillna(0).astype(bool) & pbp["passer_player_id"].notna()
        ].copy()

        if not dropbacks.empty:
            grp = dropbacks.groupby(["passer_player_id", "season", "week"])
            n_dropbacks = grp.size()

            qb_agg: dict = {}
            if "sack" in dropbacks.columns:
                qb_agg["qb_sack_rate"] = grp["sack"].sum() / n_dropbacks

            if "air_yards" in dropbacks.columns and "pass_attempt" in dropbacks.columns:
                pass_rows = dropbacks[
                    dropbacks["pass_attempt"].fillna(0).astype(bool)
                    & dropbacks["air_yards"].notna()
                ]
                if not pass_rows.empty:
                    pgrp = pass_rows.groupby(["passer_player_id", "season", "week"])
                    n_pass = pgrp.size()
                    qb_agg["qb_avg_intended_air_yards"] = pgrp["air_yards"].mean()
                    qb_agg["qb_deep_ball_rate"] = (
                        pass_rows.assign(is_deep=(pass_rows["air_yards"] >= _DEEP_AY).astype(float))
                        .groupby(["passer_player_id", "season", "week"])["is_deep"]
                        .sum()
                        / n_pass
                    )

            if qb_agg:
                qb_df = pd.DataFrame(qb_agg).reset_index()
                qb_df = qb_df.rename(columns={"passer_player_id": "player_id"})
                if "qb_sack_rate" in qb_df.columns:
                    qb_df["qb_sack_rate"] = qb_df["qb_sack_rate"].clip(0.0, 1.0)
                if "qb_deep_ball_rate" in qb_df.columns:
                    qb_df["qb_deep_ball_rate"] = qb_df["qb_deep_ball_rate"].clip(0.0, 1.0)
                qb_df["position_type"] = "qb"
                parts.append(qb_df)

    if not parts:
        return pd.DataFrame()

    result = pd.concat(parts, ignore_index=True, sort=False)
    logger.info(
        "compute_pbp_advanced_player_week season=%d: %d player-week rows",
        season,
        len(result),
    )
    return result


def add_pbp_advanced_trailing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add shift(1)-lagged rolling, season-to-date, and slope features.

    Computes trailing features within (player_id, season):
      - {feat}_roll4  : shift(1) rolling 4-week mean
      - {feat}_trail  : shift(1) season-to-date mean (expanding window)
      - adot_slope    : OLS slope of the trailing-4 shifted adot values

    LEAK DISCIPLINE: shift(1) is applied before any rolling/expanding/slope
    calculation. Week W features describe performance through week W-1.

    Args:
        df: Player-week DataFrame containing PBP_ADV_ALL_RAW_FEATURES columns.
            Must have player_id, season, week columns.

    Returns:
        DataFrame with PBP_ADVANCED_FEATURE_COLUMNS added.
    """
    if df.empty:
        return df

    df = df.sort_values(["player_id", "season", "week"]).copy()

    raw_features = [c for c in PBP_ADV_ALL_RAW_FEATURES if c in df.columns]
    if not raw_features:
        logger.warning(
            "No pbp_advanced raw feature columns found; cannot compute trailing"
        )
        return df

    grouped = df.groupby(["player_id", "season"])

    new_cols: dict = {}
    for feat in raw_features:
        new_cols[f"{feat}_roll4"] = grouped[feat].transform(
            lambda s: s.shift(1).rolling(_TRAIL_WINDOW, min_periods=_MIN_GAMES).mean()
        )
        new_cols[f"{feat}_trail"] = grouped[feat].transform(
            lambda s: s.shift(1).expanding(min_periods=_MIN_GAMES).mean()
        )

    if "adot" in df.columns:
        new_cols["adot_slope"] = grouped["adot"].transform(
            lambda s: s.shift(1).rolling(_TRAIL_WINDOW, min_periods=_SLOPE_MIN_GAMES).apply(
                _slope_for_window, raw=False
            )
        )

    df = df.assign(**new_cols)
    logger.info(
        "add_pbp_advanced_trailing_features: added %d trailing columns", len(new_cols)
    )
    return df


def build_pbp_advanced_silver(
    seasons: List[int],
    bronze_dir: Optional[str] = None,
    silver_dir: Optional[str] = None,
) -> dict:
    """Full Bronze -> Silver pbp_advanced pipeline for a list of seasons.

    Args:
        seasons: List of NFL season years.
        bronze_dir: Root Bronze directory. Defaults to data/bronze/.
        silver_dir: Root Silver directory. Defaults to data/silver/.

    Returns:
        Dict mapping season -> absolute path of saved Silver parquet.
        Seasons with no data are omitted.
    """
    _base = os.path.dirname(os.path.dirname(__file__))
    if bronze_dir is None:
        bronze_dir = os.path.join(_base, "data", "bronze")
    if silver_dir is None:
        silver_dir = os.path.join(_base, "data", "silver")

    from datetime import datetime

    saved: dict = {}
    for season in sorted(seasons):
        raw = compute_pbp_advanced_player_week(season, bronze_dir=bronze_dir)
        if raw.empty:
            logger.warning("No pbp_advanced data for season %d", season)
            continue

        enriched = add_pbp_advanced_trailing_features(raw)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        season_dir = os.path.join(silver_dir, "players", "pbp_advanced", f"season={season}")
        os.makedirs(season_dir, exist_ok=True)
        path = os.path.join(season_dir, f"pbp_advanced_player_week_{ts}.parquet")
        enriched.to_parquet(path, index=False)
        saved[season] = path
        logger.info(
            "Saved Silver pbp_advanced season %d -> %s (%d rows)",
            season,
            path,
            len(enriched),
        )

    return saved
