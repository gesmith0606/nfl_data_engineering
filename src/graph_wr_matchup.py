"""WR-vs-Defense edge construction and trailing defense-unit allowance features.

This module has two distinct feature families:

1. Same-game WR matchup aggregates (legacy Neo4j edge helpers):
   ``build_targeted_against_edges``, ``build_on_field_with_edges``,
   ``build_wr_advanced_matchup_features`` — per (WR, defteam, season, week)
   from plays within that week. These are SAME-GAME stats and are excluded
   from model features via ``_SAME_WEEK_PREFIXES`` in
   ``src/player_feature_engineering.py``.

2. Defense-side trailing allowance features (Phase ELITE-2.3 rebuild):
   ``compute_wr_def_trailing_features`` — strictly lagged, per (player,
   season, week) rows. Named with ``_trail`` suffix so they pass
   ``_is_unlagged_leak()`` and the empirical leak detector.

   Features computed (all prefixed ``wr_def_trail_``):
     yds_per_tgt        — trailing yards/target allowed by that defense to WRs
     yds_per_tgt_outside — trailing y/t on outside routes (left+right pass_location)
     yds_per_tgt_slot   — trailing y/t on slot routes (middle pass_location)
     comp_rate          — trailing completion rate allowed to WRs
     td_rate            — trailing TD rate (TDs / targets) allowed to WRs
     cb_count_per_play  — trailing avg CBs per pass play from participation

   Data availability note:
     pbp_participation (defense_players) is present 2020–2025; features are
     NaN for seasons < 2020. rosters/depth_charts are committed Bronze (TD-08).
     cb_count_per_play requires participation; other features only require PBP.

   Window: trailing up to 4 weeks (min_periods=1) in current season, falling
   back to prior-season mean when current-season window < 2 games. This matches
   the graph_rb_matchup.py pattern.

Exports:
    build_targeted_against_edges: WR → defense aggregate edges (same-game).
    build_on_field_with_edges: WR ↔ CB co-occurrence edges (same-game).
    build_wr_advanced_matchup_features: Additional signal from PBP (same-game).
    compute_wr_def_trailing_features: Lagged defense-unit allowance features.
    ingest_wr_matchup_graph: Write edges to Neo4j.
    WR_DEF_TRAILING_FEATURE_COLUMNS: Canonical list of trailing feature names.
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# Air yards threshold below which pass is considered short (press coverage proxy)
SHORT_AIR_YARDS_THRESHOLD = 5.0

# defenders_in_box thresholds for coverage shell inference.
LIGHT_BOX_THRESHOLD = 6
HEAVY_BOX_THRESHOLD = 7

# Trailing window in weeks for defense-allowance computation
_DEF_TRAIL_WINDOW = 4

# DB depth_chart positions treated as cornerbacks
_CB_DEPTH_POSITIONS = {"CB"}

# DB depth_chart positions treated as safeties
_SAFETY_DEPTH_POSITIONS = {"FS", "SS", "S"}

# All DB positions (broad) — used when depth_chart detail unavailable
_DB_POSITIONS = {"DB", "CB"}

# Canonical list of trailing defense-unit feature names
WR_DEF_TRAILING_FEATURE_COLUMNS: List[str] = [
    "wr_def_trail_yds_per_tgt",
    "wr_def_trail_yds_per_tgt_outside",
    "wr_def_trail_yds_per_tgt_slot",
    "wr_def_trail_comp_rate",
    "wr_def_trail_td_rate",
    "wr_def_trail_cb_count_per_play",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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
    same_season_prior_week = (pbp_df["season"] == target_season) & (
        pbp_df["week"] < target_week
    )
    return pbp_df[prior_season_mask | same_season_prior_week].copy()


def _build_defender_cb_map(
    rosters_df: pd.DataFrame,
) -> pd.Series:
    """Build a player_id → is_cb boolean Series from rosters.

    Uses depth_chart_position (CB) when available; falls back to position == 'DB'.

    Args:
        rosters_df: Roster DataFrame with player_id, position, depth_chart_position.

    Returns:
        Series keyed on player_id (str), True = CB/corner.
    """
    if rosters_df is None or rosters_df.empty:
        return pd.Series(dtype=bool)
    df = rosters_df.copy()
    df["player_id"] = df["player_id"].astype(str)
    # Use depth_chart_position if available, else fall back to position
    if "depth_chart_position" in df.columns:
        mask = df["depth_chart_position"].isin(_CB_DEPTH_POSITIONS)
    else:
        mask = df["position"].isin(_DB_POSITIONS)
    return df.loc[mask, "player_id"].drop_duplicates()


def _compute_def_wr_weekly(
    pbp_df: pd.DataFrame,
    wr_ids: set,
) -> pd.DataFrame:
    """Aggregate defense WR-allowed stats per (defteam, season, week).

    Computes targets, yards, completions, TDs, slot targets, outside yards, slot yards.

    Args:
        pbp_df: PBP DataFrame (typically already filtered to prior weeks).
        wr_ids: Set of WR player_id strings.

    Returns:
        DataFrame with defteam/season/week plus weekly allowance aggregates.
    """
    if pbp_df.empty or not wr_ids:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & pbp_df["receiver_player_id"].astype(str).isin(wr_ids)
    )
    passes = pbp_df[pass_mask].copy()
    if passes.empty:
        return pd.DataFrame()

    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("touchdown", 0),
        ("pass_location", ""),
    ]:
        if col not in passes.columns:
            passes[col] = default
    passes["yards_gained"] = passes["yards_gained"].fillna(0)

    passes["is_slot"] = passes["pass_location"] == "middle"
    passes["is_outside"] = passes["pass_location"].isin(["left", "right"])

    agg = passes.groupby(["defteam", "season", "week"], as_index=False).agg(
        _tgts=("play_id", "count"),
        _comps=("complete_pass", "sum"),
        _yds=("yards_gained", "sum"),
        _tds=("touchdown", "sum"),
        _slot_tgts=("is_slot", "sum"),
        _outside_tgts=("is_outside", "sum"),
        _outside_yds=(
            "yards_gained",
            lambda s: passes.loc[s.index, "yards_gained"][
                passes.loc[s.index, "is_outside"]
            ].sum(),
        ),
        _slot_yds=(
            "yards_gained",
            lambda s: passes.loc[s.index, "yards_gained"][
                passes.loc[s.index, "is_slot"]
            ].sum(),
        ),
    )
    return agg


def _compute_def_cb_count_weekly(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    cb_ids: set,
) -> pd.DataFrame:
    """Compute average CBs per pass play per (defteam, season, week).

    Args:
        pbp_df: PBP DataFrame.
        participation_parsed_df: Exploded participation rows.
        cb_ids: Set of confirmed CB player_id strings.

    Returns:
        DataFrame with defteam/season/week/avg_cb_per_play.
    """
    if (
        participation_parsed_df is None
        or participation_parsed_df.empty
        or not cb_ids
    ):
        return pd.DataFrame()

    # Get pass plays (game_id, play_id, defteam) from PBP
    pass_plays = pbp_df[
        (pbp_df["play_type"] == "pass")
        & pbp_df["defteam"].notna()
        & pbp_df["game_id"].notna()
        & pbp_df["play_id"].notna()
    ][["game_id", "play_id", "defteam", "season", "week"]].drop_duplicates()
    if pass_plays.empty:
        return pd.DataFrame()

    # Count CBs on defense per play from participation
    def_rows = participation_parsed_df[
        (participation_parsed_df["side"] == "defense")
        & participation_parsed_df["player_gsis_id"].astype(str).isin(cb_ids)
    ]
    if def_rows.empty:
        return pd.DataFrame()

    cb_per_play = (
        def_rows.groupby(["game_id", "play_id"], as_index=False)
        .agg(cb_count=("player_gsis_id", "count"))
    )

    # Join onto pass plays
    merged = pass_plays.merge(cb_per_play, on=["game_id", "play_id"], how="left")
    merged["cb_count"] = merged["cb_count"].fillna(0)

    result = (
        merged.groupby(["defteam", "season", "week"], as_index=False)
        .agg(avg_cb_per_play=("cb_count", "mean"))
    )
    return result


def _compute_trailing_allowances(
    weekly_df: pd.DataFrame,
    target_season: int,
    target_week: int,
    window: int = _DEF_TRAIL_WINDOW,
) -> pd.DataFrame:
    """Convert weekly defense allowances to trailing means before target_week.

    Uses up to ``window`` recent weeks in target_season; falls back to
    prior-season mean when fewer than 2 games are in the current window.

    Args:
        weekly_df: Output of _compute_def_wr_weekly (pre-filtered to prior weeks).
        target_season: Season being predicted.
        target_week: Week being predicted (exclusive upper bound).
        window: Rolling window size in weeks.

    Returns:
        DataFrame with defteam and trailing rate columns.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    # Current-season recent window
    recent = weekly_df[
        (weekly_df["season"] == target_season)
        & (weekly_df["week"] >= target_week - window)
        & (weekly_df["week"] < target_week)
    ]

    prior = weekly_df[weekly_df["season"] < target_season]

    if recent.empty:
        # No current-season-window data yet — fall back to all prior-season data
        if prior.empty:
            return pd.DataFrame()
        base = prior
    else:
        # Blend recent + prior so every team has at least some data.
        # (The nunique < 5 check was too strict for early-season weeks.)
        base = pd.concat([recent, prior], ignore_index=True) if not prior.empty else recent

    result = (
        base.groupby("defteam", as_index=False)
        .agg(
            _tgts=("_tgts", "sum"),
            _comps=("_comps", "sum"),
            _yds=("_yds", "sum"),
            _tds=("_tds", "sum"),
            _slot_tgts=("_slot_tgts", "sum"),
            _outside_tgts=("_outside_tgts", "sum"),
            _outside_yds=("_outside_yds", "sum"),
            _slot_yds=("_slot_yds", "sum"),
        )
    )
    if result.empty:
        return pd.DataFrame()

    result["wr_def_trail_yds_per_tgt"] = np.where(
        result["_tgts"] > 0, result["_yds"] / result["_tgts"], np.nan
    )
    result["wr_def_trail_comp_rate"] = np.where(
        result["_tgts"] > 0, result["_comps"] / result["_tgts"], np.nan
    )
    result["wr_def_trail_td_rate"] = np.where(
        result["_tgts"] > 0, result["_tds"] / result["_tgts"], np.nan
    )
    result["wr_def_trail_yds_per_tgt_outside"] = np.where(
        result["_outside_tgts"] > 0,
        result["_outside_yds"] / result["_outside_tgts"],
        np.nan,
    )
    result["wr_def_trail_yds_per_tgt_slot"] = np.where(
        result["_slot_tgts"] > 0,
        result["_slot_yds"] / result["_slot_tgts"],
        np.nan,
    )
    return result.drop(
        columns=[c for c in result.columns if c.startswith("_")]
    )


# ---------------------------------------------------------------------------
# Public: trailing defense-unit features (Phase ELITE-2.3)
# ---------------------------------------------------------------------------


def compute_wr_def_trailing_features(
    pbp_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
    participation_parsed_df: Optional[pd.DataFrame] = None,
    season: Optional[int] = None,
    window: int = _DEF_TRAIL_WINDOW,
) -> pd.DataFrame:
    """Compute defense-side trailing WR-allowance features per player-week.

    All features are strictly lagged: for a row at (player, season, week=W),
    only data from weeks < W (and prior seasons) is used. This enforces the
    same temporal contract as ``graph_rb_matchup._filter_prior_pbp``.

    Feature columns (prefixed ``wr_def_trail_``):
        yds_per_tgt        — trailing yards/target allowed to WRs overall
        yds_per_tgt_outside — trailing y/t on outside routes (left/right)
        yds_per_tgt_slot   — trailing y/t on slot routes (middle location)
        comp_rate          — trailing completion rate allowed to WRs
        td_rate            — trailing TD rate allowed to WRs
        cb_count_per_play  — trailing avg CBs per pass play (participation)

    Data availability:
        cb_count_per_play requires pbp_participation (2020+); NaN pre-2020.
        Other features only need PBP (available back to 2016).

    Args:
        pbp_df: Full multi-season PBP DataFrame.
        player_weekly_df: Player-weekly Bronze for (season, week) reference.
        rosters_df: Roster DataFrame for WR ID lookup + CB identification.
            If None, WR filter uses PBP receiver_player_id for all passes
            (looser but not leaked).
        participation_parsed_df: Output of parse_participation_players for
            CB count feature. If None, cb_count_per_play will be NaN.
        season: Target season (optional filter). If None, computes for all
            seasons in pbp_df.
        window: Trailing window in weeks (default 4).

    Returns:
        DataFrame with columns: player_id, season, week,
        wr_def_trail_yds_per_tgt, wr_def_trail_yds_per_tgt_outside,
        wr_def_trail_yds_per_tgt_slot, wr_def_trail_comp_rate,
        wr_def_trail_td_rate, wr_def_trail_cb_count_per_play.

        Returns empty DataFrame when inputs are insufficient.

    Example:
        >>> feats = compute_wr_def_trailing_features(
        ...     pbp_df=pbp, player_weekly_df=pw, rosters_df=rosters,
        ...     participation_parsed_df=parsed, season=2023,
        ... )
        >>> feats.columns.tolist()[:4]
        ['player_id', 'season', 'week', 'wr_def_trail_yds_per_tgt']
    """
    if pbp_df is None or pbp_df.empty:
        return pd.DataFrame()
    if player_weekly_df is None or player_weekly_df.empty:
        return pd.DataFrame()

    required_cols = {"season", "week", "play_type", "receiver_player_id", "defteam"}
    if not required_cols.issubset(pbp_df.columns):
        logger.warning(
            "PBP missing required columns for WR def trailing features: %s",
            required_cols - set(pbp_df.columns),
        )
        return pd.DataFrame()

    # Build WR ID set from rosters
    wr_ids: set = set()
    if rosters_df is not None and not rosters_df.empty and "position" in rosters_df.columns:
        id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
        if id_col in rosters_df.columns:
            wr_ids = set(
                rosters_df.loc[rosters_df["position"] == "WR", id_col]
                .astype(str)
                .unique()
            )

    # Build CB ID set from rosters for cb_count_per_play
    cb_ids: set = set()
    if rosters_df is not None and not rosters_df.empty:
        cb_series = _build_defender_cb_map(rosters_df)
        cb_ids = set(cb_series.astype(str).unique())

    # Determine (season, week) pairs to process
    if season is not None:
        season_weeks = (
            player_weekly_df[player_weekly_df["season"] == season][["season", "week"]]
            .drop_duplicates()
            .sort_values(["season", "week"])
        )
    else:
        season_weeks = (
            player_weekly_df[["season", "week"]]
            .drop_duplicates()
            .sort_values(["season", "week"])
        )

    # Pre-compute weekly WR allowances across all prior data (batched once)
    # to avoid re-filtering PBP each iteration
    # Note: wr_ids may be season-specific; use all-pass filter as fallback
    if wr_ids:
        wr_weekly = _compute_def_wr_weekly(pbp_df, wr_ids)
    else:
        # No roster filter — use all receivers as WR proxy
        wr_weekly = _compute_def_wr_weekly(
            pbp_df,
            set(pbp_df["receiver_player_id"].dropna().astype(str).unique()),
        )

    if wr_weekly.empty:
        logger.warning("No WR weekly defense allowances computed")
        return pd.DataFrame()

    # Pre-compute CB count weekly if participation available
    cb_weekly: pd.DataFrame = pd.DataFrame()
    if participation_parsed_df is not None and not participation_parsed_df.empty and cb_ids:
        cb_weekly = _compute_def_cb_count_weekly(pbp_df, participation_parsed_df, cb_ids)

    all_rows = []

    for _, sw_row in season_weeks.iterrows():
        target_season = int(sw_row["season"])
        target_week = int(sw_row["week"])

        # Skip week 1 — no prior data in-season
        if target_week < 2:
            continue

        # Get active WR/receiver players this (season, week) and their opponents
        active_players = player_weekly_df[
            (player_weekly_df["season"] == target_season)
            & (player_weekly_df["week"] == target_week)
            & player_weekly_df["player_id"].notna()
        ].copy()
        if active_players.empty:
            continue

        # Filter to WR position if position is available
        if "position" in active_players.columns:
            active_players = active_players[active_players["position"] == "WR"]
        if active_players.empty:
            continue

        # Determine opponent for each WR (needed to look up trailing defense stats)
        # player_weekly should have opponent_team or recent_team; we need defteam
        opp_col = None
        for c in ("opponent_team", "opponent", "defteam"):
            if c in active_players.columns:
                opp_col = c
                break

        if opp_col is None:
            # Fall back: get defteam from PBP
            opp_map = (
                pbp_df[
                    (pbp_df["season"] == target_season)
                    & (pbp_df["week"] == target_week)
                    & (pbp_df["play_type"] == "pass")
                    & pbp_df["receiver_player_id"].notna()
                    & pbp_df["defteam"].notna()
                ][["receiver_player_id", "defteam"]]
                .rename(columns={"receiver_player_id": "player_id"})
                .drop_duplicates(subset=["player_id"], keep="last")
            )
            opp_map["player_id"] = opp_map["player_id"].astype(str)
        else:
            opp_map = (
                active_players[["player_id", opp_col]]
                .rename(columns={opp_col: "defteam"})
                .copy()
            )
            opp_map["player_id"] = opp_map["player_id"].astype(str)

        if opp_map.empty:
            continue

        # Filter weekly allowances to prior data
        prior_weekly = wr_weekly[
            (wr_weekly["season"] < target_season)
            | (
                (wr_weekly["season"] == target_season)
                & (wr_weekly["week"] < target_week)
            )
        ]

        # Compute trailing allowances per defteam
        trail_df = _compute_trailing_allowances(
            prior_weekly, target_season, target_week, window=window
        )
        if trail_df.empty:
            continue

        # Optionally join CB count per play
        if not cb_weekly.empty:
            prior_cb = cb_weekly[
                (cb_weekly["season"] < target_season)
                | (
                    (cb_weekly["season"] == target_season)
                    & (cb_weekly["week"] < target_week)
                )
            ]
            if not prior_cb.empty:
                cb_recent = prior_cb[
                    (prior_cb["season"] == target_season)
                    & (prior_cb["week"] >= target_week - window)
                ]
                if cb_recent.empty and not prior_cb.empty:
                    cb_recent = prior_cb[prior_cb["season"] < target_season]
                if not cb_recent.empty:
                    cb_trail = (
                        cb_recent.groupby("defteam", as_index=False)
                        .agg(wr_def_trail_cb_count_per_play=("avg_cb_per_play", "mean"))
                    )
                    trail_df = trail_df.merge(cb_trail, on="defteam", how="left")

        if "wr_def_trail_cb_count_per_play" not in trail_df.columns:
            trail_df["wr_def_trail_cb_count_per_play"] = np.nan

        # Join trail_df onto opp_map to get per-player features
        player_trail = opp_map.merge(trail_df, on="defteam", how="left")
        player_trail["season"] = target_season
        player_trail["week"] = target_week

        # Keep only columns we need
        keep_cols = ["player_id", "season", "week"] + [
            c for c in WR_DEF_TRAILING_FEATURE_COLUMNS if c in player_trail.columns
        ]
        for col in WR_DEF_TRAILING_FEATURE_COLUMNS:
            if col not in player_trail.columns:
                player_trail[col] = np.nan

        all_rows.append(player_trail[["player_id", "season", "week"] + WR_DEF_TRAILING_FEATURE_COLUMNS])

    if not all_rows:
        return pd.DataFrame()

    output = pd.concat(all_rows, ignore_index=True)
    output = output.drop_duplicates(subset=["player_id", "season", "week"])

    logger.info(
        "Computed %d WR def trailing feature rows across seasons %s",
        len(output),
        sorted(output["season"].unique()) if not output.empty else [],
    )
    return output


# ---------------------------------------------------------------------------
# Legacy same-game edge construction (Neo4j / graph_feature_extraction.py)
# These remain unchanged from the original module; they are excluded from
# model features via _SAME_WEEK_PREFIXES in player_feature_engineering.py.
# ---------------------------------------------------------------------------


def build_wr_advanced_matchup_features(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build advanced WR matchup features from PBP columns (no external data).

    NOTE: These are same-game outcome stats per (receiver, defteam, season, week)
    and are EXCLUDED from model features (same-game leak). See
    ``_SAME_WEEK_PREFIXES`` in ``src/player_feature_engineering.py``.

    Derives nine signals per (receiver_player_id, defteam, season, week):
        wr_matchup_target_concentration
        wr_matchup_air_yards_per_target
        wr_matchup_completed_air_yards_per_target
        wr_matchup_yac_per_catch
        wr_matchup_light_box_epa
        wr_matchup_heavy_box_epa
        wr_matchup_short_pass_completion_rate
        wr_matchup_middle_target_rate
        wr_matchup_middle_epa

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.

    Returns:
        DataFrame with ``wr_matchup_*`` columns.
        Returns empty DataFrame if no pass plays are found.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[pass_mask].copy()
    if passes.empty:
        return pd.DataFrame()

    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("epa", 0.0),
        ("air_yards", np.nan),
        ("yards_after_catch", np.nan),
        ("pass_location", ""),
        ("defenders_in_box", np.nan),
    ]:
        if col not in passes.columns:
            passes[col] = default

    passes["air_yards"] = pd.to_numeric(passes["air_yards"], errors="coerce")
    passes["yards_after_catch"] = pd.to_numeric(
        passes["yards_after_catch"], errors="coerce"
    )
    passes["defenders_in_box"] = pd.to_numeric(
        passes["defenders_in_box"], errors="coerce"
    )

    passes["completed_air_yards"] = passes["air_yards"] * passes["complete_pass"]
    passes["is_light_box"] = passes["defenders_in_box"].le(LIGHT_BOX_THRESHOLD)
    passes["is_heavy_box"] = passes["defenders_in_box"].ge(HEAVY_BOX_THRESHOLD)
    passes["is_short_pass"] = passes["air_yards"].lt(SHORT_AIR_YARDS_THRESHOLD)
    passes["is_middle"] = passes["pass_location"] == "middle"

    group_keys = ["receiver_player_id", "defteam", "season", "week"]

    team_targets = passes.groupby(
        ["posteam", "defteam", "season", "week"], as_index=False
    ).agg(team_targets=("play_id", "count"))

    agg = passes.groupby(group_keys, as_index=False).agg(
        _wr_targets=("play_id", "count"),
        _catches=("complete_pass", "sum"),
        _air_yards_sum=("air_yards", "sum"),
        _completed_air_yards_sum=("completed_air_yards", "sum"),
        _yac_sum=("yards_after_catch", "sum"),
        _yac_count=("yards_after_catch", "count"),
        _light_box_epa_sum=(
            "epa",
            lambda s: s[passes.loc[s.index, "is_light_box"]].sum(),
        ),
        _light_box_count=("is_light_box", "sum"),
        _heavy_box_epa_sum=(
            "epa",
            lambda s: s[passes.loc[s.index, "is_heavy_box"]].sum(),
        ),
        _heavy_box_count=("is_heavy_box", "sum"),
        _short_pass_completions=(
            "complete_pass",
            lambda s: s[passes.loc[s.index, "is_short_pass"]].sum(),
        ),
        _short_pass_count=("is_short_pass", "sum"),
        _middle_count=("is_middle", "sum"),
        _middle_epa_sum=(
            "epa",
            lambda s: s[passes.loc[s.index, "is_middle"]].sum(),
        ),
    )

    agg["wr_matchup_air_yards_per_target"] = np.where(
        agg["_wr_targets"] > 0,
        agg["_air_yards_sum"] / agg["_wr_targets"],
        np.nan,
    )
    agg["wr_matchup_completed_air_yards_per_target"] = np.where(
        agg["_wr_targets"] > 0,
        agg["_completed_air_yards_sum"] / agg["_wr_targets"],
        np.nan,
    )
    agg["wr_matchup_yac_per_catch"] = np.where(
        agg["_catches"] > 0,
        agg["_yac_sum"] / agg["_catches"],
        np.nan,
    )
    agg["wr_matchup_light_box_epa"] = np.where(
        agg["_light_box_count"] > 0,
        agg["_light_box_epa_sum"] / agg["_light_box_count"],
        np.nan,
    )
    agg["wr_matchup_heavy_box_epa"] = np.where(
        agg["_heavy_box_count"] > 0,
        agg["_heavy_box_epa_sum"] / agg["_heavy_box_count"],
        np.nan,
    )
    agg["wr_matchup_short_pass_completion_rate"] = np.where(
        agg["_short_pass_count"] > 0,
        agg["_short_pass_completions"] / agg["_short_pass_count"],
        np.nan,
    )
    agg["wr_matchup_middle_target_rate"] = np.where(
        agg["_wr_targets"] > 0,
        agg["_middle_count"] / agg["_wr_targets"],
        np.nan,
    )
    agg["wr_matchup_middle_epa"] = np.where(
        agg["_middle_count"] > 0,
        agg["_middle_epa_sum"] / agg["_middle_count"],
        np.nan,
    )

    wr_posteam = passes[group_keys + ["posteam"]].drop_duplicates(
        subset=group_keys, keep="last"
    )
    agg = agg.merge(wr_posteam, on=group_keys, how="left")
    agg = agg.merge(
        team_targets, on=["posteam", "defteam", "season", "week"], how="left"
    )
    agg["wr_matchup_target_concentration"] = np.where(
        agg["team_targets"].gt(0),
        agg["_wr_targets"] / agg["team_targets"],
        np.nan,
    )

    drop_cols = [
        c for c in agg.columns if c.startswith("_") or c in ("posteam", "team_targets")
    ]
    agg = agg.drop(columns=drop_cols)

    logger.info(
        "Built %d advanced WR matchup feature rows from %d pass plays",
        len(agg),
        len(passes),
    )
    return agg


def build_targeted_against_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build WR-vs-defense aggregate edges from PBP pass plays.

    NOTE: Same-game stats — for Neo4j ingestion only, not model features.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.

    Returns:
        DataFrame with WR aggregate stats per (receiver, defteam, season, week).
    """
    if pbp_df.empty:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[pass_mask].copy()
    if passes.empty:
        return pd.DataFrame()

    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("touchdown", 0),
        ("epa", 0.0),
        ("air_yards", 0.0),
        ("pass_location", ""),
    ]:
        if col not in passes.columns:
            passes[col] = default

    passes["is_left"] = (passes["pass_location"] == "left").astype(int)
    passes["is_middle"] = (passes["pass_location"] == "middle").astype(int)
    passes["is_right"] = (passes["pass_location"] == "right").astype(int)

    group_keys = ["receiver_player_id", "defteam", "season", "week"]
    agg = passes.groupby(group_keys, as_index=False).agg(
        targets=("play_id", "count"),
        catches=("complete_pass", "sum"),
        yards=("yards_gained", "sum"),
        tds=("touchdown", "sum"),
        epa=("epa", "sum"),
        air_yards=("air_yards", "sum"),
        pass_left_count=("is_left", "sum"),
        pass_mid_count=("is_middle", "sum"),
        pass_right_count=("is_right", "sum"),
    )

    total = agg["pass_left_count"] + agg["pass_mid_count"] + agg["pass_right_count"]
    total = total.replace(0, 1)
    agg["pass_left_rate"] = agg["pass_left_count"] / total
    agg["pass_mid_rate"] = agg["pass_mid_count"] / total
    agg["pass_right_rate"] = agg["pass_right_count"] / total
    agg = agg.drop(columns=["pass_left_count", "pass_mid_count", "pass_right_count"])

    logger.info(
        "Built %d TARGETED_AGAINST edges from %d pass plays",
        len(agg),
        len(passes),
    )
    return agg


def build_on_field_with_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build WR-CB co-occurrence edges from PBP pass plays.

    NOTE: Same-game stats — for Neo4j ingestion only, not model features.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.

    Returns:
        DataFrame with WR-CB co-occurrence per (WR, CB, season, week).
    """
    if pbp_df.empty or participation_parsed_df.empty:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[pass_mask][
        ["game_id", "play_id", "receiver_player_id", "season", "week", "yards_gained"]
    ].copy()
    if passes.empty:
        return pd.DataFrame()

    passes["yards_gained"] = passes["yards_gained"].fillna(0)

    from graph_participation import CB_POSITIONS

    cb_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(CB_POSITIONS)
    )
    cbs = participation_parsed_df[cb_mask][
        ["game_id", "play_id", "player_gsis_id"]
    ].rename(columns={"player_gsis_id": "cb_player_id"})

    if cbs.empty:
        return pd.DataFrame()

    merged = passes.merge(cbs, on=["game_id", "play_id"], how="inner")
    merged = merged.rename(columns={"receiver_player_id": "wr_player_id"})

    if merged.empty:
        return pd.DataFrame()

    agg = merged.groupby(
        ["wr_player_id", "cb_player_id", "season", "week"], as_index=False
    ).agg(
        snap_count=("play_id", "count"),
        targets_during=("play_id", "count"),
        yards_during=("yards_gained", "sum"),
    )

    logger.info(
        "Built %d ON_FIELD_WITH edges from %d pass-play x CB rows",
        len(agg),
        len(merged),
    )
    return agg


# ---------------------------------------------------------------------------
# Neo4j ingestion
# ---------------------------------------------------------------------------


def ingest_wr_matchup_graph(
    graph_db: "GraphDB",
    targeted_edges_df: pd.DataFrame,
    cooccurrence_edges_df: Optional[pd.DataFrame] = None,
    advanced_features_df: Optional[pd.DataFrame] = None,
) -> int:
    """Write WR matchup edges to Neo4j.

    Args:
        graph_db: Connected GraphDB instance.
        targeted_edges_df: Output of build_targeted_against_edges.
        cooccurrence_edges_df: Output of build_on_field_with_edges. Optional.
        advanced_features_df: Output of build_wr_advanced_matchup_features.
            Optional.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected -- skipping WR matchup ingestion")
        return 0

    total = 0

    if not targeted_edges_df.empty:
        merge_keys = ["receiver_player_id", "defteam", "season", "week"]
        edges_df = targeted_edges_df.copy()

        if advanced_features_df is not None and not advanced_features_df.empty:
            adv = advanced_features_df[
                [
                    c
                    for c in advanced_features_df.columns
                    if c in merge_keys or c.startswith("wr_matchup_")
                ]
            ]
            edges_df = edges_df.merge(adv, on=merge_keys, how="left")

        records = edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (wr:Player {gsis_id: e.receiver_player_id}) "
                "MATCH (def:Team {abbr: e.defteam}) "
                "MERGE (wr)-[r:TARGETED_AGAINST {season: e.season, week: e.week}]->(def) "
                "SET r.targets = e.targets, r.catches = e.catches, r.yards = e.yards, "
                "    r.tds = e.tds, r.epa = e.epa, r.air_yards = e.air_yards",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d TARGETED_AGAINST edges", len(records))

    if cooccurrence_edges_df is not None and not cooccurrence_edges_df.empty:
        records = cooccurrence_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (wr:Player {gsis_id: e.wr_player_id}) "
                "MATCH (cb:Player {gsis_id: e.cb_player_id}) "
                "MERGE (wr)-[r:ON_FIELD_WITH {season: e.season, week: e.week}]->(cb) "
                "SET r.snap_count = e.snap_count, r.targets_during = e.targets_during, "
                "    r.yards_during = e.yards_during",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d ON_FIELD_WITH edges", len(records))

    return total
