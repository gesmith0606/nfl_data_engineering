"""RB vs defensive line/LB matchup feature construction for Neo4j graph.

Builds per-RB-per-week matchup features from PBP run plays using strictly
lagged data (only weeks prior to the target week to prevent leakage).

Features computed (prefixed ``rb_matchup_``):
    1. avg_dl_count         — Average number of defensive linemen faced per carry.
    2. run_gap_success_rate — Success rate (yards >= distance) by run gap vs this defense.
    3. stacked_box_rate     — Fraction of carries facing 8+ defenders in box.
    4. ybc_proxy            — Yards before contact proxy via EPA (positive-EPA rush rate).
    5. lb_tackle_rate       — Fraction of negative-EPA rush plays with LBs present.
    6. def_rush_epa_allowed — Rolling average of EPA allowed by opposing defense on run plays.
    7. goal_line_carry_rate — Fraction of carries inside the 5 yard line.
    8. short_yardage_conv   — Success rate on 3rd/4th-and-2-or-fewer (yards >= distance).

All computations use shift(1) lag or explicit week-exclusion to prevent
temporal leakage. Graceful degradation: missing columns return NaN, not crashes.

Exports:
    compute_rb_matchup_features: Main entry point — pure-pandas, no Neo4j required.
    build_rb_vs_defense_edges: Neo4j edge construction.
    ingest_rb_matchup_graph: Write edges to Neo4j (optional).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "compute_rb_matchup_features",
    "build_rb_vs_defense_edges",
    "ingest_rb_matchup_graph",
    "RB_MATCHUP_FEATURE_COLUMNS",
]

BATCH_SIZE = 500

# Defensive line positions used to count DL on field from participation data
DL_POSITIONS = {"DE", "DT", "NT", "DL", "EDGE"}

# Linebacker positions for tackle-rate computation
LB_POSITIONS = {"LB", "ILB", "OLB", "MLB"}

# Feature column names exposed so downstream aggregators can import the list
RB_MATCHUP_FEATURE_COLUMNS = [
    "rb_matchup_avg_dl_count",
    "rb_matchup_run_gap_success_rate",
    "rb_matchup_stacked_box_rate",
    "rb_matchup_ybc_proxy",
    "rb_matchup_lb_tackle_rate",
    "rb_matchup_def_rush_epa_allowed",
    "rb_matchup_goal_line_carry_rate",
    "rb_matchup_short_yardage_conv",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _safe_col(df: pd.DataFrame, col: str, default) -> pd.Series:
    """Return column series or a constant-default series if absent.

    Args:
        df: Source DataFrame.
        col: Column name to look up.
        default: Scalar default value when column is missing.

    Returns:
        pd.Series with the column data or all-default values.
    """
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def _filter_prior_pbp(
    pbp_df: pd.DataFrame,
    target_season: int,
    target_week: int,
) -> pd.DataFrame:
    """Return PBP rows strictly before (target_season, target_week).

    Args:
        pbp_df: Full play-by-play DataFrame.
        target_season: Target season year.
        target_week: Target week number (exclusive).

    Returns:
        Subset DataFrame with only historical rows.
    """
    prior_season_mask = pbp_df["season"] < target_season
    same_season_prior_week_mask = (pbp_df["season"] == target_season) & (
        pbp_df["week"] < target_week
    )
    return pbp_df[prior_season_mask | same_season_prior_week_mask].copy()


def _get_run_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Filter PBP to run plays with a valid rusher.

    Args:
        pbp_df: Play-by-play DataFrame.

    Returns:
        Filtered subset of run plays.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    run_mask = (pbp_df["play_type"] == "run") & pbp_df["rusher_player_id"].notna()
    rushes = pbp_df[run_mask].copy()

    # Ensure downstream columns exist with safe defaults
    for col, default in [
        ("yards_gained", 0),
        ("epa", 0.0),
        ("touchdown", 0),
        ("run_gap", ""),
    ]:
        if col not in rushes.columns:
            rushes[col] = default

    rushes["yards_gained"] = rushes["yards_gained"].fillna(0)
    rushes["epa"] = rushes["epa"].fillna(0.0)
    rushes["run_gap"] = rushes["run_gap"].fillna("").astype(str)

    return rushes


# ---------------------------------------------------------------------------
# Feature: DL count per play
# ---------------------------------------------------------------------------


def _compute_dl_counts(
    rushes: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Count defensive linemen on field per rush play.

    Args:
        rushes: Run plays DataFrame with game_id and play_id.
        participation_parsed_df: Exploded participation rows with side/position.

    Returns:
        DataFrame with game_id, play_id, dl_count columns.
    """
    if participation_parsed_df.empty:
        return pd.DataFrame(columns=["game_id", "play_id", "dl_count"])

    dl_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(DL_POSITIONS)
    )
    if not dl_mask.any():
        return pd.DataFrame(columns=["game_id", "play_id", "dl_count"])

    dl_per_play = (
        participation_parsed_df[dl_mask]
        .groupby(["game_id", "play_id"], as_index=False)
        .agg(dl_count=("player_gsis_id", "count"))
    )
    return dl_per_play


def _compute_lb_presence(
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Count linebackers on field per play (for tackle-rate feature).

    Args:
        participation_parsed_df: Exploded participation rows.

    Returns:
        DataFrame with game_id, play_id, lb_count columns.
    """
    if participation_parsed_df.empty:
        return pd.DataFrame(columns=["game_id", "play_id", "lb_count"])

    lb_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(LB_POSITIONS)
    )
    if not lb_mask.any():
        return pd.DataFrame(columns=["game_id", "play_id", "lb_count"])

    return (
        participation_parsed_df[lb_mask]
        .groupby(["game_id", "play_id"], as_index=False)
        .agg(lb_count=("player_gsis_id", "count"))
    )


# ---------------------------------------------------------------------------
# Feature: defensive rush EPA allowed (rolling, per opponent team)
# ---------------------------------------------------------------------------


def _compute_def_rush_epa_allowed(
    pbp_df: pd.DataFrame,
    target_season: int,
    target_week: int,
    window: int = 3,
) -> pd.DataFrame:
    """Compute rolling average of EPA allowed by each defense on run plays.

    Uses all prior-week data (shift(1) within the same season; full prior
    seasons are also included). Only the most recent ``window`` games are
    used for the rolling average to keep the feature current.

    Args:
        pbp_df: Full PBP DataFrame (all seasons/weeks).
        target_season: Season to predict for.
        target_week: Week to predict for (prior data only).
        window: Rolling window in weeks.

    Returns:
        DataFrame with defteam, def_rush_epa_allowed columns.
    """
    prior = _filter_prior_pbp(pbp_df, target_season, target_week)
    if prior.empty:
        return pd.DataFrame(columns=["defteam", "def_rush_epa_allowed"])

    run_plays = prior[prior["play_type"] == "run"].copy()
    if run_plays.empty or "epa" not in run_plays.columns:
        return pd.DataFrame(columns=["defteam", "def_rush_epa_allowed"])

    run_plays["epa"] = run_plays["epa"].fillna(0.0)

    # Aggregate to (defteam, season, week) level first
    weekly = (
        run_plays.groupby(["defteam", "season", "week"], as_index=False)
        .agg(week_epa=("epa", "mean"))
    )
    weekly = weekly.sort_values(["defteam", "season", "week"])

    # For each team, take the last `window` weeks of data before target_week
    recent = weekly[
        (weekly["season"] == target_season)
        & (weekly["week"] >= target_week - window)
        & (weekly["week"] < target_week)
    ]
    # If not enough current-season data, backfill with full prior data
    if recent.empty:
        recent = weekly[weekly["season"] < target_season]

    if recent.empty:
        return pd.DataFrame(columns=["defteam", "def_rush_epa_allowed"])

    result = (
        recent.groupby("defteam", as_index=False)
        .agg(def_rush_epa_allowed=("week_epa", "mean"))
    )
    return result


# ---------------------------------------------------------------------------
# Main public function: compute_rb_matchup_features
# ---------------------------------------------------------------------------


def compute_rb_matchup_features(
    pbp_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
    season: Optional[int] = None,
    participation_parsed_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute per-RB-per-week matchup features from PBP run plays.

    All features use strictly lagged data — only weeks prior to each target
    week are considered, preventing temporal leakage. The function iterates
    over every (season, week) pair present in ``pbp_df`` where prior data
    exists (week >= 2 within a season).

    Feature columns returned (all prefixed ``rb_matchup_``):
        avg_dl_count         — Mean DL count per carry (from participation).
        run_gap_success_rate — Success rate by run gap vs this defense.
        stacked_box_rate     — % of carries vs 8+ defenders in box.
        ybc_proxy            — Positive-EPA rush rate as YBC proxy.
        lb_tackle_rate       — LB-present rate on negative-EPA rushes.
        def_rush_epa_allowed — Rolling mean EPA allowed by opposing defense.
        goal_line_carry_rate — % of carries at yardline_100 <= 5.
        short_yardage_conv   — Success rate on 3rd/4th and <= 2 yards.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
            Required: play_type, rusher_player_id, season, week.
            Optional: yards_gained, epa, ydstogo, down, run_gap,
                defenders_in_box, yardline_100, game_id, play_id.
        rosters_df: Roster DataFrame used to confirm RB position.
            If None, all rushers in PBP are included.
        season: If provided, restrict output to this season only.
        participation_parsed_df: Output of parse_participation_players.
            Enables DL count and LB tackle-rate features.
            If None, those features will be NaN.

    Returns:
        DataFrame with columns: player_id, season, week,
        rb_matchup_avg_dl_count, rb_matchup_run_gap_success_rate,
        rb_matchup_stacked_box_rate, rb_matchup_ybc_proxy,
        rb_matchup_lb_tackle_rate, rb_matchup_def_rush_epa_allowed,
        rb_matchup_goal_line_carry_rate, rb_matchup_short_yardage_conv.
        Returns empty DataFrame if inputs are insufficient.

    Example:
        >>> features = compute_rb_matchup_features(
        ...     pbp_df=pbp,
        ...     rosters_df=rosters,
        ...     season=2024,
        ...     participation_parsed_df=parsed_participation,
        ... )
        >>> features.columns.tolist()[:4]
        ['player_id', 'season', 'week', 'rb_matchup_avg_dl_count']
    """
    if pbp_df is None or pbp_df.empty:
        return pd.DataFrame()

    if "season" not in pbp_df.columns or "week" not in pbp_df.columns:
        logger.warning("PBP missing season/week columns — cannot compute RB matchup features")
        return pd.DataFrame()

    if "play_type" not in pbp_df.columns or "rusher_player_id" not in pbp_df.columns:
        logger.warning("PBP missing play_type or rusher_player_id — cannot compute RB matchup features")
        return pd.DataFrame()

    # Determine set of valid RB player IDs from rosters
    rb_ids: Optional[set] = None
    if rosters_df is not None and not rosters_df.empty and "position" in rosters_df.columns:
        id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
        if id_col in rosters_df.columns:
            rb_ids = set(
                rosters_df.loc[rosters_df["position"] == "RB", id_col]
                .astype(str)
                .unique()
            )

    # Determine (season, week) pairs to compute features for
    if season is not None:
        season_weeks = (
            pbp_df[pbp_df["season"] == season][["season", "week"]]
            .drop_duplicates()
            .sort_values(["season", "week"])
        )
    else:
        season_weeks = (
            pbp_df[["season", "week"]].drop_duplicates().sort_values(["season", "week"])
        )

    # Pre-compute lagged DL counts and LB presence if participation available
    dl_counts: pd.DataFrame = pd.DataFrame(columns=["game_id", "play_id", "dl_count"])
    lb_presence: pd.DataFrame = pd.DataFrame(columns=["game_id", "play_id", "lb_count"])
    if participation_parsed_df is not None and not participation_parsed_df.empty:
        all_rushes = _get_run_plays(pbp_df)
        if not all_rushes.empty:
            dl_counts = _compute_dl_counts(all_rushes, participation_parsed_df)
            lb_presence = _compute_lb_presence(participation_parsed_df)

    all_results = []

    for _, sw_row in season_weeks.iterrows():
        target_season = int(sw_row["season"])
        target_week = int(sw_row["week"])

        # Skip week 1 — no prior data within season
        if target_week < 2:
            continue

        # --- Prior PBP for this target week ---
        prior_pbp = _filter_prior_pbp(pbp_df, target_season, target_week)
        if prior_pbp.empty:
            continue

        prior_rushes = _get_run_plays(prior_pbp)
        if prior_rushes.empty:
            continue

        # Filter to RBs if roster is available
        if rb_ids is not None:
            prior_rushes = prior_rushes[
                prior_rushes["rusher_player_id"].astype(str).isin(rb_ids)
            ]
        if prior_rushes.empty:
            continue

        # Get active rushers for this (season, week) to build output rows
        active_rushers = (
            pbp_df[
                (pbp_df["season"] == target_season)
                & (pbp_df["week"] == target_week)
                & (pbp_df["play_type"] == "run")
                & pbp_df["rusher_player_id"].notna()
            ]["rusher_player_id"]
            .astype(str)
            .unique()
        )
        if rb_ids is not None:
            active_rushers = [r for r in active_rushers if r in rb_ids]
        if len(active_rushers) == 0:
            continue

        # Restrict prior rushes to same season for recent features
        recent_prior_rushes = prior_rushes[
            (prior_rushes["season"] == target_season)
            & (prior_rushes["week"] >= target_week - 3)
        ]

        # Merge DL counts if available
        has_participation = (
            not dl_counts.empty
            and "game_id" in prior_rushes.columns
            and "play_id" in prior_rushes.columns
        )
        if has_participation:
            prior_rushes_with_dl = prior_rushes.merge(
                dl_counts, on=["game_id", "play_id"], how="left"
            )
            prior_rushes_with_dl["dl_count"] = prior_rushes_with_dl["dl_count"].fillna(
                np.nan
            )
            prior_rushes_with_lb = prior_rushes.merge(
                lb_presence, on=["game_id", "play_id"], how="left"
            )
            prior_rushes_with_lb["lb_count"] = prior_rushes_with_lb["lb_count"].fillna(
                0
            )
        else:
            prior_rushes_with_dl = prior_rushes.copy()
            prior_rushes_with_dl["dl_count"] = np.nan
            prior_rushes_with_lb = prior_rushes.copy()
            prior_rushes_with_lb["lb_count"] = 0

        # --- Compute per-player features ---
        rows = _compute_per_rb_features(
            rusher_ids=active_rushers,
            prior_rushes=prior_rushes,
            recent_prior_rushes=recent_prior_rushes,
            prior_rushes_with_dl=prior_rushes_with_dl,
            prior_rushes_with_lb=prior_rushes_with_lb,
            target_season=target_season,
            target_week=target_week,
        )

        # --- Attach def_rush_epa_allowed from opposing defense ---
        def_epa_df = _compute_def_rush_epa_allowed(pbp_df, target_season, target_week)

        # Get opponent team for each rusher from the current week's PBP
        opp_map = (
            pbp_df[
                (pbp_df["season"] == target_season)
                & (pbp_df["week"] == target_week)
                & (pbp_df["play_type"] == "run")
                & pbp_df["rusher_player_id"].notna()
                & pbp_df["defteam"].notna()
            ][["rusher_player_id", "defteam"]]
            .rename(columns={"rusher_player_id": "player_id"})
            .drop_duplicates(subset=["player_id"], keep="last")
        )
        opp_map["player_id"] = opp_map["player_id"].astype(str)

        result_df = pd.DataFrame(rows)
        if not result_df.empty and not opp_map.empty and not def_epa_df.empty:
            result_df = result_df.merge(opp_map, on="player_id", how="left")
            result_df = result_df.merge(
                def_epa_df, on="defteam", how="left"
            )
            if "def_rush_epa_allowed" in result_df.columns:
                result_df["rb_matchup_def_rush_epa_allowed"] = result_df[
                    "def_rush_epa_allowed"
                ]
                result_df = result_df.drop(
                    columns=["def_rush_epa_allowed", "defteam"], errors="ignore"
                )
        else:
            if not result_df.empty:
                result_df["rb_matchup_def_rush_epa_allowed"] = np.nan
                result_df = result_df.drop(columns=["defteam"], errors="ignore")

        if not result_df.empty:
            all_results.append(result_df)

    if not all_results:
        return pd.DataFrame()

    output = pd.concat(all_results, ignore_index=True)

    # Ensure all expected columns exist
    out_cols = ["player_id", "season", "week"] + RB_MATCHUP_FEATURE_COLUMNS
    for col in out_cols:
        if col not in output.columns:
            output[col] = np.nan

    output = output[out_cols].drop_duplicates(subset=["player_id", "season", "week"])
    logger.info(
        "Computed %d RB matchup feature rows across %d seasons",
        len(output),
        output["season"].nunique() if not output.empty else 0,
    )
    return output


def _compute_per_rb_features(
    rusher_ids: list,
    prior_rushes: pd.DataFrame,
    recent_prior_rushes: pd.DataFrame,
    prior_rushes_with_dl: pd.DataFrame,
    prior_rushes_with_lb: pd.DataFrame,
    target_season: int,
    target_week: int,
) -> list[dict]:
    """Compute all 8 features for each active rusher.

    Args:
        rusher_ids: List of rusher GSIS IDs active this week.
        prior_rushes: All historical rush plays for this RB.
        recent_prior_rushes: Rush plays from last 3 weeks (same season).
        prior_rushes_with_dl: prior_rushes merged with DL counts.
        prior_rushes_with_lb: prior_rushes merged with LB counts.
        target_season: Season being predicted.
        target_week: Week being predicted.

    Returns:
        List of feature dicts, one per rusher.
    """
    rows = []

    for rusher_id in rusher_ids:
        rid = str(rusher_id)
        rb_rushes = prior_rushes[prior_rushes["rusher_player_id"].astype(str) == rid]
        rb_recent = recent_prior_rushes[
            recent_prior_rushes["rusher_player_id"].astype(str) == rid
        ]
        rb_dl = prior_rushes_with_dl[
            prior_rushes_with_dl["rusher_player_id"].astype(str) == rid
        ]
        rb_lb = prior_rushes_with_lb[
            prior_rushes_with_lb["rusher_player_id"].astype(str) == rid
        ]

        feat: dict = {
            "player_id": rid,
            "season": target_season,
            "week": target_week,
        }

        # 1. avg_dl_count: mean DL count per carry from participation
        if not rb_dl.empty and "dl_count" in rb_dl.columns:
            dl_vals = rb_dl["dl_count"].dropna()
            feat["rb_matchup_avg_dl_count"] = float(dl_vals.mean()) if len(dl_vals) > 0 else np.nan
        else:
            feat["rb_matchup_avg_dl_count"] = np.nan

        # 2. run_gap_success_rate: success (yards >= ydstogo) by run_gap vs opponent
        feat["rb_matchup_run_gap_success_rate"] = _run_gap_success_rate(rb_recent)

        # 3. stacked_box_rate: % of carries facing 8+ defenders in box
        feat["rb_matchup_stacked_box_rate"] = _stacked_box_rate(rb_recent)

        # 4. ybc_proxy: fraction of carries with positive EPA (proxy for breaking tackles)
        feat["rb_matchup_ybc_proxy"] = _ybc_proxy(rb_recent)

        # 5. lb_tackle_rate: LB present on negative-EPA rushes
        feat["rb_matchup_lb_tackle_rate"] = _lb_tackle_rate(rb_lb)

        # 6. def_rush_epa_allowed: filled after merge with def_epa_df
        # (set placeholder; will be replaced after merge in caller)
        feat["rb_matchup_def_rush_epa_allowed"] = np.nan

        # 7. goal_line_carry_rate: % of carries at yardline_100 <= 5
        feat["rb_matchup_goal_line_carry_rate"] = _goal_line_carry_rate(rb_rushes)

        # 8. short_yardage_conv: success rate on 3rd/4th and <= 2
        feat["rb_matchup_short_yardage_conv"] = _short_yardage_conv(rb_rushes)

        rows.append(feat)

    return rows


# ---------------------------------------------------------------------------
# Feature sub-computations
# ---------------------------------------------------------------------------


def _run_gap_success_rate(rushes: pd.DataFrame) -> float:
    """Compute success rate (yards >= distance) across run gaps.

    Args:
        rushes: Run play rows for one RB vs one opponent.

    Returns:
        Success rate [0.0, 1.0] or np.nan if no data.
    """
    if rushes.empty or "yards_gained" not in rushes.columns:
        return np.nan

    if "ydstogo" not in rushes.columns:
        # Without distance data, use a heuristic of 4+ yards as success
        n = len(rushes)
        if n == 0:
            return np.nan
        successes = (rushes["yards_gained"] >= 4).sum()
        return float(successes / n)

    valid = rushes[rushes["ydstogo"].notna() & (rushes["ydstogo"] > 0)]
    if valid.empty:
        return np.nan

    successes = (valid["yards_gained"] >= valid["ydstogo"]).sum()
    return float(successes / len(valid))


def _stacked_box_rate(rushes: pd.DataFrame) -> float:
    """Compute fraction of carries that faced 8+ defenders in box.

    Args:
        rushes: Run play rows for one RB.

    Returns:
        Rate [0.0, 1.0] or np.nan if defenders_in_box is unavailable.
    """
    if rushes.empty or "defenders_in_box" not in rushes.columns:
        return np.nan

    valid = rushes["defenders_in_box"].dropna()
    if len(valid) == 0:
        return np.nan

    stacked = (valid >= 8).sum()
    return float(stacked / len(valid))


def _ybc_proxy(rushes: pd.DataFrame) -> float:
    """Compute positive-EPA rush rate as a yards-before-contact proxy.

    A rush with positive EPA suggests the RB gained more than expected,
    which correlates with breaking through the line before contact.

    Args:
        rushes: Run play rows for one RB.

    Returns:
        Fraction of carries with positive EPA, or np.nan if no data.
    """
    if rushes.empty or "epa" not in rushes.columns:
        return np.nan

    valid = rushes["epa"].dropna()
    if len(valid) == 0:
        return np.nan

    positive_epa = (valid > 0).sum()
    return float(positive_epa / len(valid))


def _lb_tackle_rate(rushes_with_lb: pd.DataFrame) -> float:
    """Compute fraction of negative-EPA rushes where LBs were on field.

    Negative-EPA plays proxy for plays where the RB was stopped early,
    which are more likely to involve a linebacker making the tackle.

    Args:
        rushes_with_lb: Rush plays merged with LB presence counts.

    Returns:
        LB-present rate on negative-EPA carries, or np.nan if no data.
    """
    if rushes_with_lb.empty or "epa" not in rushes_with_lb.columns:
        return np.nan

    if "lb_count" not in rushes_with_lb.columns:
        return np.nan

    negative_epa = rushes_with_lb[rushes_with_lb["epa"] < 0]
    if negative_epa.empty:
        return np.nan

    lb_present = (negative_epa["lb_count"] > 0).sum()
    return float(lb_present / len(negative_epa))


def _goal_line_carry_rate(rushes: pd.DataFrame) -> float:
    """Compute fraction of carries at the goal line (yardline_100 <= 5).

    Args:
        rushes: All historical rush plays for one RB.

    Returns:
        Rate [0.0, 1.0] or np.nan if yardline_100 unavailable.
    """
    if rushes.empty:
        return np.nan

    if "yardline_100" not in rushes.columns:
        return np.nan

    valid = rushes["yardline_100"].dropna()
    if len(valid) == 0:
        return np.nan

    goal_line = (valid <= 5).sum()
    return float(goal_line / len(valid))


def _short_yardage_conv(rushes: pd.DataFrame) -> float:
    """Compute success rate on 3rd or 4th down with <= 2 yards to go.

    Args:
        rushes: All historical rush plays for one RB.

    Returns:
        Conversion rate [0.0, 1.0] or np.nan if no qualifying plays.
    """
    if rushes.empty:
        return np.nan

    if "down" not in rushes.columns or "ydstogo" not in rushes.columns:
        return np.nan

    short_yardage = rushes[
        rushes["down"].isin([3, 4]) & (rushes["ydstogo"] <= 2) & rushes["ydstogo"].notna()
    ]
    if short_yardage.empty:
        return np.nan

    conversions = (short_yardage["yards_gained"] >= short_yardage["ydstogo"]).sum()
    return float(conversions / len(short_yardage))


# ---------------------------------------------------------------------------
# Neo4j edge construction
# ---------------------------------------------------------------------------


def build_rb_vs_defense_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build RB vs defense aggregate edges from PBP run plays.

    Groups run plays by (rusher_player_id, defteam, season, week) and
    aggregates carries, yards, TDs, EPA, stacked-box rate, and run gap
    success rate.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.
            Optional — enables DL count aggregation.

    Returns:
        DataFrame with columns: rusher_player_id, defteam, season, week,
        carries, yards, tds, epa, avg_dl_count, stacked_box_rate,
        run_gap_success_rate.
        Empty DataFrame if no run plays found.
    """
    if pbp_df is None or pbp_df.empty:
        return pd.DataFrame()

    rushes = _get_run_plays(pbp_df)
    if rushes.empty:
        return pd.DataFrame()

    # Ensure defteam exists
    if "defteam" not in rushes.columns:
        return pd.DataFrame()

    for col, default in [
        ("touchdown", 0),
        ("epa", 0.0),
        ("defenders_in_box", np.nan),
        ("ydstogo", np.nan),
    ]:
        if col not in rushes.columns:
            rushes[col] = default

    rushes["is_stacked_box"] = (rushes["defenders_in_box"] >= 8).astype(float)
    rushes["is_success"] = (rushes["yards_gained"] >= rushes["ydstogo"].fillna(4)).astype(float)

    group_keys = ["rusher_player_id", "defteam", "season", "week"]
    agg = rushes.groupby(group_keys, as_index=False).agg(
        carries=("play_id" if "play_id" in rushes.columns else "yards_gained", "count"),
        yards=("yards_gained", "sum"),
        tds=("touchdown", "sum"),
        epa=("epa", "sum"),
        stacked_box_rate=("is_stacked_box", "mean"),
        run_gap_success_rate=("is_success", "mean"),
    )

    # Add DL count if participation data is available
    if participation_parsed_df is not None and not participation_parsed_df.empty:
        dl_counts = _compute_dl_counts(rushes, participation_parsed_df)
        if not dl_counts.empty:
            rushes_with_dl = rushes.merge(
                dl_counts, on=["game_id", "play_id"], how="left"
            )
            dl_agg = rushes_with_dl.groupby(group_keys, as_index=False).agg(
                avg_dl_count=("dl_count", "mean")
            )
            agg = agg.merge(dl_agg, on=group_keys, how="left")

    if "avg_dl_count" not in agg.columns:
        agg["avg_dl_count"] = np.nan

    logger.info(
        "Built %d RB_VS_DEFENSE edges from %d run plays",
        len(agg),
        len(rushes),
    )
    return agg


# ---------------------------------------------------------------------------
# Neo4j ingestion
# ---------------------------------------------------------------------------


def ingest_rb_matchup_graph(
    graph_db: "GraphDB",
    rb_defense_edges_df: pd.DataFrame,
) -> int:
    """Write RB matchup edges to Neo4j.

    Creates :RB_RUSHES_AGAINST edges (RB -> Team) with rushing aggregates.
    Uses MERGE for idempotent re-runs.

    Args:
        graph_db: Connected GraphDB instance.
        rb_defense_edges_df: Output of build_rb_vs_defense_edges.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected — skipping RB matchup ingestion")
        return 0

    if rb_defense_edges_df.empty:
        return 0

    records = rb_defense_edges_df.to_dict("records")
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        graph_db.run_write(
            "UNWIND $edges AS e "
            "MATCH (rb:Player {gsis_id: e.rusher_player_id}) "
            "MATCH (def:Team {abbr: e.defteam}) "
            "MERGE (rb)-[r:RB_RUSHES_AGAINST {season: e.season, week: e.week}]->(def) "
            "SET r.carries = e.carries, "
            "    r.yards = e.yards, "
            "    r.tds = e.tds, "
            "    r.epa = e.epa, "
            "    r.avg_dl_count = e.avg_dl_count, "
            "    r.stacked_box_rate = e.stacked_box_rate, "
            "    r.run_gap_success_rate = e.run_gap_success_rate",
            {"edges": batch},
        )

    logger.info("Ingested %d RB_RUSHES_AGAINST edges", len(records))
    return len(records)
