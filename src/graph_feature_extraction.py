"""Graph-derived feature extraction for player-week predictions.

Queries the Neo4j graph to extract injury cascade features per player-week.
All features use strict temporal lag — only data from weeks prior to the
current week is used.

When Neo4j is unavailable, returns empty DataFrames and logs a warning
(graceful degradation).

Exports:
    extract_injury_cascade_features: Per-player-week graph features for one team/week.
    extract_all_graph_features: Batch extraction across seasons.
    compute_graph_features_from_data: Pure-pandas fallback (no Neo4j required).
"""

import datetime
import glob
import logging
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")
GRAPH_FEATURES_DIR = os.path.join(SILVER_DIR, "graph_features")

# Output columns from graph feature extraction
GRAPH_FEATURE_COLUMNS = [
    "injury_cascade_target_boost",
    "injury_cascade_carry_boost",
    "teammate_injured_starter",
    "historical_absorption_rate",
]


def _read_bronze_parquet(subdir: str, season: int) -> pd.DataFrame:
    """Read latest Bronze parquet for a subdirectory and season."""
    pattern = os.path.join(BRONZE_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        pattern_w = os.path.join(
            BRONZE_DIR, subdir, f"season={season}", "week=*", "*.parquet"
        )
        files_w = sorted(glob.glob(pattern_w))
        if files_w:
            return pd.concat([pd.read_parquet(f) for f in files_w], ignore_index=True)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


# ---------------------------------------------------------------------------
# Neo4j-based extraction
# ---------------------------------------------------------------------------


def extract_injury_cascade_features(
    gdb: "GraphDB",
    season: int,
    week: int,
    team: str,
) -> pd.DataFrame:
    """Extract injury cascade features for all players on a team in a week.

    Uses Cypher queries with temporal lag (only prior weeks).

    Args:
        gdb: Connected GraphDB instance.
        season: NFL season year.
        week: NFL week number.
        team: Team abbreviation.

    Returns:
        DataFrame with columns: player_id, season, week, and GRAPH_FEATURE_COLUMNS.
        Empty DataFrame if Neo4j unavailable.
    """
    if not gdb.is_connected:
        return pd.DataFrame()

    # Get teammates on this team for this season
    players = gdb.run(
        "MATCH (p:Player)-[r:PLAYS_FOR]->(t:Team {abbr: $team}) "
        "WHERE r.season = $season "
        "RETURN p.gsis_id AS player_id, p.name AS player_name",
        {"team": team, "season": season},
    )

    if not players:
        return pd.DataFrame()

    # Find currently injured starters (status Out/IR in prior weeks this season)
    injured_starters = gdb.run(
        "MATCH (p:Player)-[r:INJURED]->(g:Game) "
        "WHERE g.season = $season AND g.week < $week AND g.week >= $week - 3 "
        "  AND (g.home_team = $team OR g.away_team = $team) "
        "RETURN DISTINCT p.gsis_id AS injured_id",
        {"season": season, "week": week, "team": team},
    )
    injured_ids = {r["injured_id"] for r in injured_starters}

    # Find historical absorption patterns for each player
    rows = []
    for player in players:
        pid = player["player_id"]

        # Historical absorption rate: average target_share_delta
        # from all past ABSORBS_ROLE edges for this player
        absorptions = gdb.run(
            "MATCH (p:Player {gsis_id: $pid})-[r:ABSORBS_ROLE]->() "
            "WHERE r.season < $season OR (r.season = $season AND r.week_injured < $week) "
            "RETURN avg(r.target_share_delta) AS avg_target_delta, "
            "       avg(r.carry_share_delta) AS avg_carry_delta, "
            "       count(r) AS n_absorptions",
            {"pid": pid, "season": season, "week": week},
        )

        hist_rate = 0.0
        target_boost = 0.0
        carry_boost = 0.0

        if absorptions and absorptions[0].get("n_absorptions", 0) > 0:
            avg_td = absorptions[0].get("avg_target_delta") or 0.0
            avg_cd = absorptions[0].get("avg_carry_delta") or 0.0
            hist_rate = float(avg_td) + float(avg_cd)

            # If teammates are currently injured, project boost
            if injured_ids:
                target_boost = float(avg_td) * len(injured_ids)
                carry_boost = float(avg_cd) * len(injured_ids)

        rows.append(
            {
                "player_id": pid,
                "season": season,
                "week": week,
                "injury_cascade_target_boost": target_boost,
                "injury_cascade_carry_boost": carry_boost,
                "teammate_injured_starter": 1 if injured_ids else 0,
                "historical_absorption_rate": hist_rate,
            }
        )

    return pd.DataFrame(rows)


def extract_all_graph_features(
    gdb: "GraphDB",
    seasons: List[int],
) -> pd.DataFrame:
    """Batch-extract graph features across multiple seasons.

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of season years.

    Returns:
        Concatenated DataFrame of player-week graph features.
    """
    if not gdb.is_connected:
        logger.warning("Neo4j not connected — returning empty graph features")
        return pd.DataFrame()

    dfs = []
    for season in seasons:
        # Get all teams active this season
        teams = gdb.run(
            "MATCH (t:Team)<-[:PLAYS_FOR {season: $season}]-() "
            "RETURN DISTINCT t.abbr AS team",
            {"season": season},
        )
        team_list = [r["team"] for r in teams]

        for week in range(1, 19):
            for team in team_list:
                df = extract_injury_cascade_features(gdb, season, week, team)
                if not df.empty:
                    dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    logger.info(
        "Extracted %d graph feature rows across %d seasons", len(result), len(seasons)
    )
    return result


# ---------------------------------------------------------------------------
# Pure-pandas fallback (no Neo4j required)
# ---------------------------------------------------------------------------


def compute_graph_features_from_data(
    injuries_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    target_season: int,
    target_week: int,
) -> pd.DataFrame:
    """Compute graph-equivalent features using pure pandas (no Neo4j).

    This is the offline/fallback path used when Neo4j is not available.
    Computes the same features as extract_injury_cascade_features but
    directly from DataFrames.

    IMPORTANT: Only uses data from weeks strictly before target_week
    to prevent temporal leakage.

    Args:
        injuries_df: Bronze injuries with gsis_id, team, season, week,
            report_status.
        player_weekly_df: Bronze player_weekly with player_id, recent_team,
            season, week, target_share, carries.
        target_season: Season to compute features for.
        target_week: Week to compute features for (features use prior data only).

    Returns:
        DataFrame with columns: player_id, season, week, and GRAPH_FEATURE_COLUMNS.
    """
    if injuries_df.empty or player_weekly_df.empty:
        return pd.DataFrame()

    pw = player_weekly_df.copy()

    # Ensure carry_share exists
    if "carry_share" not in pw.columns:
        if "carries" in pw.columns:
            team_carries = pw.groupby(["recent_team", "season", "week"])[
                "carries"
            ].transform("sum")
            pw["carry_share"] = np.where(
                team_carries > 0, pw["carries"] / team_carries, 0.0
            )
        else:
            pw["carry_share"] = 0.0

    # --- Step 1: Identify currently injured starters ---
    # "Current" = Out/IR in the 3 weeks leading up to target_week
    id_col = "gsis_id" if "gsis_id" in injuries_df.columns else "player_id"
    recent_injuries = injuries_df[
        (injuries_df["season"] == target_season)
        & (injuries_df["week"] < target_week)
        & (injuries_df["week"] >= target_week - 3)
        & (injuries_df["report_status"].isin({"Out", "IR", "Injured Reserve"}))
    ]

    # Check prior usage of injured players to filter "starters"
    injured_starters = {}  # team -> set of injured player_ids
    for _, row in recent_injuries.iterrows():
        pid = str(row[id_col])
        team = str(row["team"])

        # Check if player had meaningful usage before injury
        prior = pw[
            (pw["player_id"] == pid)
            & (pw["season"] == target_season)
            & (pw["week"] < int(row["week"]))
            & (pw["week"] >= int(row["week"]) - 3)
        ]
        if prior.empty:
            continue

        ts = prior["target_share"].mean() if "target_share" in prior.columns else 0.0
        cs = prior["carry_share"].mean() if "carry_share" in prior.columns else 0.0

        if ts > 0.15 or cs > 0.20:
            if team not in injured_starters:
                injured_starters[team] = set()
            injured_starters[team].add(pid)

    # --- Step 2: Compute historical absorption rates ---
    # For each player, compute how much they historically absorbed when
    # teammates got injured (before target_week).
    # Use all prior seasons + prior weeks in current season.
    prior_pw = pw[
        (pw["season"] < target_season)
        | ((pw["season"] == target_season) & (pw["week"] < target_week))
    ]

    prior_injuries = injuries_df[
        (injuries_df["season"] < target_season)
        | (
            (injuries_df["season"] == target_season)
            & (injuries_df["week"] < target_week)
        )
    ]
    prior_injuries = prior_injuries[
        prior_injuries["report_status"].isin({"Out", "IR", "Injured Reserve"})
    ]

    # Build absorption history per player
    absorption_history = {}  # player_id -> list of (ts_delta, cs_delta)

    if not prior_injuries.empty and not prior_pw.empty:
        # Group injury events
        inj_events = prior_injuries.drop_duplicates(
            subset=[id_col, "team", "season", "week"]
        )

        for _, inj_row in inj_events.iterrows():
            inj_pid = str(inj_row[id_col])
            inj_team = str(inj_row["team"])
            inj_season = int(inj_row["season"])
            inj_week = int(inj_row["week"])

            # Only process if injured player was a significant contributor
            inj_prior = prior_pw[
                (prior_pw["player_id"] == inj_pid)
                & (prior_pw["season"] == inj_season)
                & (prior_pw["week"] >= inj_week - 3)
                & (prior_pw["week"] < inj_week)
            ]
            if inj_prior.empty:
                continue

            ts_mean = (
                inj_prior["target_share"].mean()
                if "target_share" in inj_prior.columns
                else 0.0
            )
            cs_mean = (
                inj_prior["carry_share"].mean()
                if "carry_share" in inj_prior.columns
                else 0.0
            )

            if ts_mean <= 0.15 and cs_mean <= 0.20:
                continue

            # Get teammates before/after
            teammates_before = prior_pw[
                (prior_pw["recent_team"] == inj_team)
                & (prior_pw["season"] == inj_season)
                & (prior_pw["week"] >= inj_week - 3)
                & (prior_pw["week"] < inj_week)
                & (prior_pw["player_id"] != inj_pid)
            ]
            teammates_after = prior_pw[
                (prior_pw["recent_team"] == inj_team)
                & (prior_pw["season"] == inj_season)
                & (prior_pw["week"] > inj_week)
                & (prior_pw["week"] <= inj_week + 3)
                & (prior_pw["player_id"] != inj_pid)
            ]

            if teammates_before.empty or teammates_after.empty:
                continue

            share_cols = [
                c for c in ["target_share", "carry_share"] if c in prior_pw.columns
            ]
            before_avg = teammates_before.groupby("player_id")[share_cols].mean()
            after_avg = teammates_after.groupby("player_id")[share_cols].mean()
            common = before_avg.index.intersection(after_avg.index)

            for pid in common:
                ts_d = (
                    float(
                        after_avg.loc[pid, "target_share"]
                        - before_avg.loc[pid, "target_share"]
                    )
                    if "target_share" in share_cols
                    else 0.0
                )
                cs_d = (
                    float(
                        after_avg.loc[pid, "carry_share"]
                        - before_avg.loc[pid, "carry_share"]
                    )
                    if "carry_share" in share_cols
                    else 0.0
                )

                if ts_d > 0.03 or cs_d > 0.03:
                    if pid not in absorption_history:
                        absorption_history[pid] = []
                    absorption_history[pid].append((ts_d, cs_d))

    # --- Step 3: Build output features ---
    # Get all players on all teams for this week
    current_players = pw[
        (pw["season"] == target_season)
        & (pw["week"] == target_week - 1)  # use most recent prior week
    ][["player_id", "recent_team"]].drop_duplicates()

    if current_players.empty:
        # Fall back to any prior week data
        current_players = pw[
            (pw["season"] == target_season) & (pw["week"] < target_week)
        ][["player_id", "recent_team"]].drop_duplicates()

    rows = []
    for _, row in current_players.iterrows():
        pid = str(row["player_id"])
        team = str(row["recent_team"])

        # Historical absorption rate
        hist = absorption_history.get(pid, [])
        hist_target = np.mean([h[0] for h in hist]) if hist else 0.0
        hist_carry = np.mean([h[1] for h in hist]) if hist else 0.0
        hist_rate = hist_target + hist_carry

        # Current injury cascade boost
        team_injured = injured_starters.get(team, set())
        n_injured = len(team_injured)
        target_boost = hist_target * n_injured if hist else 0.0
        carry_boost = hist_carry * n_injured if hist else 0.0

        rows.append(
            {
                "player_id": pid,
                "season": target_season,
                "week": target_week,
                "injury_cascade_target_boost": float(target_boost),
                "injury_cascade_carry_boost": float(carry_boost),
                "teammate_injured_starter": 1 if n_injured > 0 else 0,
                "historical_absorption_rate": float(hist_rate),
            }
        )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(
        "Computed %d graph feature rows for season %d week %d",
        len(result),
        target_season,
        target_week,
    )
    return result


def compute_all_graph_features_from_data(
    seasons: List[int],
) -> pd.DataFrame:
    """Compute graph features for all player-weeks across seasons (no Neo4j).

    Args:
        seasons: List of season years.

    Returns:
        Concatenated DataFrame of graph features.
    """
    dfs = []

    for season in seasons:
        injuries_df = _read_bronze_parquet("players/injuries", season)
        player_weekly_df = _read_bronze_parquet("players/weekly", season)

        if injuries_df.empty or player_weekly_df.empty:
            logger.warning("Missing data for season %d, skipping", season)
            continue

        # Also load prior seasons for historical absorption rates
        all_injuries = [injuries_df]
        all_pw = [player_weekly_df]
        for prior_season in range(
            max(season - 3, seasons[0] if seasons else 2020), season
        ):
            pi = _read_bronze_parquet("players/injuries", prior_season)
            pp = _read_bronze_parquet("players/weekly", prior_season)
            if not pi.empty:
                all_injuries.append(pi)
            if not pp.empty:
                all_pw.append(pp)

        combined_injuries = pd.concat(all_injuries, ignore_index=True)
        combined_pw = pd.concat(all_pw, ignore_index=True)

        # Compute features for each week in the season
        weeks = sorted(player_weekly_df["week"].dropna().unique())
        for week in weeks:
            if week < 2:
                continue  # Need at least 1 prior week

            df = compute_graph_features_from_data(
                combined_injuries, combined_pw, season, int(week)
            )
            if not df.empty:
                dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    logger.info(
        "Computed %d total graph feature rows across %d seasons",
        len(result),
        len(seasons),
    )
    return result


def save_graph_features(df: pd.DataFrame, season: int) -> Optional[str]:
    """Save graph features as Silver-layer parquet.

    Args:
        df: DataFrame with graph features.
        season: Season year for partitioning.

    Returns:
        Path to saved file, or None if empty.
    """
    if df.empty:
        return None

    season_df = df[df["season"] == season] if "season" in df.columns else df
    if season_df.empty:
        return None

    out_dir = os.path.join(GRAPH_FEATURES_DIR, f"season={season}")
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"graph_injury_cascade_{ts}.parquet")
    season_df.to_parquet(path, index=False)
    logger.info("Saved %d graph feature rows to %s", len(season_df), path)
    return path


# ---------------------------------------------------------------------------
# Phase 2: WR matchup features (pure-pandas fallback)
# ---------------------------------------------------------------------------

# Output columns from WR/OL graph feature extraction
WR_MATCHUP_FEATURE_COLUMNS = [
    "def_pass_epa_allowed",
    "wr_epa_vs_defense_history",
    "cb_cooccurrence_quality",
    "similar_wr_vs_defense",
]

OL_RB_FEATURE_COLUMNS = [
    "ol_starters_active",
    "ol_backup_insertions",
    "rb_ypc_with_full_ol",
    "rb_ypc_delta_backup_ol",
    "ol_continuity_score",
]


def compute_wr_matchup_features(
    pbp_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    target_season: int,
    target_week: int,
) -> pd.DataFrame:
    """Compute WR matchup features using pure pandas (no Neo4j).

    All features use data from weeks strictly before target_week to
    prevent temporal leakage.

    Args:
        pbp_df: Bronze PBP data with pass play columns.
        player_weekly_df: Bronze player_weekly with receiver stats.
        target_season: Season year.
        target_week: Week number (features use prior weeks only).

    Returns:
        DataFrame with player_id, season, week, and WR_MATCHUP_FEATURE_COLUMNS.
    """
    if pbp_df.empty or player_weekly_df.empty:
        return pd.DataFrame()

    # Temporal lag: only use data before target_week
    prior_pbp = pbp_df[
        (pbp_df["season"] < target_season)
        | ((pbp_df["season"] == target_season) & (pbp_df["week"] < target_week))
    ]

    # Pass plays with receiver
    pass_mask = (prior_pbp["play_type"] == "pass") & prior_pbp[
        "receiver_player_id"
    ].notna()
    passes = prior_pbp[pass_mask].copy() if pass_mask.any() else pd.DataFrame()

    # 1. def_pass_epa_allowed: average EPA allowed by defense on pass plays
    # over the prior 3 weeks (same season only)
    def_epa = pd.DataFrame()
    if not passes.empty and "epa" in passes.columns:
        recent_passes = passes[
            (passes["season"] == target_season)
            & (passes["week"] >= target_week - 3)
            & (passes["week"] < target_week)
        ]
        if not recent_passes.empty:
            def_epa = (
                recent_passes.groupby("defteam", as_index=False)
                .agg(def_pass_epa_allowed=("epa", "mean"))
                .rename(columns={"defteam": "opponent_team"})
            )

    # 2. wr_epa_vs_defense_history: WR's EPA against specific defense (all prior)
    wr_vs_def = pd.DataFrame()
    if not passes.empty and "epa" in passes.columns:
        wr_vs_def = (
            passes.groupby(["receiver_player_id", "defteam"], as_index=False)
            .agg(wr_epa_vs_defense_history=("epa", "mean"))
            .rename(
                columns={
                    "receiver_player_id": "player_id",
                    "defteam": "opponent_team",
                }
            )
        )

    # 3. similar_wr_vs_defense: average EPA of WRs with similar target share
    # against the same defense. Use player_weekly for target_share.
    similar_wr = pd.DataFrame()
    if not passes.empty and not player_weekly_df.empty:
        pw = player_weekly_df[
            (player_weekly_df["season"] == target_season)
            & (player_weekly_df["week"] < target_week)
            & (player_weekly_df["week"] >= target_week - 3)
        ]
        if "target_share" in pw.columns:
            avg_ts = pw.groupby("player_id")["target_share"].mean().to_dict()

            if avg_ts and not passes.empty:
                # For each defense, compute average EPA from WRs with ts > 0.15
                recent_passes = passes[
                    (passes["season"] == target_season) & (passes["week"] < target_week)
                ]
                if not recent_passes.empty:
                    similar_wr = (
                        recent_passes.groupby("defteam", as_index=False)
                        .agg(similar_wr_vs_defense=("epa", "mean"))
                        .rename(columns={"defteam": "opponent_team"})
                    )

    # Build output: one row per active WR for target_week
    pw_current = player_weekly_df[
        (player_weekly_df["season"] == target_season)
        & (player_weekly_df["week"] == target_week - 1)
        & (player_weekly_df["position"] == "WR")
    ]
    if pw_current.empty:
        pw_current = player_weekly_df[
            (player_weekly_df["season"] == target_season)
            & (player_weekly_df["week"] < target_week)
            & (player_weekly_df["position"] == "WR")
        ]

    if pw_current.empty:
        return pd.DataFrame()

    # Get opponent for each player
    result = pw_current[["player_id"]].drop_duplicates().copy()
    result["season"] = target_season
    result["week"] = target_week

    # Get opponent team + recent_team from most recent game
    keep_cols = ["player_id", "recent_team"]
    if "opponent_team" in pw_current.columns:
        keep_cols.append("opponent_team")
    team_opp = pw_current[keep_cols].drop_duplicates(subset=["player_id"], keep="last")
    result = result.merge(team_opp, on="player_id", how="left")

    # Ensure opponent_team is string type (not float NaN)
    if "opponent_team" not in result.columns:
        result["opponent_team"] = ""
    result["opponent_team"] = result["opponent_team"].fillna("").astype(str)

    # Join features
    for col in WR_MATCHUP_FEATURE_COLUMNS:
        result[col] = np.nan

    has_opp = result["opponent_team"].str.len().gt(0).any()

    if not def_epa.empty and has_opp:
        def_epa["opponent_team"] = def_epa["opponent_team"].astype(str)
        result = result.merge(
            def_epa, on="opponent_team", how="left", suffixes=("", "_new")
        )
        if "def_pass_epa_allowed_new" in result.columns:
            result["def_pass_epa_allowed"] = result["def_pass_epa_allowed_new"]
            result = result.drop(columns=["def_pass_epa_allowed_new"])

    if not wr_vs_def.empty and has_opp:
        wr_vs_def["opponent_team"] = wr_vs_def["opponent_team"].astype(str)
        result = result.merge(
            wr_vs_def,
            on=["player_id", "opponent_team"],
            how="left",
            suffixes=("", "_new"),
        )
        if "wr_epa_vs_defense_history_new" in result.columns:
            result["wr_epa_vs_defense_history"] = result[
                "wr_epa_vs_defense_history_new"
            ]
            result = result.drop(columns=["wr_epa_vs_defense_history_new"])

    if not similar_wr.empty and has_opp:
        similar_wr["opponent_team"] = similar_wr["opponent_team"].astype(str)
        result = result.merge(
            similar_wr, on="opponent_team", how="left", suffixes=("", "_new")
        )
        if "similar_wr_vs_defense_new" in result.columns:
            result["similar_wr_vs_defense"] = result["similar_wr_vs_defense_new"]
            result = result.drop(columns=["similar_wr_vs_defense_new"])

    # cb_cooccurrence_quality: requires participation data; NaN in fallback
    # (graph or participation-enhanced path fills this)

    out_cols = ["player_id", "season", "week"] + WR_MATCHUP_FEATURE_COLUMNS
    result = result.drop(columns=["recent_team", "opponent_team"], errors="ignore")
    for c in out_cols:
        if c not in result.columns:
            result[c] = np.nan

    return result[out_cols].drop_duplicates(subset=["player_id", "season", "week"])


# ---------------------------------------------------------------------------
# Phase 2: TE matchup features (pure-pandas fallback)
# ---------------------------------------------------------------------------

# Output columns from TE graph feature extraction
TE_FEATURE_COLUMNS = [
    "te_lb_coverage_rate",
    "te_vs_defense_epa_history",
    "te_red_zone_target_share",
    "def_te_fantasy_pts_allowed",
]


def compute_te_features(
    player_weekly_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
    participation_df: Optional[pd.DataFrame] = None,
    season: Optional[int] = None,
) -> pd.DataFrame:
    """Compute TE matchup features using pure pandas (no Neo4j).

    All features use data from weeks strictly before the target week to
    prevent temporal leakage.

    Features:
        te_lb_coverage_rate: LB coverage rate against TEs for the opposing
            defense (from participation data; NaN if unavailable).
        te_vs_defense_epa_history: Rolling EPA of this TE against the
            specific opposing defense from prior matchups only.
        te_red_zone_target_share: TE's share of their team's red zone
            targets (rolling 3 games, shift(1)).
        def_te_fantasy_pts_allowed: Opposing defense's average fantasy
            points allowed to TEs (rolling 3 games, shift(1)).

    Args:
        player_weekly_df: Bronze player_weekly with player_id, recent_team,
            season, week, position, targets, receptions, receiving_yards,
            receiving_tds, opponent_team.
        rosters_df: Roster DataFrame with player_id and position columns.
        participation_df: Parsed participation DataFrame. Optional.
        season: If provided, restrict output to this season only.

    Returns:
        DataFrame with player_id, season, week, and TE_FEATURE_COLUMNS.
    """
    if player_weekly_df.empty:
        return pd.DataFrame()

    pw = player_weekly_df.copy()

    # Identify TE players
    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set()
    if not rosters_df.empty:
        te_ids = set(
            rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
        )

    # Also include TEs identified from player_weekly position column
    if "position" in pw.columns:
        pw_te_ids = set(
            pw.loc[pw["position"] == "TE", "player_id"].astype(str).unique()
        )
        te_ids = te_ids | pw_te_ids

    if not te_ids:
        return pd.DataFrame()

    # Filter to TE rows only
    te_pw = pw[pw["player_id"].astype(str).isin(te_ids)].copy()
    if te_pw.empty:
        return pd.DataFrame()

    # Sort for rolling computations
    te_pw = te_pw.sort_values(["player_id", "season", "week"])

    # Optionally filter to target season
    seasons_in_data = te_pw["season"].unique() if season is None else [season]

    results = []
    for target_season in seasons_in_data:
        season_te = te_pw[te_pw["season"] == target_season]
        weeks = sorted(season_te["week"].dropna().unique())

        for target_week in weeks:
            if target_week < 2:
                continue  # Need at least 1 prior week

            # --- te_vs_defense_epa_history ---
            # Prior data only (all seasons up to but not including target_week)
            prior_te = te_pw[
                (te_pw["season"] < target_season)
                | ((te_pw["season"] == target_season) & (te_pw["week"] < target_week))
            ]

            # Get opponent for each TE in target_week
            week_rows = season_te[season_te["week"] == target_week]
            if week_rows.empty:
                continue

            for _, row in week_rows.iterrows():
                pid = str(row["player_id"])
                opp = str(row.get("opponent_team", ""))

                feat = {
                    "player_id": pid,
                    "season": int(target_season),
                    "week": int(target_week),
                    "te_lb_coverage_rate": np.nan,
                    "te_vs_defense_epa_history": np.nan,
                    "te_red_zone_target_share": np.nan,
                    "def_te_fantasy_pts_allowed": np.nan,
                }

                # te_vs_defense_epa_history: EPA of this TE vs this opponent
                if opp and "receiving_epa" in prior_te.columns:
                    hist = prior_te[
                        (prior_te["player_id"] == pid)
                        & (prior_te["opponent_team"] == opp)
                    ]
                    if not hist.empty:
                        feat["te_vs_defense_epa_history"] = float(
                            hist["receiving_epa"].mean()
                        )

                # te_red_zone_target_share: rolling 3 games, shift(1)
                # Compute from prior weeks this season
                prior_season = prior_te[
                    (prior_te["season"] == target_season)
                    & (prior_te["week"] >= max(1, target_week - 3))
                    & (prior_te["week"] < target_week)
                ]
                if "rz_target_share" in prior_season.columns:
                    player_prior = prior_season[prior_season["player_id"] == pid]
                    if not player_prior.empty:
                        feat["te_red_zone_target_share"] = float(
                            player_prior["rz_target_share"].mean()
                        )

                # def_te_fantasy_pts_allowed: avg fantasy points allowed to TEs
                # by opponent defense (rolling 3 games, shift(1))
                if opp and "fantasy_points" in prior_te.columns:
                    opp_allowed = prior_te[
                        (prior_te["opponent_team"].astype(str) == opp)
                        & (prior_te["season"] == target_season)
                        & (prior_te["week"] >= max(1, target_week - 3))
                        & (prior_te["week"] < target_week)
                    ]
                    # Filter to opponent's TE opponents (TEs that played against opp)
                    # We actually want TEs that had opponent_team == opp, meaning they
                    # played against this defense
                    if not opp_allowed.empty:
                        feat["def_te_fantasy_pts_allowed"] = float(
                            opp_allowed["fantasy_points"].mean()
                        )

                # te_lb_coverage_rate: from participation data if available
                if participation_df is not None and not participation_df.empty and opp:
                    from graph_te_matchup import LB_POSITIONS, SAFETY_POSITIONS

                    # Get defense players from opponent in prior weeks
                    def_mask = participation_df["side"] == "defense"
                    lb_mask = def_mask & participation_df["position"].isin(LB_POSITIONS)
                    safety_mask = def_mask & participation_df["position"].isin(
                        SAFETY_POSITIONS
                    )

                    # We need game_ids where opponent was on defense
                    # This requires joining with PBP to find which games had
                    # this opponent as defteam — simplified: count overall
                    # LB vs safety ratio from participation in prior weeks
                    lb_total = lb_mask.sum()
                    safety_total = safety_mask.sum()
                    total = lb_total + safety_total
                    if total > 0:
                        feat["te_lb_coverage_rate"] = float(lb_total / total)

                results.append(feat)

    if not results:
        return pd.DataFrame()

    result = pd.DataFrame(results)
    logger.info(
        "Computed %d TE feature rows",
        len(result),
    )
    return result


def compute_ol_rb_features(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    target_season: int,
    target_week: int,
) -> pd.DataFrame:
    """Compute OL/RB features using pure pandas (no Neo4j).

    Features:
        ol_starters_active: Count of starting OL (0-5) on field.
        ol_backup_insertions: Number of non-starter OL.
        rb_ypc_with_full_ol: RB YPC when all 5 starters in (rolling 3 games).
        rb_ypc_delta_backup_ol: YPC change when backup OL is in.
        ol_continuity_score: Rolling % of snaps with same 5 starters.

    Uses only data from weeks before target_week.

    Args:
        pbp_df: PBP data.
        participation_parsed_df: Parsed participation data.
        player_weekly_df: Player weekly stats.
        target_season: Season year.
        target_week: Week (prior data only).

    Returns:
        DataFrame with player_id, season, week, and OL_RB_FEATURE_COLUMNS.
    """
    if player_weekly_df.empty:
        return pd.DataFrame()

    # Get active RBs for target_week
    pw_current = player_weekly_df[
        (player_weekly_df["season"] == target_season)
        & (player_weekly_df["week"] < target_week)
        & (player_weekly_df["position"] == "RB")
    ]
    if pw_current.empty:
        return pd.DataFrame()

    result = pw_current[["player_id"]].drop_duplicates().copy()
    result["season"] = target_season
    result["week"] = target_week

    # Default: all NaN (graceful degradation if participation data unavailable)
    for col in OL_RB_FEATURE_COLUMNS:
        result[col] = np.nan

    if participation_parsed_df.empty or pbp_df.empty:
        return result

    # Temporal lag: only use prior data
    prior_pbp = pbp_df[
        (pbp_df["season"] == target_season)
        & (pbp_df["week"] < target_week)
        & (pbp_df["week"] >= max(1, target_week - 3))
    ]
    if prior_pbp.empty:
        return result

    # Count OL per play from participation data
    from graph_participation import OL_POSITIONS

    ol_mask = (participation_parsed_df["side"] == "offense") & (
        participation_parsed_df["position"].isin(OL_POSITIONS)
    )
    if not ol_mask.any():
        return result

    ol_per_play = (
        participation_parsed_df[ol_mask]
        .groupby(["game_id", "play_id"], as_index=False)
        .agg(ol_count=("player_gsis_id", "count"))
    )

    # Merge OL count with rush plays
    rush_mask = (prior_pbp["play_type"] == "run") & prior_pbp[
        "rusher_player_id"
    ].notna()
    rushes = prior_pbp[rush_mask].copy() if rush_mask.any() else pd.DataFrame()

    if rushes.empty:
        return result

    rushes = rushes.merge(ol_per_play, on=["game_id", "play_id"], how="left")
    rushes["ol_count"] = rushes["ol_count"].fillna(5)
    rushes["yards_gained"] = rushes["yards_gained"].fillna(0)

    # Full OL = 5 starters on field
    rushes["full_ol"] = rushes["ol_count"] >= 5

    # Per-RB aggregation
    group = rushes.groupby("rusher_player_id", as_index=False)
    rb_stats = group.agg(
        avg_ol_count=("ol_count", "mean"),
        total_carries=("play_id", "count"),
    )
    rb_stats = rb_stats.rename(columns={"rusher_player_id": "player_id"})

    # YPC with full OL
    full_ol_plays = rushes[rushes["full_ol"]]
    if not full_ol_plays.empty:
        ypc_full = full_ol_plays.groupby("rusher_player_id", as_index=False).agg(
            rb_ypc_with_full_ol_val=("yards_gained", "mean")
        )
        ypc_full = ypc_full.rename(columns={"rusher_player_id": "player_id"})
        rb_stats = rb_stats.merge(ypc_full, on="player_id", how="left")
    else:
        rb_stats["rb_ypc_with_full_ol_val"] = np.nan

    # YPC without full OL (backup)
    partial_ol = rushes[~rushes["full_ol"]]
    if not partial_ol.empty:
        ypc_partial = partial_ol.groupby("rusher_player_id", as_index=False).agg(
            ypc_backup=("yards_gained", "mean")
        )
        ypc_partial = ypc_partial.rename(columns={"rusher_player_id": "player_id"})
        rb_stats = rb_stats.merge(ypc_partial, on="player_id", how="left")
    else:
        rb_stats["ypc_backup"] = np.nan

    rb_stats["rb_ypc_delta_backup_ol"] = rb_stats["rb_ypc_with_full_ol_val"].fillna(
        0
    ) - rb_stats["ypc_backup"].fillna(0)

    # Map features to result
    result = result.merge(rb_stats, on="player_id", how="left")

    result["ol_starters_active"] = result["avg_ol_count"].clip(0, 5)
    result["ol_backup_insertions"] = (5 - result["avg_ol_count"].fillna(5)).clip(0, 5)
    result["rb_ypc_with_full_ol"] = result.get("rb_ypc_with_full_ol_val", np.nan)
    # ol_continuity_score: fraction of plays with full 5 OL
    if not rushes.empty:
        team_continuity = rushes.groupby(
            ["posteam"] if "posteam" in rushes.columns else ["home_team"],
            as_index=False,
        ).agg(continuity=("full_ol", "mean"))
        team_col_name = "posteam" if "posteam" in rushes.columns else "home_team"
        team_continuity = team_continuity.rename(columns={team_col_name: "recent_team"})

        # Map team continuity to RBs via player_weekly
        rb_teams = pw_current[["player_id", "recent_team"]].drop_duplicates(
            subset=["player_id"], keep="last"
        )
        result = result.merge(rb_teams, on="player_id", how="left")
        result = result.merge(team_continuity, on="recent_team", how="left")
        result["ol_continuity_score"] = result.get("continuity", np.nan)
        result = result.drop(columns=["recent_team", "continuity"], errors="ignore")

    # Clean up intermediate columns
    drop_cols = [
        "avg_ol_count",
        "total_carries",
        "rb_ypc_with_full_ol_val",
        "ypc_backup",
    ]
    result = result.drop(columns=[c for c in drop_cols if c in result.columns])

    out_cols = ["player_id", "season", "week"] + OL_RB_FEATURE_COLUMNS
    for c in out_cols:
        if c not in result.columns:
            result[c] = np.nan

    return result[out_cols].drop_duplicates(subset=["player_id", "season", "week"])


# ---------------------------------------------------------------------------
# Phase 3: Scheme matchup features (pure-pandas)
# ---------------------------------------------------------------------------

# Output columns from scheme/defensive front feature extraction
SCHEME_FEATURE_COLUMNS = [
    "def_front_quality_vs_run",
    "scheme_matchup_score",
    "rb_ypc_by_gap_vs_defense",
    "def_run_epa_allowed",
]


def compute_scheme_features(
    pbp_df: pd.DataFrame,
    pfr_def_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute scheme matchup features per team per week (RB-relevant).

    Pure-pandas computation -- no Neo4j required. All features use strict
    temporal lag (shift(1) or prior-week-only data).

    Features:
    - def_front_quality_vs_run: opposing team's front7_quality (rolling 3, shift(1))
    - scheme_matchup_score: historical YPC of this team's scheme type vs
      opposing defense's front7 tier (top/mid/bottom third)
    - rb_ypc_by_gap_vs_defense: team's YPC by gap type vs this opponent
      (if repeat matchup, else NaN)
    - def_run_epa_allowed: opposing defense EPA allowed on run plays
      (rolling 3 games, shift(1))

    Args:
        pbp_df: Bronze PBP data with run plays.
        pfr_def_df: Bronze PFR defensive weekly data.
        rosters_df: Roster data (may be empty).
        schedules_df: Bronze schedules with home_team, away_team.

    Returns:
        DataFrame with team, season, week, and SCHEME_FEATURE_COLUMNS.
        Empty DataFrame if inputs are insufficient.
    """
    from graph_scheme import classify_run_scheme, compute_defensive_front_quality

    if pbp_df.empty:
        return pd.DataFrame()

    # Get season from PBP data
    seasons = sorted(pbp_df["season"].dropna().unique())
    if not seasons:
        return pd.DataFrame()

    all_results = []

    for season in seasons:
        season_pbp = pbp_df[pbp_df["season"] == season].copy()
        season_pfr = (
            pfr_def_df[pfr_def_df["season"] == season].copy()
            if not pfr_def_df.empty and "season" in pfr_def_df.columns
            else pd.DataFrame()
        )
        season_sched = (
            schedules_df[schedules_df["season"] == season].copy()
            if not schedules_df.empty and "season" in schedules_df.columns
            else pd.DataFrame()
        )

        # 1. Classify run scheme for this season
        schemes = classify_run_scheme(season_pbp, season)

        # 2. Compute defensive front quality
        def_front = compute_defensive_front_quality(season_pfr, rosters_df)

        # 3. Compute def_run_epa_allowed from PBP run plays
        run_plays = season_pbp[season_pbp["play_type"] == "run"].copy()
        if not run_plays.empty and "epa" in run_plays.columns:
            def_run_epa = (
                run_plays.groupby(["defteam", "season", "week"])["epa"]
                .mean()
                .reset_index()
            )
            def_run_epa.columns = ["team", "season", "week", "def_run_epa_raw"]
            def_run_epa = def_run_epa.sort_values(["team", "season", "week"])
            def_run_epa["def_run_epa_allowed"] = def_run_epa.groupby(
                ["team", "season"]
            )["def_run_epa_raw"].transform(
                lambda s: s.shift(1).rolling(3, min_periods=1).mean()
            )
        else:
            def_run_epa = pd.DataFrame()

        # 4. Build matchup schedule: team -> opponent per week
        matchups = pd.DataFrame()
        if not season_sched.empty:
            home = season_sched[["season", "week", "home_team", "away_team"]].rename(
                columns={"home_team": "team", "away_team": "opponent"}
            )
            away = season_sched[["season", "week", "away_team", "home_team"]].rename(
                columns={"away_team": "team", "home_team": "opponent"}
            )
            matchups = pd.concat([home, away], ignore_index=True)

        if matchups.empty:
            # Build matchups from PBP
            if "posteam" in season_pbp.columns and "defteam" in season_pbp.columns:
                matchups = (
                    season_pbp[["season", "week", "posteam", "defteam"]]
                    .drop_duplicates()
                    .rename(columns={"posteam": "team", "defteam": "opponent"})
                )

        if matchups.empty:
            continue

        # 5. Compute team YPC per week (for scheme_matchup_score)
        if not run_plays.empty and "yards_gained" in run_plays.columns:
            team_ypc = (
                run_plays.groupby(["posteam", "season", "week"])["yards_gained"]
                .mean()
                .reset_index()
            )
            team_ypc.columns = ["team", "season", "week", "team_ypc"]
        else:
            team_ypc = pd.DataFrame()

        # Assign front7 tiers (top/mid/bottom third)
        if not def_front.empty and "front7_quality" in def_front.columns:
            season_front = def_front[def_front["season"] == season].copy()
            quality_vals = season_front["front7_quality"].dropna()
            if len(quality_vals) > 0:
                q33 = quality_vals.quantile(0.33)
                q66 = quality_vals.quantile(0.66)
                season_front["front7_tier"] = np.where(
                    season_front["front7_quality"] >= q66,
                    "top",
                    np.where(season_front["front7_quality"] >= q33, "mid", "bottom"),
                )
            else:
                season_front["front7_tier"] = "mid"
        else:
            season_front = pd.DataFrame()

        # 6. Compute gap YPC vs specific opponents
        gap_ypc = pd.DataFrame()
        if not run_plays.empty and "yards_gained" in run_plays.columns:
            gap_plays = run_plays.dropna(subset=["run_gap"])
            if not gap_plays.empty:
                gap_ypc = (
                    gap_plays.groupby(["posteam", "defteam", "season", "week"])[
                        "yards_gained"
                    ]
                    .mean()
                    .reset_index()
                )
                gap_ypc.columns = [
                    "team",
                    "opponent",
                    "season",
                    "week",
                    "gap_ypc_raw",
                ]

        # 7. Assemble per team-week rows
        for _, mrow in matchups.iterrows():
            team = mrow["team"]
            opp = mrow["opponent"]
            week = int(mrow["week"])

            row = {
                "team": team,
                "season": season,
                "week": week,
                "def_front_quality_vs_run": np.nan,
                "scheme_matchup_score": np.nan,
                "rb_ypc_by_gap_vs_defense": np.nan,
                "def_run_epa_allowed": np.nan,
            }

            # def_front_quality_vs_run: opponent's front7_quality
            if not season_front.empty:
                opp_front = season_front[
                    (season_front["team"] == opp)
                    & (season_front["season"] == season)
                    & (season_front["week"] == week)
                ]
                if not opp_front.empty:
                    row["def_front_quality_vs_run"] = float(
                        opp_front["front7_quality"].iloc[0]
                    )

            # def_run_epa_allowed: opponent's run EPA allowed
            if not def_run_epa.empty:
                opp_epa = def_run_epa[
                    (def_run_epa["team"] == opp)
                    & (def_run_epa["season"] == season)
                    & (def_run_epa["week"] == week)
                ]
                if not opp_epa.empty:
                    val = opp_epa["def_run_epa_allowed"].iloc[0]
                    if not pd.isna(val):
                        row["def_run_epa_allowed"] = float(val)

            # scheme_matchup_score: historical YPC of same scheme type vs
            # opponent's front7 tier (prior weeks only)
            if not schemes.empty and not season_front.empty and not team_ypc.empty:
                team_scheme = schemes[schemes["team"] == team]
                if not team_scheme.empty:
                    scheme_type = team_scheme["scheme_type"].iloc[0]

                    # Get opponent's tier for this week
                    opp_tier_row = season_front[
                        (season_front["team"] == opp) & (season_front["week"] == week)
                    ]
                    if not opp_tier_row.empty and "front7_tier" in opp_tier_row.columns:
                        opp_tier = opp_tier_row["front7_tier"].iloc[0]

                        # Find all prior games where teams with same scheme
                        # faced defenses in same tier
                        same_scheme_teams = set(
                            schemes[schemes["scheme_type"] == scheme_type]["team"]
                        )
                        same_tier_defs = set()
                        if not season_front.empty:
                            prior_front = season_front[season_front["week"] < week]
                            same_tier_defs = set(
                                prior_front[prior_front["front7_tier"] == opp_tier][
                                    "team"
                                ]
                            )

                        if same_scheme_teams and same_tier_defs:
                            prior_ypc = team_ypc[
                                (team_ypc["team"].isin(same_scheme_teams))
                                & (team_ypc["week"] < week)
                                & (team_ypc["season"] == season)
                            ]
                            if not prior_ypc.empty:
                                row["scheme_matchup_score"] = float(
                                    prior_ypc["team_ypc"].mean()
                                )

            # rb_ypc_by_gap_vs_defense: team's YPC vs this specific opponent
            # (prior meetings only)
            if not gap_ypc.empty:
                prior_gap = gap_ypc[
                    (gap_ypc["team"] == team)
                    & (gap_ypc["opponent"] == opp)
                    & (
                        (gap_ypc["season"] < season)
                        | ((gap_ypc["season"] == season) & (gap_ypc["week"] < week))
                    )
                ]
                if not prior_gap.empty:
                    row["rb_ypc_by_gap_vs_defense"] = float(
                        prior_gap["gap_ypc_raw"].mean()
                    )

            all_results.append(row)

    if not all_results:
        return pd.DataFrame()

    result = pd.DataFrame(all_results)
    out_cols = ["team", "season", "week"] + SCHEME_FEATURE_COLUMNS
    for c in out_cols:
        if c not in result.columns:
            result[c] = np.nan

    logger.info("Computed %d scheme feature rows", len(result))
    return result[out_cols]


# ---------------------------------------------------------------------------
# Phase 4: RB matchup features (pure-pandas, no Neo4j required)
# ---------------------------------------------------------------------------

# Re-export the column list for downstream callers
from graph_rb_matchup import (  # noqa: E402 — import after module-level constants
    RB_MATCHUP_FEATURE_COLUMNS,
    compute_rb_matchup_features as _compute_rb_matchup_features_impl,
)


def compute_rb_matchup_features_from_data(
    pbp_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
    season: Optional[int] = None,
    participation_parsed_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute RB vs defensive line/LB matchup features (pure-pandas).

    Wraps ``graph_rb_matchup.compute_rb_matchup_features`` so callers can
    import a single entry point from ``graph_feature_extraction``.

    All features use strictly lagged data (only weeks prior to target week).
    Gracefully returns an empty DataFrame when PBP is unavailable.

    Feature columns returned (prefixed ``rb_matchup_``):
        avg_dl_count         — Mean DL defenders faced per carry.
        run_gap_success_rate — Success rate (yards >= distance) by gap vs defense.
        stacked_box_rate     — % of carries against 8+ defenders in box.
        ybc_proxy            — Positive-EPA rush rate (yards-before-contact proxy).
        lb_tackle_rate       — LB presence rate on negative-EPA rushes.
        def_rush_epa_allowed — Rolling EPA allowed by opposing defense on run plays.
        goal_line_carry_rate — % of carries at yardline_100 <= 5.
        short_yardage_conv   — Conversion rate on 3rd/4th and <= 2 yards to go.

    Args:
        pbp_df: Bronze PBP data with run play columns.
        rosters_df: Roster DataFrame to identify RBs. Optional.
        season: If provided, restrict output to this season. Optional.
        participation_parsed_df: Output of parse_participation_players.
            Enables DL count and LB tackle-rate features. Optional.

    Returns:
        DataFrame with player_id, season, week, and RB_MATCHUP_FEATURE_COLUMNS.
        Empty DataFrame if inputs are insufficient.
    """
    if pbp_df is None or pbp_df.empty:
        return pd.DataFrame()

    result = _compute_rb_matchup_features_impl(
        pbp_df=pbp_df,
        rosters_df=rosters_df,
        season=season,
        participation_parsed_df=participation_parsed_df,
    )

    logger.info(
        "compute_rb_matchup_features_from_data: %d rows for season=%s",
        len(result),
        season,
    )
    return result
