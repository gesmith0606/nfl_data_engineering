"""TE coverage mismatch and trailing defense-unit allowance features.

This module has two distinct feature families:

1. Same-game TE matchup aggregates (legacy Neo4j edge helpers):
   ``build_te_coverage_edges``, ``build_te_red_zone_edges``,
   ``build_te_advanced_matchup_features`` — per (TE, defteam, season, week)
   from plays within that week. These are SAME-GAME stats and are excluded
   from model features via ``_SAME_WEEK_PREFIXES`` in
   ``src/player_feature_engineering.py``.

2. Defense-side trailing allowance features (Phase ELITE-2.3 rebuild):
   ``compute_te_def_trailing_features`` — strictly lagged, per (player,
   season, week) rows. Named with ``_trail`` suffix so they pass
   ``_is_unlagged_leak()`` and the empirical leak detector.

   Features computed (all prefixed ``te_def_trail_``):
     yds_per_tgt        — trailing yards/target allowed by defense to TEs overall
     comp_rate          — trailing completion rate allowed to TEs
     td_rate            — trailing TD rate allowed to TEs
     lb_coverage_share  — trailing share of coverage defenders who are LBs
                          (vs CBs/safeties) on TE-targeted pass plays
     cb_coverage_share  — trailing share of coverage defenders who are CBs
                          (favorable matchup indicator; higher = mismatch)

   Data availability note:
     lb_coverage_share / cb_coverage_share require pbp_participation (2020+).
     Other features only require PBP (available back to 2016).
     Features are NaN for seasons < 2020 when participation is absent.

   Window: trailing up to 4 weeks (min_periods=1) in current season, falling
   back to prior-season mean when current-season window < 2 games. Matches
   graph_rb_matchup.py lagging pattern.

Exports:
    build_te_coverage_edges: TE → defense coverage edges (same-game).
    build_te_red_zone_edges: TE → team red zone role edges (same-game).
    build_te_advanced_matchup_features: Additional PBP signal (same-game).
    compute_te_def_trailing_features: Lagged defense-unit allowance features.
    ingest_te_matchup_graph: Write edges to Neo4j.
    TE_DEF_TRAILING_FEATURE_COLUMNS: Canonical list of trailing feature names.
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# Positions treated as linebackers for TE coverage analysis
LB_POSITIONS = {"LB", "ILB", "OLB", "MLB"}

# Positions treated as safeties
SAFETY_POSITIONS = {"S", "SS", "FS"}

# Positions treated as cornerbacks/DBs
CB_POSITIONS = {"CB", "DB"}

# Depth-chart CB positions (granular)
_CB_DEPTH_POSITIONS = {"CB"}

# Seam route threshold
SEAM_ROUTE_AIR_YARDS_THRESHOLD = 10.0

# Heavy rush threshold
HEAVY_RUSH_BOX_THRESHOLD = 7

# Red zone boundary
RED_ZONE_YARDLINE = 20

# Trailing window in weeks
_DEF_TRAIL_WINDOW = 4

# Canonical list of trailing defense-unit feature names
TE_DEF_TRAILING_FEATURE_COLUMNS: List[str] = [
    "te_def_trail_yds_per_tgt",
    "te_def_trail_comp_rate",
    "te_def_trail_td_rate",
    "te_def_trail_lb_coverage_share",
    "te_def_trail_cb_coverage_share",
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


def _compute_def_te_weekly(
    pbp_df: pd.DataFrame,
    te_ids: set,
) -> pd.DataFrame:
    """Aggregate defense TE-allowed stats per (defteam, season, week).

    Args:
        pbp_df: PBP DataFrame (typically filtered to prior weeks).
        te_ids: Set of TE player_id strings.

    Returns:
        DataFrame with defteam/season/week plus weekly TE-allowed aggregates.
    """
    if pbp_df.empty or not te_ids:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & pbp_df["receiver_player_id"].astype(str).isin(te_ids)
    )
    passes = pbp_df[pass_mask].copy()
    if passes.empty:
        return pd.DataFrame()

    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("touchdown", 0),
    ]:
        if col not in passes.columns:
            passes[col] = default
    passes["yards_gained"] = passes["yards_gained"].fillna(0)

    agg = passes.groupby(["defteam", "season", "week"], as_index=False).agg(
        _tgts=("play_id", "count"),
        _comps=("complete_pass", "sum"),
        _yds=("yards_gained", "sum"),
        _tds=("touchdown", "sum"),
    )
    return agg


def _compute_def_te_coverage_weekly(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    te_ids: set,
) -> pd.DataFrame:
    """Compute LB and CB share of coverage defenders on TE-targeted plays.

    Args:
        pbp_df: PBP DataFrame.
        participation_parsed_df: Exploded participation rows.
        te_ids: Set of TE player_id strings.

    Returns:
        DataFrame with defteam/season/week/lb_share_sum/cb_share_sum/play_count.
    """
    if (
        participation_parsed_df is None
        or participation_parsed_df.empty
        or not te_ids
    ):
        return pd.DataFrame()

    # Get TE-targeted pass plays
    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & pbp_df["receiver_player_id"].astype(str).isin(te_ids)
        & pbp_df["defteam"].notna()
        & pbp_df["game_id"].notna()
        & pbp_df["play_id"].notna()
    )
    te_plays = pbp_df[pass_mask][
        ["game_id", "play_id", "defteam", "season", "week"]
    ].drop_duplicates()
    if te_plays.empty:
        return pd.DataFrame()

    # Count LBs on defense per play
    lb_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(LB_POSITIONS)
    )
    cb_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(CB_POSITIONS)
    )
    safety_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(SAFETY_POSITIONS)
    )

    lb_per_play = pd.DataFrame()
    cb_per_play = pd.DataFrame()
    safety_per_play = pd.DataFrame()

    if lb_mask.any():
        lb_per_play = (
            participation_parsed_df[lb_mask]
            .groupby(["game_id", "play_id"], as_index=False)
            .agg(lb_count=("player_gsis_id", "count"))
        )
    if cb_mask.any():
        cb_per_play = (
            participation_parsed_df[cb_mask]
            .groupby(["game_id", "play_id"], as_index=False)
            .agg(cb_count=("player_gsis_id", "count"))
        )
    if safety_mask.any():
        safety_per_play = (
            participation_parsed_df[safety_mask]
            .groupby(["game_id", "play_id"], as_index=False)
            .agg(safety_count=("player_gsis_id", "count"))
        )

    # Merge counts onto TE plays
    merged = te_plays.copy()
    for counts_df, col_name in [
        (lb_per_play, "lb_count"),
        (cb_per_play, "cb_count"),
        (safety_per_play, "safety_count"),
    ]:
        if not counts_df.empty:
            merged = merged.merge(counts_df, on=["game_id", "play_id"], how="left")
        if col_name not in merged.columns:
            merged[col_name] = 0
        merged[col_name] = merged[col_name].fillna(0)

    merged["total_coverage"] = (
        merged["lb_count"] + merged["cb_count"] + merged["safety_count"]
    )

    # Aggregate per (defteam, season, week)
    result = merged.groupby(["defteam", "season", "week"], as_index=False).agg(
        _lb_sum=("lb_count", "sum"),
        _cb_sum=("cb_count", "sum"),
        _total_sum=("total_coverage", "sum"),
        _play_count=("play_id", "count"),
    )
    return result


def _compute_trailing_allowances(
    weekly_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    target_season: int,
    target_week: int,
    window: int = _DEF_TRAIL_WINDOW,
) -> pd.DataFrame:
    """Convert weekly TE-defense allowances to trailing means before target_week.

    Args:
        weekly_df: Output of _compute_def_te_weekly (pre-filtered to prior weeks).
        coverage_df: Output of _compute_def_te_coverage_weekly (pre-filtered).
        target_season: Season being predicted.
        target_week: Week being predicted (exclusive upper bound).
        window: Rolling window in weeks (default 4).

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
        # No current-season-window data yet — fall back to prior-season data
        if prior.empty:
            return pd.DataFrame()
        base = prior
    else:
        # Blend recent + prior so every team has at least some data.
        base = pd.concat([recent, prior], ignore_index=True) if not prior.empty else recent

    result = (
        base.groupby("defteam", as_index=False)
        .agg(
            _tgts=("_tgts", "sum"),
            _comps=("_comps", "sum"),
            _yds=("_yds", "sum"),
            _tds=("_tds", "sum"),
        )
    )
    if result.empty:
        return pd.DataFrame()

    result["te_def_trail_yds_per_tgt"] = np.where(
        result["_tgts"] > 0, result["_yds"] / result["_tgts"], np.nan
    )
    result["te_def_trail_comp_rate"] = np.where(
        result["_tgts"] > 0, result["_comps"] / result["_tgts"], np.nan
    )
    result["te_def_trail_td_rate"] = np.where(
        result["_tgts"] > 0, result["_tds"] / result["_tgts"], np.nan
    )

    # Add coverage shares if available
    if not coverage_df.empty:
        cov_recent = coverage_df[
            (coverage_df["season"] < target_season)
            | (
                (coverage_df["season"] == target_season)
                & (coverage_df["week"] >= target_week - window)
                & (coverage_df["week"] < target_week)
            )
        ]
        if not cov_recent.empty:
            cov_agg = (
                cov_recent.groupby("defteam", as_index=False)
                .agg(
                    __lb_sum=("_lb_sum", "sum"),
                    __cb_sum=("_cb_sum", "sum"),
                    __total_sum=("_total_sum", "sum"),
                )
            )
            cov_agg["te_def_trail_lb_coverage_share"] = np.where(
                cov_agg["__total_sum"] > 0,
                cov_agg["__lb_sum"] / cov_agg["__total_sum"],
                np.nan,
            )
            cov_agg["te_def_trail_cb_coverage_share"] = np.where(
                cov_agg["__total_sum"] > 0,
                cov_agg["__cb_sum"] / cov_agg["__total_sum"],
                np.nan,
            )
            cov_agg = cov_agg.drop(columns=["__lb_sum", "__cb_sum", "__total_sum"])
            result = result.merge(cov_agg, on="defteam", how="left")

    if "te_def_trail_lb_coverage_share" not in result.columns:
        result["te_def_trail_lb_coverage_share"] = np.nan
    if "te_def_trail_cb_coverage_share" not in result.columns:
        result["te_def_trail_cb_coverage_share"] = np.nan

    return result.drop(columns=[c for c in result.columns if c.startswith("_")])


# ---------------------------------------------------------------------------
# Public: trailing defense-unit features (Phase ELITE-2.3)
# ---------------------------------------------------------------------------


def compute_te_def_trailing_features(
    pbp_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
    participation_parsed_df: Optional[pd.DataFrame] = None,
    season: Optional[int] = None,
    window: int = _DEF_TRAIL_WINDOW,
) -> pd.DataFrame:
    """Compute defense-side trailing TE-allowance features per player-week.

    All features are strictly lagged: for a row at (player, season, week=W),
    only data from weeks < W (and prior seasons) is used. Same temporal
    contract as ``graph_rb_matchup._filter_prior_pbp``.

    Feature columns (prefixed ``te_def_trail_``):
        yds_per_tgt         — trailing yards/target allowed to TEs
        comp_rate           — trailing completion rate allowed to TEs
        td_rate             — trailing TD rate allowed to TEs
        lb_coverage_share   — trailing fraction of coverage defenders who are LBs
                              on TE-targeted plays (favorable for TE = high LB share)
        cb_coverage_share   — trailing fraction of coverage defenders who are CBs
                              (mismatch indicator; higher = CB covering big TE)

    Data availability:
        lb/cb_coverage_share require pbp_participation (2020+); NaN pre-2020.
        yds_per_tgt/comp_rate/td_rate only need PBP (available back to 2016).

    Args:
        pbp_df: Full multi-season PBP DataFrame.
        player_weekly_df: Player-weekly Bronze for (season, week) reference.
        rosters_df: Roster DataFrame for TE ID lookup.
            If None, all receivers in PBP are used (looser but not leaked).
        participation_parsed_df: Output of parse_participation_players for
            coverage share features. If None, those features will be NaN.
        season: Target season (optional filter).
        window: Trailing window in weeks (default 4).

    Returns:
        DataFrame with columns: player_id, season, week,
        te_def_trail_yds_per_tgt, te_def_trail_comp_rate,
        te_def_trail_td_rate, te_def_trail_lb_coverage_share,
        te_def_trail_cb_coverage_share.

        Returns empty DataFrame when inputs are insufficient.

    Example:
        >>> feats = compute_te_def_trailing_features(
        ...     pbp_df=pbp, player_weekly_df=pw, rosters_df=rosters,
        ...     participation_parsed_df=parsed, season=2023,
        ... )
        >>> feats.columns.tolist()[:4]
        ['player_id', 'season', 'week', 'te_def_trail_yds_per_tgt']
    """
    if pbp_df is None or pbp_df.empty:
        return pd.DataFrame()
    if player_weekly_df is None or player_weekly_df.empty:
        return pd.DataFrame()

    required_cols = {"season", "week", "play_type", "receiver_player_id", "defteam"}
    if not required_cols.issubset(pbp_df.columns):
        logger.warning(
            "PBP missing required columns for TE def trailing features: %s",
            required_cols - set(pbp_df.columns),
        )
        return pd.DataFrame()

    # Build TE ID set
    te_ids: set = set()
    if rosters_df is not None and not rosters_df.empty and "position" in rosters_df.columns:
        id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
        if id_col in rosters_df.columns:
            te_ids = set(
                rosters_df.loc[rosters_df["position"] == "TE", id_col]
                .astype(str)
                .unique()
            )

    if not te_ids:
        # Fallback: use all receivers (weaker filter)
        te_ids = set(pbp_df["receiver_player_id"].dropna().astype(str).unique())

    # Determine (season, week) pairs
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

    # Pre-compute weekly TE allowances once (full history)
    te_weekly = _compute_def_te_weekly(pbp_df, te_ids)
    if te_weekly.empty:
        logger.warning("No TE weekly defense allowances computed")
        return pd.DataFrame()

    # Pre-compute coverage shares if participation available
    coverage_weekly: pd.DataFrame = pd.DataFrame()
    if participation_parsed_df is not None and not participation_parsed_df.empty:
        coverage_weekly = _compute_def_te_coverage_weekly(
            pbp_df, participation_parsed_df, te_ids
        )

    all_rows = []

    for _, sw_row in season_weeks.iterrows():
        target_season = int(sw_row["season"])
        target_week = int(sw_row["week"])

        if target_week < 2:
            continue

        # Get active TE players this (season, week) + opponents
        active_players = player_weekly_df[
            (player_weekly_df["season"] == target_season)
            & (player_weekly_df["week"] == target_week)
            & player_weekly_df["player_id"].notna()
        ].copy()
        if active_players.empty:
            continue

        if "position" in active_players.columns:
            active_players = active_players[active_players["position"] == "TE"]
        if active_players.empty:
            continue

        # Determine opponent (defteam) for each player
        opp_col = None
        for c in ("opponent_team", "opponent", "defteam"):
            if c in active_players.columns:
                opp_col = c
                break

        if opp_col is None:
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

        # Filter weekly TE allowances to prior data
        prior_weekly = te_weekly[
            (te_weekly["season"] < target_season)
            | (
                (te_weekly["season"] == target_season)
                & (te_weekly["week"] < target_week)
            )
        ]

        prior_coverage = pd.DataFrame()
        if not coverage_weekly.empty:
            prior_coverage = coverage_weekly[
                (coverage_weekly["season"] < target_season)
                | (
                    (coverage_weekly["season"] == target_season)
                    & (coverage_weekly["week"] < target_week)
                )
            ]

        trail_df = _compute_trailing_allowances(
            prior_weekly, prior_coverage, target_season, target_week, window=window
        )
        if trail_df.empty:
            continue

        # Join onto player-opponent map
        player_trail = opp_map.merge(trail_df, on="defteam", how="left")
        player_trail["season"] = target_season
        player_trail["week"] = target_week

        for col in TE_DEF_TRAILING_FEATURE_COLUMNS:
            if col not in player_trail.columns:
                player_trail[col] = np.nan

        all_rows.append(
            player_trail[["player_id", "season", "week"] + TE_DEF_TRAILING_FEATURE_COLUMNS]
        )

    if not all_rows:
        return pd.DataFrame()

    output = pd.concat(all_rows, ignore_index=True)
    output = output.drop_duplicates(subset=["player_id", "season", "week"])

    logger.info(
        "Computed %d TE def trailing feature rows across seasons %s",
        len(output),
        sorted(output["season"].unique()) if not output.empty else [],
    )
    return output


# ---------------------------------------------------------------------------
# Legacy same-game edge construction (Neo4j / graph_feature_extraction.py)
# These remain unchanged; they are excluded from model features via
# _SAME_WEEK_PREFIXES in player_feature_engineering.py.
# ---------------------------------------------------------------------------


def build_te_coverage_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build TE-vs-defense coverage breakdown edges from PBP pass plays.

    NOTE: Same-game stats — for Neo4j ingestion only, not model features.

    Args:
        pbp_df: Play-by-play DataFrame.
        participation_parsed_df: Output of parse_participation_players.
        rosters_df: Roster DataFrame.

    Returns:
        DataFrame with TE aggregate stats per (TE, defteam, season, week).
    """
    if pbp_df.empty or rosters_df.empty:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[pass_mask].copy()
    if passes.empty:
        return pd.DataFrame()

    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set(
        rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
    )
    if not te_ids:
        return pd.DataFrame()

    passes = passes[passes["receiver_player_id"].astype(str).isin(te_ids)].copy()
    if passes.empty:
        return pd.DataFrame()

    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("touchdown", 0),
        ("epa", 0.0),
    ]:
        if col not in passes.columns:
            passes[col] = default

    lb_counts = pd.DataFrame()
    safety_counts = pd.DataFrame()

    if not participation_parsed_df.empty:
        lb_mask = (participation_parsed_df["side"] == "defense") & (
            participation_parsed_df["position"].isin(LB_POSITIONS)
        )
        if lb_mask.any():
            lb_counts = (
                participation_parsed_df[lb_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(lb_count=("player_gsis_id", "count"))
            )

        safety_mask = (participation_parsed_df["side"] == "defense") & (
            participation_parsed_df["position"].isin(SAFETY_POSITIONS)
        )
        if safety_mask.any():
            safety_counts = (
                participation_parsed_df[safety_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(safety_count=("player_gsis_id", "count"))
            )

    if not lb_counts.empty:
        passes = passes.merge(lb_counts, on=["game_id", "play_id"], how="left")
    if "lb_count" not in passes.columns:
        passes["lb_count"] = 0
    passes["lb_count"] = passes["lb_count"].fillna(0)

    if not safety_counts.empty:
        passes = passes.merge(safety_counts, on=["game_id", "play_id"], how="left")
    if "safety_count" not in passes.columns:
        passes["safety_count"] = 0
    passes["safety_count"] = passes["safety_count"].fillna(0)

    group_keys = ["receiver_player_id", "defteam", "season", "week"]
    agg = passes.groupby(group_keys, as_index=False).agg(
        targets=("play_id", "count"),
        catches=("complete_pass", "sum"),
        yards=("yards_gained", "sum"),
        tds=("touchdown", "sum"),
        epa=("epa", "sum"),
        lb_on_field_count=("lb_count", "sum"),
        safety_on_field_count=("safety_count", "sum"),
    )

    total_coverage = agg["lb_on_field_count"] + agg["safety_on_field_count"]
    total_coverage = total_coverage.replace(0, 1)
    agg["lb_coverage_rate"] = agg["lb_on_field_count"] / total_coverage

    logger.info(
        "Built %d TE_TARGETED_AGAINST edges from %d TE pass plays",
        len(agg),
        len(passes),
    )
    return agg


def build_te_red_zone_edges(
    pbp_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build TE red zone role edges from PBP pass plays.

    NOTE: Same-game stats — for Neo4j ingestion only, not model features.

    Args:
        pbp_df: Play-by-play DataFrame.
        rosters_df: Roster DataFrame.

    Returns:
        DataFrame with TE red zone stats per (TE, team, season, week).
    """
    if pbp_df.empty or rosters_df.empty:
        return pd.DataFrame()

    if "yardline_100" not in pbp_df.columns:
        return pd.DataFrame()

    rz_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
        & (pbp_df["yardline_100"] <= 20)
    )
    rz_passes = pbp_df[rz_mask].copy()
    if rz_passes.empty:
        return pd.DataFrame()

    for col, default in [("complete_pass", 0), ("touchdown", 0)]:
        if col not in rz_passes.columns:
            rz_passes[col] = default

    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set(
        rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
    )

    team_col = "posteam" if "posteam" in rz_passes.columns else "home_team"
    team_rz = rz_passes.groupby([team_col, "season", "week"], as_index=False).agg(
        total_team_rz_targets=("play_id", "count"),
    )

    te_passes = rz_passes[rz_passes["receiver_player_id"].astype(str).isin(te_ids)]
    if te_passes.empty:
        return pd.DataFrame()

    group_keys = ["receiver_player_id", team_col, "season", "week"]
    agg = te_passes.groupby(group_keys, as_index=False).agg(
        red_zone_targets=("play_id", "count"),
        red_zone_catches=("complete_pass", "sum"),
        red_zone_tds=("touchdown", "sum"),
    )

    agg = agg.merge(team_rz, on=[team_col, "season", "week"], how="left")
    agg["total_team_rz_targets"] = agg["total_team_rz_targets"].fillna(1)
    agg["red_zone_target_share"] = (
        agg["red_zone_targets"] / agg["total_team_rz_targets"]
    )

    if team_col != "posteam":
        agg = agg.rename(columns={team_col: "posteam"})

    logger.info(
        "Built %d RED_ZONE_ROLE edges from %d red zone TE passes",
        len(agg),
        len(te_passes),
    )
    return agg


def build_te_advanced_matchup_features(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build advanced TE matchup features from PBP columns (no external data).

    NOTE: Same-game stats per (receiver, defteam, season, week) — excluded
    from model features via ``_SAME_WEEK_PREFIXES`` in
    ``src/player_feature_engineering.py``.

    Derives five signals:
        te_matchup_cb_coverage_rate
        te_matchup_seam_route_rate
        te_matchup_seam_completion_rate
        te_matchup_rz_personnel_lb_rate
        te_matchup_blocking_proxy_rate

    Args:
        pbp_df: Play-by-play DataFrame.
        participation_parsed_df: Output of parse_participation_players.
        rosters_df: Roster DataFrame.

    Returns:
        DataFrame with ``te_matchup_*`` columns.
        Returns empty DataFrame if no TE pass plays are found.
    """
    if pbp_df.empty or rosters_df.empty:
        return pd.DataFrame()

    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set(
        rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
    )
    if not te_ids:
        return pd.DataFrame()

    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
        & pbp_df["receiver_player_id"].astype(str).isin(te_ids)
    )
    te_passes = pbp_df[pass_mask].copy()
    if te_passes.empty:
        return pd.DataFrame()

    for col, default in [
        ("complete_pass", 0),
        ("air_yards", np.nan),
        ("pass_location", ""),
        ("yardline_100", np.nan),
        ("defenders_in_box", np.nan),
        ("game_id", ""),
    ]:
        if col not in te_passes.columns:
            te_passes[col] = default

    te_passes["air_yards"] = pd.to_numeric(te_passes["air_yards"], errors="coerce")
    te_passes["defenders_in_box"] = pd.to_numeric(
        te_passes["defenders_in_box"], errors="coerce"
    )
    te_passes["yardline_100"] = pd.to_numeric(
        te_passes["yardline_100"], errors="coerce"
    )

    te_passes["is_seam"] = (te_passes["pass_location"] == "middle") & (
        te_passes["air_yards"] > SEAM_ROUTE_AIR_YARDS_THRESHOLD
    )
    te_passes["is_red_zone"] = te_passes["yardline_100"].le(RED_ZONE_YARDLINE)
    te_passes["is_heavy_box"] = te_passes["defenders_in_box"].ge(HEAVY_RUSH_BOX_THRESHOLD)

    group_keys = ["receiver_player_id", "defteam", "season", "week"]

    lb_counts = pd.DataFrame()
    safety_counts = pd.DataFrame()
    cb_counts = pd.DataFrame()

    if not participation_parsed_df.empty:
        def_mask = participation_parsed_df["side"] == "defense"

        lb_mask = def_mask & participation_parsed_df["position"].isin(LB_POSITIONS)
        if lb_mask.any():
            lb_counts = (
                participation_parsed_df[lb_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(lb_count=("player_gsis_id", "count"))
            )

        safety_mask = def_mask & participation_parsed_df["position"].isin(SAFETY_POSITIONS)
        if safety_mask.any():
            safety_counts = (
                participation_parsed_df[safety_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(safety_count=("player_gsis_id", "count"))
            )

        cb_mask = def_mask & participation_parsed_df["position"].isin(CB_POSITIONS)
        if cb_mask.any():
            cb_counts = (
                participation_parsed_df[cb_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(cb_count=("player_gsis_id", "count"))
            )

    for counts_df, col_name in [
        (lb_counts, "lb_count"),
        (safety_counts, "safety_count"),
        (cb_counts, "cb_count"),
    ]:
        if not counts_df.empty:
            te_passes = te_passes.merge(
                counts_df, on=["game_id", "play_id"], how="left"
            )
        if col_name not in te_passes.columns:
            te_passes[col_name] = np.nan
        te_passes[col_name] = te_passes[col_name].fillna(0)

    agg = te_passes.groupby(group_keys, as_index=False).agg(
        _te_targets=("play_id", "count"),
        _seam_count=("is_seam", "sum"),
        _seam_completions=(
            "complete_pass",
            lambda s: s[te_passes.loc[s.index, "is_seam"]].sum(),
        ),
        _rz_targets=("is_red_zone", "sum"),
        _rz_lb_sum=(
            "lb_count",
            lambda s: s[te_passes.loc[s.index, "is_red_zone"]].sum(),
        ),
        _rz_total_def_sum=(
            "lb_count",
            lambda s: (
                te_passes.loc[s.index, "lb_count"]
                + te_passes.loc[s.index, "safety_count"]
                + te_passes.loc[s.index, "cb_count"]
            )[te_passes.loc[s.index, "is_red_zone"]].sum(),
        ),
        _cb_sum=("cb_count", "sum"),
        _total_coverage_sum=(
            "lb_count",
            lambda s: (
                te_passes.loc[s.index, "lb_count"]
                + te_passes.loc[s.index, "safety_count"]
                + te_passes.loc[s.index, "cb_count"]
            ).sum(),
        ),
        _heavy_box_count=("is_heavy_box", "sum"),
    )

    agg["te_matchup_cb_coverage_rate"] = np.where(
        agg["_total_coverage_sum"] > 0,
        agg["_cb_sum"] / agg["_total_coverage_sum"],
        np.nan,
    )
    agg["te_matchup_seam_route_rate"] = np.where(
        agg["_te_targets"] > 0,
        agg["_seam_count"] / agg["_te_targets"],
        np.nan,
    )
    agg["te_matchup_seam_completion_rate"] = np.where(
        agg["_seam_count"] > 0,
        agg["_seam_completions"] / agg["_seam_count"],
        np.nan,
    )
    agg["te_matchup_rz_personnel_lb_rate"] = np.where(
        agg["_rz_total_def_sum"] > 0,
        agg["_rz_lb_sum"] / agg["_rz_total_def_sum"],
        np.nan,
    )
    agg["te_matchup_blocking_proxy_rate"] = np.where(
        agg["_te_targets"] > 0,
        agg["_heavy_box_count"] / agg["_te_targets"],
        np.nan,
    )

    drop_cols = [c for c in agg.columns if c.startswith("_")]
    agg = agg.drop(columns=drop_cols)

    logger.info(
        "Built %d advanced TE matchup feature rows from %d TE pass plays",
        len(agg),
        len(te_passes),
    )
    return agg


# ---------------------------------------------------------------------------
# Neo4j ingestion
# ---------------------------------------------------------------------------


def ingest_te_matchup_graph(
    graph_db: "GraphDB",
    coverage_edges_df: pd.DataFrame,
    rz_edges_df: Optional[pd.DataFrame] = None,
    advanced_features_df: Optional[pd.DataFrame] = None,
) -> int:
    """Write TE matchup edges to Neo4j.

    Args:
        graph_db: Connected GraphDB instance.
        coverage_edges_df: Output of build_te_coverage_edges.
        rz_edges_df: Output of build_te_red_zone_edges. Optional.
        advanced_features_df: Output of build_te_advanced_matchup_features. Optional.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected -- skipping TE matchup ingestion")
        return 0

    total = 0

    if not coverage_edges_df.empty:
        merge_keys = ["receiver_player_id", "defteam", "season", "week"]
        edges_df = coverage_edges_df.copy()

        if advanced_features_df is not None and not advanced_features_df.empty:
            adv = advanced_features_df[
                [
                    c
                    for c in advanced_features_df.columns
                    if c in merge_keys or c.startswith("te_matchup_")
                ]
            ]
            edges_df = edges_df.merge(adv, on=merge_keys, how="left")

        records = edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (te:Player {gsis_id: e.receiver_player_id}) "
                "MATCH (def:Team {abbr: e.defteam}) "
                "MERGE (te)-[r:TE_TARGETED_AGAINST {season: e.season, week: e.week}]->(def) "
                "SET r.targets = e.targets, r.catches = e.catches, r.yards = e.yards, "
                "    r.tds = e.tds, r.epa = e.epa, "
                "    r.lb_on_field_count = e.lb_on_field_count, "
                "    r.safety_on_field_count = e.safety_on_field_count, "
                "    r.lb_coverage_rate = e.lb_coverage_rate",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d TE_TARGETED_AGAINST edges", len(records))

    if rz_edges_df is not None and not rz_edges_df.empty:
        records = rz_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (te:Player {gsis_id: e.receiver_player_id}) "
                "MATCH (tm:Team {abbr: e.posteam}) "
                "MERGE (te)-[r:RED_ZONE_ROLE {season: e.season, week: e.week}]->(tm) "
                "SET r.red_zone_targets = e.red_zone_targets, "
                "    r.total_team_rz_targets = e.total_team_rz_targets, "
                "    r.red_zone_target_share = e.red_zone_target_share, "
                "    r.red_zone_catches = e.red_zone_catches, "
                "    r.red_zone_tds = e.red_zone_tds",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d RED_ZONE_ROLE edges", len(records))

    return total
