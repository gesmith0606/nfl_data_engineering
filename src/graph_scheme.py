"""Scheme classification and defensive front profiling.

Classifies offensive run schemes (zone, gap_power, spread, balanced) from
PBP data, and profiles defensive front-7 quality from PFR defensive stats.

All rolling/aggregate features use strict temporal lag (shift(1)) to prevent
data leakage.

Exports:
    classify_run_scheme: Per-team-per-season run scheme classification.
    build_scheme_nodes: Create Neo4j (:Scheme) nodes and edges.
    compute_defensive_front_quality: Front-7 composite from PFR defensive data.
    build_defends_run_edges: Create Neo4j [:DEFENDS_RUN] edges.
"""

import glob
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")

# DL and LB position groups for front-7 filtering
_DL_POSITIONS = {"DE", "DT", "NT"}
_LB_POSITIONS = {"LB", "ILB", "OLB", "MLB", "EDGE"}
_FRONT7_POSITIONS = _DL_POSITIONS | _LB_POSITIONS

# Defensive front composite weights (normalized per game)
_SACK_WEIGHT = 0.3
_PRESSURE_WEIGHT = 0.3
_HURRY_WEIGHT = 0.2
_TACKLE_WEIGHT = 0.2

# Scheme classification thresholds
_ZONE_END_RATE_THRESHOLD = 0.35
_GAP_POWER_INNER_THRESHOLD = 0.50
_SPREAD_SHOTGUN_THRESHOLD = 0.60
_BALANCED_LOCATION_TOLERANCE = 0.15


# ---------------------------------------------------------------------------
# Bronze readers
# ---------------------------------------------------------------------------


def _read_bronze_pbp(season: int) -> pd.DataFrame:
    """Read latest Bronze PBP for a season.

    Args:
        season: NFL season year.

    Returns:
        DataFrame of PBP data, or empty DataFrame if not found.
    """
    pattern = os.path.join(BRONZE_DIR, "pbp", f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_bronze_pfr_def(season: int) -> pd.DataFrame:
    """Read latest Bronze PFR defensive weekly data for a season.

    Args:
        season: NFL season year.

    Returns:
        DataFrame of PFR defensive data, or empty DataFrame if not found.
    """
    pattern = os.path.join(
        BRONZE_DIR, "pfr", "weekly", "def", f"season={season}", "*.parquet"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


# ---------------------------------------------------------------------------
# Step 1: Scheme Classification
# ---------------------------------------------------------------------------


def classify_run_scheme(pbp_df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Classify each team's run scheme for a season from PBP run plays.

    Filters PBP to run plays (play_type='run') and computes per-team:
    - run_gap distribution (end/tackle/guard rates)
    - run_location distribution (left/middle/right rates)
    - shotgun_rate and no_huddle_rate on run plays

    Classification rules:
    - "zone": run_gap_end_rate > 0.35 OR balanced run_location
    - "gap_power": run_gap_guard_rate + run_gap_tackle_rate > 0.50
    - "spread": shotgun_rate > 0.60
    - "balanced": none of above

    Args:
        pbp_df: Bronze PBP DataFrame with play_type, run_gap, run_location,
            shotgun, no_huddle, posteam columns.
        season: NFL season year (added to output).

    Returns:
        DataFrame with columns: team, season, scheme_type,
        run_gap_end_rate, run_gap_tackle_rate, run_gap_guard_rate,
        run_loc_left_rate, run_loc_middle_rate, run_loc_right_rate,
        shotgun_rate, no_huddle_rate.
        Empty DataFrame if no run plays found.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    # Filter to run plays
    runs = pbp_df[pbp_df["play_type"] == "run"].copy()
    if runs.empty:
        return pd.DataFrame()

    # Ensure posteam exists
    if "posteam" not in runs.columns:
        logger.warning("posteam column missing from PBP data")
        return pd.DataFrame()

    teams = runs["posteam"].dropna().unique()
    rows = []

    for team in teams:
        team_runs = runs[runs["posteam"] == team]
        n_runs = len(team_runs)
        if n_runs == 0:
            continue

        # Run gap distribution
        gap_counts = team_runs["run_gap"].value_counts()
        end_rate = gap_counts.get("end", 0) / n_runs
        tackle_rate = gap_counts.get("tackle", 0) / n_runs
        guard_rate = gap_counts.get("guard", 0) / n_runs

        # Run location distribution
        loc_counts = team_runs["run_location"].value_counts()
        left_rate = loc_counts.get("left", 0) / n_runs
        middle_rate = loc_counts.get("middle", 0) / n_runs
        right_rate = loc_counts.get("right", 0) / n_runs

        # Shotgun rate on run plays
        shotgun_rate = 0.0
        if "shotgun" in team_runs.columns:
            shotgun_rate = float(team_runs["shotgun"].fillna(0).mean())

        # No-huddle rate on run plays
        no_huddle_rate = 0.0
        if "no_huddle" in team_runs.columns:
            no_huddle_rate = float(team_runs["no_huddle"].fillna(0).mean())

        # Classify scheme
        # Check balance: all location rates within tolerance of 1/3
        location_balanced = (
            abs(left_rate - 1 / 3) < _BALANCED_LOCATION_TOLERANCE
            and abs(middle_rate - 1 / 3) < _BALANCED_LOCATION_TOLERANCE
            and abs(right_rate - 1 / 3) < _BALANCED_LOCATION_TOLERANCE
        )

        if end_rate > _ZONE_END_RATE_THRESHOLD or location_balanced:
            scheme_type = "zone"
        elif (guard_rate + tackle_rate) > _GAP_POWER_INNER_THRESHOLD:
            scheme_type = "gap_power"
        elif shotgun_rate > _SPREAD_SHOTGUN_THRESHOLD:
            scheme_type = "spread"
        else:
            scheme_type = "balanced"

        rows.append(
            {
                "team": team,
                "season": season,
                "scheme_type": scheme_type,
                "run_gap_end_rate": round(end_rate, 4),
                "run_gap_tackle_rate": round(tackle_rate, 4),
                "run_gap_guard_rate": round(guard_rate, 4),
                "run_loc_left_rate": round(left_rate, 4),
                "run_loc_middle_rate": round(middle_rate, 4),
                "run_loc_right_rate": round(right_rate, 4),
                "shotgun_rate": round(shotgun_rate, 4),
                "no_huddle_rate": round(no_huddle_rate, 4),
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def build_scheme_nodes(
    graph_db: "GraphDB",  # noqa: F821
    schemes_df: pd.DataFrame,
) -> int:
    """Create (:Scheme) nodes and (:Team)-[:RUNS_SCHEME]->(:Scheme) edges.

    Args:
        graph_db: Connected GraphDB instance.
        schemes_df: Output of classify_run_scheme with team, season,
            scheme_type columns.

    Returns:
        Number of edges created. 0 if Neo4j unavailable.
    """
    if not graph_db.is_connected or schemes_df.empty:
        return 0

    count = 0
    for _, row in schemes_df.iterrows():
        graph_db.run_write(
            "MERGE (s:Scheme {name: $scheme_type}) " "SET s.description = $scheme_type",
            {"scheme_type": row["scheme_type"]},
        )
        graph_db.run_write(
            "MATCH (t:Team {abbr: $team}) "
            "MERGE (s:Scheme {name: $scheme_type}) "
            "MERGE (t)-[r:RUNS_SCHEME {season: $season}]->(s) "
            "SET r.shotgun_rate = $shotgun_rate, "
            "    r.no_huddle_rate = $no_huddle_rate, "
            "    r.run_gap_end_rate = $run_gap_end_rate",
            {
                "team": row["team"],
                "scheme_type": row["scheme_type"],
                "season": int(row["season"]),
                "shotgun_rate": float(row.get("shotgun_rate", 0)),
                "no_huddle_rate": float(row.get("no_huddle_rate", 0)),
                "run_gap_end_rate": float(row.get("run_gap_end_rate", 0)),
            },
        )
        count += 1

    logger.info("Created %d RUNS_SCHEME edges", count)
    return count


# ---------------------------------------------------------------------------
# Step 2: Defensive Front Profiling
# ---------------------------------------------------------------------------


def compute_defensive_front_quality(
    pfr_def_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute front-7 defensive quality per team per week.

    Filters to DL/LB positions (via roster join if available, otherwise
    uses heuristics on PFR stats), sums sacks/pressures/hurries/tackles
    per team-week, and computes a composite score:

        front7_quality = 0.3*sacks + 0.3*pressures + 0.2*hurries + 0.2*tackles

    Values are normalized per game (already per-game in PFR data).
    Rolling 3-game average with shift(1) is applied for temporal safety.

    Args:
        pfr_def_df: Bronze PFR defensive weekly data with def_sacks,
            def_pressures, def_times_hurried, def_tackles_combined,
            pfr_player_name, team, season, week columns.
        rosters_df: Optional roster DataFrame with position, player name,
            and team for filtering to front-7 positions. If None, uses
            pressure/sack heuristic to identify front-7 players.

    Returns:
        DataFrame with columns: team, season, week, front7_quality,
        front7_sacks, front7_pressures, front7_hurries, front7_tackles.
        Empty DataFrame if input is empty.
    """
    if pfr_def_df.empty:
        return pd.DataFrame()

    df = pfr_def_df.copy()

    # Ensure required columns exist
    required = ["team", "season", "week"]
    stat_cols = {
        "def_sacks": "front7_sacks",
        "def_pressures": "front7_pressures",
        "def_times_hurried": "front7_hurries",
        "def_tackles_combined": "front7_tackles",
    }
    for col in required:
        if col not in df.columns:
            logger.warning("Missing required column %s in PFR def data", col)
            return pd.DataFrame()

    # Filter to front-7 positions if rosters available
    if rosters_df is not None and not rosters_df.empty:
        # Try to join on name + team to get position
        roster = rosters_df.copy()

        # Standardize name column
        name_col = None
        for candidate in ["full_name", "player_name", "player", "name"]:
            if candidate in roster.columns:
                name_col = candidate
                break

        pos_col = None
        for candidate in ["position", "pos"]:
            if candidate in roster.columns:
                pos_col = candidate
                break

        if name_col and pos_col:
            # Build lookup: (name, team) -> position
            roster_lookup = roster.drop_duplicates(subset=[name_col, "team"]).set_index(
                [name_col, "team"]
            )[pos_col]

            if "pfr_player_name" in df.columns:
                df["_position"] = df.apply(
                    lambda r: roster_lookup.get(
                        (r.get("pfr_player_name"), r.get("team")), None
                    ),
                    axis=1,
                )
                df = df[
                    df["_position"].isin(_FRONT7_POSITIONS) | df["_position"].isna()
                ]
                df = df.drop(columns=["_position"])
    else:
        # Heuristic: keep players with any sacks, pressures, or hurries > 0
        # (likely DL/EDGE/LB) when no roster data available
        mask = pd.Series(False, index=df.index)
        for col in ["def_sacks", "def_pressures", "def_times_hurried"]:
            if col in df.columns:
                mask = mask | (df[col].fillna(0) > 0)
        # Also keep players with high tackle counts (likely LBs)
        if "def_tackles_combined" in df.columns:
            mask = mask | (df["def_tackles_combined"].fillna(0) >= 5)
        if mask.any():
            df = df[mask]

    # Fill missing stat columns with 0
    for src_col in stat_cols:
        if src_col not in df.columns:
            df[src_col] = 0.0

    # Aggregate to team-week level
    agg_dict = {col: "sum" for col in stat_cols if col in df.columns}
    team_week = df.groupby(["team", "season", "week"]).agg(agg_dict).reset_index()

    # Rename to output column names
    team_week = team_week.rename(columns=stat_cols)

    # Compute composite quality score
    team_week["front7_quality_raw"] = (
        _SACK_WEIGHT * team_week.get("front7_sacks", 0)
        + _PRESSURE_WEIGHT * team_week.get("front7_pressures", 0)
        + _HURRY_WEIGHT * team_week.get("front7_hurries", 0)
        + _TACKLE_WEIGHT * team_week.get("front7_tackles", 0)
    )

    # Rolling 3-game average with shift(1) for temporal lag
    team_week = team_week.sort_values(["team", "season", "week"])

    roll_cols = [
        "front7_quality_raw",
        "front7_sacks",
        "front7_pressures",
        "front7_hurries",
        "front7_tackles",
    ]
    for col in roll_cols:
        if col not in team_week.columns:
            continue
        team_week[col + "_roll3"] = team_week.groupby(["team", "season"])[
            col
        ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

    # Use rolling values as the primary output
    team_week["front7_quality"] = team_week["front7_quality_raw_roll3"]
    for src, tgt in stat_cols.items():
        roll_name = tgt + "_roll3"
        if roll_name in team_week.columns:
            team_week[tgt] = team_week[roll_name]

    # Select output columns
    out_cols = [
        "team",
        "season",
        "week",
        "front7_quality",
        "front7_sacks",
        "front7_pressures",
        "front7_hurries",
        "front7_tackles",
    ]
    for c in out_cols:
        if c not in team_week.columns:
            team_week[c] = np.nan

    result = team_week[out_cols].copy()
    logger.info("Computed defensive front quality: %d team-week rows", len(result))
    return result


def build_defends_run_edges(
    graph_db: "GraphDB",  # noqa: F821
    def_front_df: pd.DataFrame,
) -> int:
    """Create [:DEFENDS_RUN] edges per team per week in Neo4j.

    Args:
        graph_db: Connected GraphDB instance.
        def_front_df: Output of compute_defensive_front_quality with
            team, season, week, front7_quality columns.

    Returns:
        Number of edges created. 0 if Neo4j unavailable.
    """
    if not graph_db.is_connected or def_front_df.empty:
        return 0

    count = 0
    for _, row in def_front_df.iterrows():
        if pd.isna(row.get("front7_quality")):
            continue
        graph_db.run_write(
            "MATCH (t:Team {abbr: $team}) "
            "MATCH (g:Game {season: $season, week: $week}) "
            "WHERE g.home_team = $team OR g.away_team = $team "
            "MERGE (t)-[r:DEFENDS_RUN {season: $season, week: $week}]->(g) "
            "SET r.front7_quality = $quality, "
            "    r.front7_sacks = $sacks, "
            "    r.front7_pressures = $pressures",
            {
                "team": row["team"],
                "season": int(row["season"]),
                "week": int(row["week"]),
                "quality": float(row["front7_quality"]),
                "sacks": float(row.get("front7_sacks", 0) or 0),
                "pressures": float(row.get("front7_pressures", 0) or 0),
            },
        )
        count += 1

    logger.info("Created %d DEFENDS_RUN edges", count)
    return count
