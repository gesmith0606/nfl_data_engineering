#!/usr/bin/env python3
"""Silver Player Quality Transformation.

Aggregates Bronze player data (weekly stats, depth charts, injuries)
to team-level per-week player quality features.

Output: data/silver/teams/player_quality/season=YYYY/

Features produced:
- qb_passing_epa: Starting QB's passing EPA per game
- backup_qb_start: Boolean flag when non-depth-chart QB started
- rb_weighted_epa: Top-2 RB rushing EPA weighted by carry share
- wr_te_weighted_epa: Top-3 WR/TE receiving EPA weighted by target share
- qb_injury_impact: QB injury impact score (1 - multiplier)
- skill_injury_impact: Skill position (RB/WR/TE) injury impact
- def_injury_impact: Defensive position injury impact
- All numeric features get _roll3, _roll6, _std via apply_team_rolling()

Usage:
    python scripts/silver_player_quality_transformation.py --seasons 2020 2021 2022 2023 2024
"""

import argparse
import glob as globmod
import logging
import os
import sys
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from team_analytics import apply_team_rolling

logger = logging.getLogger(__name__)

BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")

INJURY_MULTIPLIERS = {
    "Active": 1.0,
    "Questionable": 0.85,
    "Doubtful": 0.50,
    "Out": 0.0,
    "IR": 0.0,
    "PUP": 0.0,
}

# Position groups for injury impact
_SKILL_POSITIONS = {"RB", "WR", "TE"}
_DEF_POSITIONS = {"DE", "DT", "LB", "CB", "S", "DB", "ILB", "OLB", "MLB", "FS", "SS", "NT"}


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------


def _read_local_bronze(data_type: str, season: int) -> pd.DataFrame:
    """Read the latest parquet file from local Bronze directory.

    Args:
        data_type: Bronze data type (e.g., 'player_weekly', 'depth_charts', 'injuries').
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if not found.
    """
    pattern = os.path.join(BRONZE_DIR, data_type, f"season={season}", "*.parquet")
    files = sorted(globmod.glob(pattern))
    if not files:
        logger.warning("No Bronze %s data for season %d", data_type, season)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _save_local_silver(df: pd.DataFrame, key: str) -> str:
    """Save DataFrame to the local Silver directory.

    Args:
        df: DataFrame to save.
        key: Relative path within Silver directory.

    Returns:
        Absolute path to saved file.
    """
    path = os.path.join(SILVER_DIR, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"    Saved -> data/silver/{key}")
    return path


# ---------------------------------------------------------------------------
# Feature computation functions
# ---------------------------------------------------------------------------


def compute_qb_quality(
    weekly_df: pd.DataFrame, depth_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute QB quality metrics per team per week.

    Selects the starting QB (most passing attempts) and computes passing EPA.
    Detects backup QB starts by comparing depth chart starter vs actual starter.

    Args:
        weekly_df: Bronze weekly stats with player_id, recent_team, season, week,
            position, passing_epa, attempts columns.
        depth_df: Bronze depth charts with club_code, pos_abb, depth_team,
            gsis_id, week, season columns.

    Returns:
        DataFrame with [team, season, week, qb_passing_epa, backup_qb_start].
    """
    # Filter to QBs only
    qb_weekly = weekly_df[weekly_df["position"] == "QB"].copy()
    if qb_weekly.empty:
        return pd.DataFrame(columns=["team", "season", "week", "qb_passing_epa", "backup_qb_start"])

    # Find the QB with most attempts per team per week (actual starter)
    qb_weekly = qb_weekly.rename(columns={"recent_team": "team"})
    idx = qb_weekly.groupby(["team", "season", "week"])["attempts"].idxmax()
    starters = qb_weekly.loc[idx, ["team", "season", "week", "passing_epa", "player_id"]].copy()
    starters = starters.rename(columns={
        "passing_epa": "qb_passing_epa",
        "player_id": "actual_starter_id",
    })

    # Get depth chart starters (QB, depth_team='1')
    # depth_charts use 'position' column (not 'pos_abb') and 'club_code' for team
    pos_col = "pos_abb" if "pos_abb" in depth_df.columns else "position"
    has_depth_team = "depth_team" in depth_df.columns
    if not depth_df.empty and pos_col in depth_df.columns and has_depth_team:
        dc_qb = depth_df[
            (depth_df[pos_col] == "QB") & (depth_df["depth_team"].astype(str) == "1")
        ].copy()
        # Convert week to int if float (depth charts use float64, may have NaN)
        dc_qb = dc_qb.dropna(subset=["week"])
        dc_qb["week"] = dc_qb["week"].astype(int)
        dc_qb = dc_qb.rename(columns={"club_code": "team", "gsis_id": "dc_starter_id"})
        dc_qb = dc_qb[["team", "season", "week", "dc_starter_id"]].drop_duplicates(
            subset=["team", "season", "week"], keep="first"
        )

        # Merge depth chart info
        starters = starters.merge(
            dc_qb, on=["team", "season", "week"], how="left"
        )
        # Backup QB start = depth chart starter differs from actual starter
        # Note: depth chart uses gsis_id, weekly uses player_id — same format (00-XXXXXXX)
        starters["backup_qb_start"] = (
            starters["dc_starter_id"].notna()
            & (starters["actual_starter_id"] != starters["dc_starter_id"])
        )
    else:
        starters["backup_qb_start"] = False

    result = starters[["team", "season", "week", "qb_passing_epa", "backup_qb_start"]].copy()
    result["backup_qb_start"] = result["backup_qb_start"].fillna(False).astype(bool)
    return result.reset_index(drop=True)


def compute_positional_quality(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Compute positional quality metrics per team per week.

    - rb_weighted_epa: Top 2 RBs by carries, weighted by carry_share
    - wr_te_weighted_epa: Top 3 WR/TEs by targets, weighted by target_share

    carry_share is computed as carries/team_total_carries (not from Bronze).

    Args:
        weekly_df: Bronze weekly stats DataFrame.

    Returns:
        DataFrame with [team, season, week, rb_weighted_epa, wr_te_weighted_epa].
    """
    df = weekly_df.copy()
    df = df.rename(columns={"recent_team": "team"})

    # --- RB weighted EPA ---
    rb_df = df[df["position"] == "RB"].copy()
    # Compute carry_share per team per week
    team_carries = rb_df.groupby(["team", "season", "week"])["carries"].transform("sum")
    rb_df["carry_share"] = np.where(team_carries > 0, rb_df["carries"] / team_carries, 0.0)

    # Top 2 RBs by carries per team per week
    rb_df = rb_df.sort_values(["team", "season", "week", "carries"], ascending=[True, True, True, False])
    rb_top2 = rb_df.groupby(["team", "season", "week"]).head(2)

    # Weighted EPA = sum(rushing_epa * carry_share) / sum(carry_share)
    rb_agg = rb_top2.groupby(["team", "season", "week"]).apply(
        lambda g: pd.Series({
            "rb_weighted_epa": (
                (g["rushing_epa"] * g["carry_share"]).sum() / g["carry_share"].sum()
                if g["carry_share"].sum() > 0
                else 0.0
            )
        })
    ).reset_index()

    # --- WR/TE weighted EPA ---
    wrte_df = df[df["position"].isin(["WR", "TE"])].copy()

    # Compute target count from target_share * team total targets (approximate)
    # Since we have target_share directly, use it for weighting
    wrte_df = wrte_df.sort_values(
        ["team", "season", "week", "target_share"], ascending=[True, True, True, False]
    )
    wrte_top3 = wrte_df.groupby(["team", "season", "week"]).head(3)

    wrte_agg = wrte_top3.groupby(["team", "season", "week"]).apply(
        lambda g: pd.Series({
            "wr_te_weighted_epa": (
                (g["receiving_epa"] * g["target_share"]).sum() / g["target_share"].sum()
                if g["target_share"].sum() > 0
                else 0.0
            )
        })
    ).reset_index()

    # Merge RB and WR/TE results
    result = rb_agg.merge(wrte_agg, on=["team", "season", "week"], how="outer")
    result["rb_weighted_epa"] = result["rb_weighted_epa"].fillna(0.0)
    result["wr_te_weighted_epa"] = result["wr_te_weighted_epa"].fillna(0.0)

    return result[["team", "season", "week", "rb_weighted_epa", "wr_te_weighted_epa"]].reset_index(drop=True)


def compute_injury_impact(
    injury_df: pd.DataFrame, weekly_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute injury impact scores per team per week by position group.

    Impact = sum(player_usage_share * (1 - injury_multiplier)) per group.
    Active=1.0, Questionable=0.85, Doubtful=0.50, Out/IR/PUP=0.0.

    Args:
        injury_df: Bronze injuries with gsis_id, position, report_status,
            team, season, week columns.
        weekly_df: Bronze weekly stats for usage share context.

    Returns:
        DataFrame with [team, season, week, qb_injury_impact,
        skill_injury_impact, def_injury_impact].
    """
    # Get all team-week combinations from weekly data
    wk = weekly_df.copy()
    wk = wk.rename(columns={"recent_team": "team"})
    team_weeks = wk[["team", "season", "week"]].drop_duplicates()

    if injury_df.empty:
        team_weeks["qb_injury_impact"] = 0.0
        team_weeks["skill_injury_impact"] = 0.0
        team_weeks["def_injury_impact"] = 0.0
        return team_weeks.reset_index(drop=True)

    inj = injury_df.copy()
    # Map injury status to multiplier
    inj["multiplier"] = inj["report_status"].map(INJURY_MULTIPLIERS).fillna(1.0)
    inj["impact"] = 1.0 - inj["multiplier"]

    # Compute usage shares from weekly data
    # QB: attempts-based
    qb_wk = wk[wk["position"] == "QB"].copy()
    team_qb_attempts = qb_wk.groupby(["team", "season", "week"])["attempts"].transform("sum")
    qb_wk["usage_share"] = np.where(team_qb_attempts > 0, qb_wk["attempts"] / team_qb_attempts, 0.0)
    # Rename player_id to gsis_id for join with injuries (same format: 00-XXXXXXX)
    qb_wk = qb_wk.rename(columns={"player_id": "gsis_id"})
    qb_usage = qb_wk[["gsis_id", "team", "season", "week", "usage_share"]].copy()

    # Skill: target_share for WR/TE, carry_share for RB
    rb_wk = wk[wk["position"] == "RB"].copy()
    team_carries = rb_wk.groupby(["team", "season", "week"])["carries"].transform("sum")
    rb_wk["usage_share"] = np.where(team_carries > 0, rb_wk["carries"] / team_carries, 0.0)
    rb_wk = rb_wk.rename(columns={"player_id": "gsis_id"})
    rb_usage = rb_wk[["gsis_id", "team", "season", "week", "usage_share"]].copy()

    wrte_wk = wk[wk["position"].isin(["WR", "TE"])].copy()
    wrte_wk["usage_share"] = wrte_wk["target_share"].fillna(0.0)
    wrte_wk = wrte_wk.rename(columns={"player_id": "gsis_id"})
    wrte_usage = wrte_wk[["gsis_id", "team", "season", "week", "usage_share"]].copy()

    skill_usage = pd.concat([rb_usage, wrte_usage], ignore_index=True)

    # --- QB injury impact ---
    qb_inj = inj[inj["position"] == "QB"].copy()
    qb_impact = _compute_group_impact(qb_inj, qb_usage, team_weeks, "qb_injury_impact")

    # --- Skill injury impact ---
    skill_inj = inj[inj["position"].isin(_SKILL_POSITIONS)].copy()
    skill_impact = _compute_group_impact(skill_inj, skill_usage, team_weeks, "skill_injury_impact")

    # --- Defensive injury impact ---
    def_inj = inj[inj["position"].isin(_DEF_POSITIONS)].copy()
    # For defense, use equal weighting (no usage share in weekly data)
    def_impact = _compute_def_impact(def_inj, team_weeks)

    # Merge all
    result = team_weeks.merge(qb_impact, on=["team", "season", "week"], how="left")
    result = result.merge(skill_impact, on=["team", "season", "week"], how="left")
    result = result.merge(def_impact, on=["team", "season", "week"], how="left")

    for col in ["qb_injury_impact", "skill_injury_impact", "def_injury_impact"]:
        result[col] = result[col].fillna(0.0)

    return result[["team", "season", "week", "qb_injury_impact", "skill_injury_impact", "def_injury_impact"]].reset_index(drop=True)


def _compute_group_impact(
    inj_group: pd.DataFrame,
    usage_df: pd.DataFrame,
    team_weeks: pd.DataFrame,
    col_name: str,
) -> pd.DataFrame:
    """Compute injury impact for a position group using usage shares.

    Args:
        inj_group: Injuries filtered to a position group.
        usage_df: Usage shares with [gsis_id, team, season, week, usage_share].
        team_weeks: All team-week combinations.
        col_name: Output column name.

    Returns:
        DataFrame with [team, season, week, col_name].
    """
    if inj_group.empty:
        result = team_weeks[["team", "season", "week"]].copy()
        result[col_name] = 0.0
        return result

    # Join injuries with usage
    merged = inj_group.merge(
        usage_df,
        on=["gsis_id", "team", "season", "week"],
        how="left",
    )
    merged["usage_share"] = merged["usage_share"].fillna(1.0)  # Default full share for QB
    merged["weighted_impact"] = merged["usage_share"] * merged["impact"]

    agg = merged.groupby(["team", "season", "week"])["weighted_impact"].sum().reset_index()
    agg = agg.rename(columns={"weighted_impact": col_name})

    return agg[["team", "season", "week", col_name]]


def _compute_def_impact(
    def_inj: pd.DataFrame, team_weeks: pd.DataFrame
) -> pd.DataFrame:
    """Compute defensive injury impact using equal weighting.

    Args:
        def_inj: Injuries for defensive positions.
        team_weeks: All team-week combinations.

    Returns:
        DataFrame with [team, season, week, def_injury_impact].
    """
    if def_inj.empty:
        result = team_weeks[["team", "season", "week"]].copy()
        result["def_injury_impact"] = 0.0
        return result

    agg = def_inj.groupby(["team", "season", "week"])["impact"].sum().reset_index()
    agg = agg.rename(columns={"impact": "def_injury_impact"})
    return agg[["team", "season", "week", "def_injury_impact"]]


# ---------------------------------------------------------------------------
# Season orchestration
# ---------------------------------------------------------------------------


def transform_season(season: int) -> Optional[pd.DataFrame]:
    """Run full player quality transformation for a season.

    Reads Bronze player_weekly, depth_charts, and injuries data.
    Computes QB quality, positional quality, and injury impact.
    Applies rolling averages via apply_team_rolling().

    Args:
        season: NFL season year.

    Returns:
        Transformed DataFrame or None if no data available.
    """
    print(f"  Loading Bronze data for season {season}...")

    weekly_df = _read_local_bronze("players/weekly", season)
    if weekly_df.empty:
        print(f"    WARNING: No weekly data for season {season}, skipping.")
        return None

    depth_df = _read_local_bronze("depth_charts", season)
    if depth_df.empty:
        print(f"    WARNING: No depth chart data for {season}, QB backup detection limited.")

    injury_df = _read_local_bronze("players/injuries", season)
    if injury_df.empty:
        print(f"    WARNING: No injury data for {season}, injury impact will be zero.")

    print(f"  Computing QB quality...")
    qb_df = compute_qb_quality(weekly_df, depth_df)

    print(f"  Computing positional quality...")
    pos_df = compute_positional_quality(weekly_df)

    print(f"  Computing injury impact...")
    inj_df = compute_injury_impact(injury_df, weekly_df)

    # Merge all on [team, season, week]
    result = qb_df.merge(pos_df, on=["team", "season", "week"], how="outer")
    result = result.merge(inj_df, on=["team", "season", "week"], how="outer")

    # Fill NaN for numeric columns
    numeric_cols = [
        "qb_passing_epa", "rb_weighted_epa", "wr_te_weighted_epa",
        "qb_injury_impact", "skill_injury_impact", "def_injury_impact",
    ]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0.0)
    if "backup_qb_start" in result.columns:
        result["backup_qb_start"] = result["backup_qb_start"].fillna(False).astype(bool)

    # Apply rolling averages (shift(1) inside apply_team_rolling)
    stat_cols = [
        "qb_passing_epa",
        "rb_weighted_epa",
        "wr_te_weighted_epa",
        "qb_injury_impact",
        "skill_injury_impact",
        "def_injury_impact",
    ]
    print(f"  Applying rolling averages...")
    result = apply_team_rolling(result, stat_cols, windows=[3, 6])

    print(
        f"    Player quality: {len(result):,} rows, "
        f"{result['team'].nunique()} teams, "
        f"{len(result.columns)} columns"
    )
    return result


def main() -> int:
    """Parse CLI arguments and run Silver player quality transformation."""
    parser = argparse.ArgumentParser(
        description="NFL Silver Layer - Player Quality Transformation"
    )
    parser.add_argument("--season", type=int, help="Single NFL season to transform")
    parser.add_argument(
        "--seasons", type=int, nargs="+", help="Multiple seasons to transform"
    )
    args = parser.parse_args()

    seasons = args.seasons or ([args.season] if args.season else [2024])

    print("NFL Silver Layer - Player Quality Transformation")
    print(f"Seasons: {seasons}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for season in seasons:
        print(f"\n{'=' * 60}")
        print(f"Processing Season {season}")
        print("=" * 60)

        result = transform_season(season)
        if result is None:
            continue

        # Save to Silver
        key = f"teams/player_quality/season={season}/player_quality_{ts}.parquet"
        _save_local_silver(result, key)

        print(f"  Season {season} complete.")

    print("\nSilver player quality transformation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
