"""FTN Charting Data — Silver Player-Week Feature Computation.

Joins FTN play-charting data (from Bronze) against Bronze PBP to attribute
per-play flags to the correct receiver/QB, then aggregates to player-week
granularity with shift(1) temporal lag enforced.

Coverage: FTN data available 2022+ only. For seasons 2016-2021 all feature
columns are NaN; imputation is left to downstream consumers (position-mean
fill or 2022+ restricted training subset).

Receiver (WR/RB/TE) features (all _roll4 and _trail variants use shift(1)):
  - ftn_catchable_rate      : catchable targets / targets
  - ftn_contested_rate      : contested targets / targets
  - ftn_drop_rate           : drops / targets
  - ftn_pa_target_share     : play-action targets / targets
  - ftn_created_rec_rate    : YAC-created receptions / completions

QB features:
  - ftn_blitz_rate          : fraction of dropbacks with n_blitzers > 0
  - ftn_avg_pass_rushers    : mean n_pass_rushers per dropback
  - ftn_out_of_pocket_rate  : mean is_qb_out_of_pocket
  - ftn_throw_away_rate     : mean is_throw_away
  - ftn_interception_worthy_rate : mean is_interception_worthy
  - ftn_play_action_rate    : mean is_play_action (as QB caller)

All features in FTN_RECEIVER_RAW_FEATURES and FTN_QB_RAW_FEATURES are the
unlagged per-week values used to compute the trailing features below.

Exported trailing feature columns (the only columns that should flow into
`player_feature_engineering.py`):
  - {feat}_roll4   : shift(1) rolling 4-week mean within (player_id, season)
  - {feat}_trail   : shift(1) season-to-date mean within (player_id, season)

Usage:
    from ftn_features import (
        compute_ftn_player_week,
        add_ftn_trailing_features,
        FTN_FEATURE_COLUMNS,
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

FTN_RECEIVER_RAW_FEATURES: List[str] = [
    "ftn_catchable_rate",
    "ftn_contested_rate",
    "ftn_drop_rate",
    "ftn_pa_target_share",
    "ftn_created_rec_rate",
]

FTN_QB_RAW_FEATURES: List[str] = [
    "ftn_blitz_rate",
    "ftn_avg_pass_rushers",
    "ftn_out_of_pocket_rate",
    "ftn_throw_away_rate",
    "ftn_interception_worthy_rate",
    "ftn_play_action_rate",
]

FTN_ALL_RAW_FEATURES: List[str] = FTN_RECEIVER_RAW_FEATURES + FTN_QB_RAW_FEATURES

# Trailing feature columns added by add_ftn_trailing_features().
# These are the ONLY FTN columns that should appear in the model feature vector.
FTN_FEATURE_COLUMNS: List[str] = [
    f"{feat}_roll4" for feat in FTN_ALL_RAW_FEATURES
] + [
    f"{feat}_trail" for feat in FTN_ALL_RAW_FEATURES
]

# Join keys between FTN and PBP
_FTN_GAME_KEY = "nflverse_game_id"
_FTN_PLAY_KEY = "nflverse_play_id"
_PBP_GAME_KEY = "game_id"
_PBP_PLAY_KEY = "play_id_int"  # cast from float32 play_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_bronze_ftn(season: int, bronze_dir: str) -> pd.DataFrame:
    """Read latest Bronze FTN parquet for a season.

    Args:
        season: NFL season year.
        bronze_dir: Root Bronze data directory.

    Returns:
        FTN charting DataFrame, or empty DataFrame if not found.
    """
    pattern = os.path.join(
        bronze_dir, "ftn_charting", f"season={season}", "*.parquet"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        logger.debug("No Bronze FTN data for season %d at %s", season, pattern)
        return pd.DataFrame()
    try:
        df = pd.read_parquet(files[-1])
        logger.info(
            "Loaded Bronze FTN season %d: %d rows from %s",
            season,
            len(df),
            files[-1],
        )
        return df
    except Exception as exc:
        logger.warning("Failed to read Bronze FTN season %d: %s", season, exc)
        return pd.DataFrame()


def _load_bronze_pbp(season: int, bronze_dir: str) -> pd.DataFrame:
    """Read latest Bronze PBP parquet for a season, retaining only needed columns.

    Args:
        season: NFL season year.
        bronze_dir: Root Bronze data directory.

    Returns:
        PBP DataFrame with join keys and player attribution columns.
    """
    pattern = os.path.join(bronze_dir, "pbp", f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        logger.warning("No Bronze PBP data for season %d", season)
        return pd.DataFrame()

    keep_cols = [
        "game_id",
        "play_id",
        "season",
        "week",
        "posteam",
        "defteam",
        "pass_attempt",
        "complete_pass",
        "receiver_player_id",
        "passer_player_id",
        "yardline_100",
        "qb_dropback",
    ]
    try:
        df = pd.read_parquet(files[-1])
        avail = [c for c in keep_cols if c in df.columns]
        df = df[avail].copy()
        # Cast play_id to int for FTN join
        if "play_id" in df.columns:
            df[_PBP_PLAY_KEY] = df["play_id"].astype("Int32")
        return df
    except Exception as exc:
        logger.warning("Failed to read Bronze PBP season %d: %s", season, exc)
        return pd.DataFrame()


def _join_ftn_to_pbp(ftn: pd.DataFrame, pbp: pd.DataFrame) -> pd.DataFrame:
    """Join FTN charting flags onto PBP rows using (game_id, play_id).

    Args:
        ftn: FTN charting DataFrame with nflverse_game_id, nflverse_play_id.
        pbp: PBP DataFrame with game_id, play_id_int.

    Returns:
        Merged DataFrame of PBP rows enriched with FTN flags.
    """
    if ftn.empty or pbp.empty:
        return pd.DataFrame()

    ftn_cols = [
        _FTN_GAME_KEY,
        _FTN_PLAY_KEY,
        "is_catchable_ball",
        "is_contested_ball",
        "is_drop",
        "is_play_action",
        "is_created_reception",
        "n_blitzers",
        "n_pass_rushers",
        "is_qb_out_of_pocket",
        "is_throw_away",
        "is_interception_worthy",
    ]
    avail_ftn = [c for c in ftn_cols if c in ftn.columns]
    ftn_slim = ftn[avail_ftn].copy()
    ftn_slim = ftn_slim.rename(
        columns={
            _FTN_GAME_KEY: _PBP_GAME_KEY,
            _FTN_PLAY_KEY: _PBP_PLAY_KEY,
        }
    )

    merged = pbp.merge(ftn_slim, on=[_PBP_GAME_KEY, _PBP_PLAY_KEY], how="inner")
    logger.info(
        "FTN-PBP join: %d PBP rows, %d FTN rows, %d matched",
        len(pbp),
        len(ftn),
        len(merged),
    )
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_ftn_player_week(
    season: int,
    bronze_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Compute per-player-week FTN raw aggregate features for one season.

    Joins FTN charting data onto PBP, attributes play flags to the correct
    receiver (via receiver_player_id) and QB (via passer_player_id), then
    groups to player-week granularity.

    This function produces the RAW (unlagged) weekly aggregates. Callers must
    apply add_ftn_trailing_features() before feeding into any model.

    Args:
        season: NFL season year. Returns empty DataFrame for seasons < 2022.
        bronze_dir: Root Bronze data directory. Defaults to
            {project_root}/data/bronze/.

    Returns:
        DataFrame with columns:
            player_id, season, week, position_type,
            ftn_catchable_rate, ftn_contested_rate, ftn_drop_rate,
            ftn_pa_target_share, ftn_created_rec_rate,
            ftn_blitz_rate, ftn_avg_pass_rushers, ftn_out_of_pocket_rate,
            ftn_throw_away_rate, ftn_interception_worthy_rate,
            ftn_play_action_rate
    """
    if bronze_dir is None:
        bronze_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "bronze"
        )

    if season < 2022:
        logger.info("FTN data not available for season %d (coverage starts 2022)", season)
        return pd.DataFrame()

    ftn = _load_bronze_ftn(season, bronze_dir)
    if ftn.empty:
        logger.info("No Bronze FTN data for season %d; returning empty", season)
        return pd.DataFrame()

    pbp = _load_bronze_pbp(season, bronze_dir)
    if pbp.empty:
        logger.info("No Bronze PBP data for season %d; returning empty", season)
        return pd.DataFrame()

    merged = _join_ftn_to_pbp(ftn, pbp)
    if merged.empty:
        return pd.DataFrame()

    receiver_rows = []
    qb_rows = []

    # Cast boolean FTN flags
    bool_cols = [
        "is_catchable_ball",
        "is_contested_ball",
        "is_drop",
        "is_play_action",
        "is_created_reception",
        "is_qb_out_of_pocket",
        "is_throw_away",
        "is_interception_worthy",
    ]
    for col in bool_cols:
        if col in merged.columns:
            merged[col] = merged[col].astype(float)

    # --- Receiver features ---
    # Pass-attempt rows with an attributed receiver
    pass_rows = merged[
        merged.get("pass_attempt", merged.get("complete_pass", pd.Series(dtype=float)))
        .fillna(0)
        .astype(bool)
        & merged["receiver_player_id"].notna()
    ].copy() if "receiver_player_id" in merged.columns else pd.DataFrame()

    if not pass_rows.empty:
        pass_rows = pass_rows.rename(columns={"receiver_player_id": "player_id"})

        grp_recv = pass_rows.groupby(["player_id", "season", "week"])

        recv_agg: dict = {}

        targets = grp_recv.size()
        completions = (
            grp_recv["complete_pass"].sum()
            if "complete_pass" in pass_rows.columns
            else pd.Series(0, index=targets.index)
        )

        # catchable_rate: catchable targets / targets
        if "is_catchable_ball" in pass_rows.columns:
            recv_agg["ftn_catchable_rate"] = (
                grp_recv["is_catchable_ball"].sum() / targets
            )

        # contested_rate: contested targets / targets
        if "is_contested_ball" in pass_rows.columns:
            recv_agg["ftn_contested_rate"] = (
                grp_recv["is_contested_ball"].sum() / targets
            )

        # drop_rate: drops / targets (NaN when 0 targets)
        if "is_drop" in pass_rows.columns:
            recv_agg["ftn_drop_rate"] = grp_recv["is_drop"].sum() / targets

        # pa_target_share: play-action targets / targets
        if "is_play_action" in pass_rows.columns:
            recv_agg["ftn_pa_target_share"] = (
                grp_recv["is_play_action"].sum() / targets
            )

        # created_rec_rate: YAC-created receptions / completions
        if "is_created_reception" in pass_rows.columns:
            comp_safe = completions.replace(0, np.nan)
            recv_agg["ftn_created_rec_rate"] = (
                grp_recv["is_created_reception"].sum() / comp_safe
            )

        if recv_agg:
            recv_df = pd.DataFrame(recv_agg)
            recv_df = recv_df.reset_index()
            recv_df["position_type"] = "receiver"
            receiver_rows.append(recv_df)

    # --- QB features ---
    # Dropback rows attributed to the passer
    if "passer_player_id" in merged.columns:
        dropback_mask = (
            merged.get("pass_attempt", pd.Series(0, index=merged.index))
            .fillna(0)
            .astype(bool)
        )
        if "qb_dropback" in merged.columns:
            dropback_mask = (
                merged["qb_dropback"].fillna(0).astype(bool) | dropback_mask
            )

        dropback_rows = merged[
            dropback_mask & merged["passer_player_id"].notna()
        ].copy()

        if not dropback_rows.empty:
            dropback_rows = dropback_rows.rename(
                columns={"passer_player_id": "player_id"}
            )
            grp_qb = dropback_rows.groupby(["player_id", "season", "week"])
            n_dropbacks = grp_qb.size()

            qb_agg: dict = {}

            if "n_blitzers" in dropback_rows.columns:
                qb_agg["ftn_blitz_rate"] = (
                    (dropback_rows.assign(is_blitz=(dropback_rows["n_blitzers"] > 0).astype(float))
                     .groupby(["player_id", "season", "week"])["is_blitz"].sum())
                    / n_dropbacks
                )

            if "n_pass_rushers" in dropback_rows.columns:
                qb_agg["ftn_avg_pass_rushers"] = grp_qb["n_pass_rushers"].mean()

            if "is_qb_out_of_pocket" in dropback_rows.columns:
                qb_agg["ftn_out_of_pocket_rate"] = (
                    grp_qb["is_qb_out_of_pocket"].sum() / n_dropbacks
                )

            if "is_throw_away" in dropback_rows.columns:
                qb_agg["ftn_throw_away_rate"] = (
                    grp_qb["is_throw_away"].sum() / n_dropbacks
                )

            if "is_interception_worthy" in dropback_rows.columns:
                qb_agg["ftn_interception_worthy_rate"] = (
                    grp_qb["is_interception_worthy"].sum() / n_dropbacks
                )

            if "is_play_action" in dropback_rows.columns:
                qb_agg["ftn_play_action_rate"] = (
                    grp_qb["is_play_action"].sum() / n_dropbacks
                )

            if qb_agg:
                qb_df = pd.DataFrame(qb_agg).reset_index()
                qb_df["position_type"] = "qb"
                qb_rows.append(qb_df)

    # Combine receiver and QB rows; a player may appear in both (e.g. scramble
    # catches) but position_type distinguishes use case.
    parts = receiver_rows + qb_rows
    if not parts:
        return pd.DataFrame()

    result = pd.concat(parts, ignore_index=True)

    # Clip rates to [0, 1]
    rate_cols = [c for c in FTN_ALL_RAW_FEATURES if "rate" in c or "share" in c]
    for col in rate_cols:
        if col in result.columns:
            result[col] = result[col].clip(0.0, 1.0)

    # Clip avg_pass_rushers to reasonable range
    if "ftn_avg_pass_rushers" in result.columns:
        result["ftn_avg_pass_rushers"] = result["ftn_avg_pass_rushers"].clip(0.0, 11.0)

    logger.info(
        "compute_ftn_player_week season=%d: %d player-week rows", season, len(result)
    )
    return result


def add_ftn_trailing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add shift(1)-lagged rolling and season-to-date FTN features.

    Computes trailing features within (player_id, season):
      - {feat}_roll4  : shift(1) rolling 4-week mean
      - {feat}_trail  : shift(1) season-to-date mean (expanding window)

    LEAK DISCIPLINE: shift(1) is applied before any rolling calculation.
    Week W features describe performance through week W-1. Never use the
    raw (unlagged) columns from this function's input as model features.

    Args:
        df: Player-week DataFrame containing FTN raw feature columns.
            Must have player_id, season, week columns.

    Returns:
        DataFrame with FTN_FEATURE_COLUMNS added. Raw feature columns are
        retained for intermediate inspection but excluded from the model
        feature set via player_feature_engineering._SAME_WEEK_RAW_STATS.
    """
    if df.empty:
        return df

    df = df.sort_values(["player_id", "season", "week"]).copy()

    raw_features = [c for c in FTN_ALL_RAW_FEATURES if c in df.columns]
    if not raw_features:
        logger.warning(
            "No FTN raw feature columns found; cannot compute trailing features"
        )
        return df

    grouped = df.groupby(["player_id", "season"])

    new_cols: dict = {}
    for feat in raw_features:
        shifted = grouped[feat].transform(lambda s: s.shift(1))

        # Rolling 4-week mean (min_periods=2 to allow early-season values)
        new_cols[f"{feat}_roll4"] = grouped[feat].transform(
            lambda s: s.shift(1).rolling(4, min_periods=2).mean()
        )

        # Season-to-date expanding mean
        new_cols[f"{feat}_trail"] = grouped[feat].transform(
            lambda s: s.shift(1).expanding(min_periods=2).mean()
        )

    df = df.assign(**new_cols)

    logger.info(
        "add_ftn_trailing_features: added %d trailing columns", len(new_cols)
    )
    return df


def build_ftn_silver(
    seasons: List[int],
    bronze_dir: Optional[str] = None,
    silver_dir: Optional[str] = None,
) -> dict:
    """Full Bronze → Silver FTN pipeline for a list of seasons.

    For each season: fetches Bronze FTN, joins to PBP, computes raw
    player-week aggregates, adds trailing features, and writes Silver parquet
    to data/silver/players/ftn/season=YYYY/.

    Args:
        seasons: List of NFL season years (must all be >= 2022).
        bronze_dir: Root Bronze directory. Defaults to data/bronze/.
        silver_dir: Root Silver directory. Defaults to data/silver/.

    Returns:
        Dict mapping season → absolute path of saved Silver parquet.
        Seasons with no data are omitted from the dict.
    """
    _base = os.path.join(os.path.dirname(os.path.dirname(__file__)))
    if bronze_dir is None:
        bronze_dir = os.path.join(_base, "data", "bronze")
    if silver_dir is None:
        silver_dir = os.path.join(_base, "data", "silver")

    from datetime import datetime

    saved: dict = {}
    for season in sorted(seasons):
        if season < 2022:
            logger.info("Skipping season %d — FTN coverage starts 2022", season)
            continue

        raw = compute_ftn_player_week(season, bronze_dir=bronze_dir)
        if raw.empty:
            logger.warning("No FTN player-week data for season %d", season)
            continue

        enriched = add_ftn_trailing_features(raw)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        season_dir = os.path.join(silver_dir, "players", "ftn", f"season={season}")
        os.makedirs(season_dir, exist_ok=True)
        path = os.path.join(season_dir, f"ftn_player_week_{ts}.parquet")
        enriched.to_parquet(path, index=False)
        saved[season] = path
        logger.info("Saved Silver FTN season %d -> %s (%d rows)", season, path, len(enriched))

    return saved
