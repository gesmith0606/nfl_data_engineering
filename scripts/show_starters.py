#!/usr/bin/env python3
"""
CLI for displaying NFL team starting lineups.

Usage examples::

    python scripts/show_starters.py --season 2024 --week 17
    python scripts/show_starters.py --season 2024 --week 17 --team KC
    python scripts/show_starters.py --season 2024 --week 17 --position RB
    python scripts/show_starters.py --season 2024 --week 17 --team KC --projections
"""

import argparse
import sys
import os

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np

from lineup_builder import get_team_starters, get_team_lineup_with_projections

# Team full names for display
TEAM_NAMES = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams",
    "LV": "Las Vegas Raiders",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
    # Legacy codes
    "LA": "Los Angeles Rams",
    "OAK": "Oakland Raiders",
    "SD": "San Diego Chargers",
    "STL": "St. Louis Rams",
    "WFT": "Washington Football Team",
}


def _fmt_points(pts: float) -> str:
    """Format projected points, returning '--' for NaN."""
    if pd.isna(pts):
        return "--"
    return f"{pts:.1f}"


def _print_team_starters(df: pd.DataFrame, team: str, week: int) -> None:
    """Print formatted starters list for a single team."""
    team_name = TEAM_NAMES.get(team, team)
    print(f"\n{team_name} -- Week {week} Starters")
    print("=" * 55)

    offense = df[df["side"] == "offense"]
    defense = df[df["side"] == "defense"]

    if not offense.empty:
        print("\nOFFENSE")
        for _, row in offense.iterrows():
            snap_str = (
                f" ({row['snap_pct']:.0f}% snaps)"
                if pd.notna(row.get("snap_pct"))
                else ""
            )
            pg = row["position_group"]
            rank_suffix = f"{row['depth_rank']}" if row["depth_rank"] > 1 else ""
            label = f"{pg}{rank_suffix}"
            print(f"  {label:>4}: {row['player_name']:<22}{snap_str}")

    if not defense.empty:
        print("\nDEFENSE")
        for _, row in defense.iterrows():
            snap_str = (
                f" ({row['snap_pct']:.0f}% snaps)"
                if pd.notna(row.get("snap_pct"))
                else ""
            )
            pg = row["position_group"]
            rank_suffix = f"{row['depth_rank']}" if row["depth_rank"] > 1 else ""
            label = f"{pg}{rank_suffix}"
            print(f"  {label:>4}: {row['player_name']:<22}{snap_str}")


def _print_team_with_projections(df: pd.DataFrame, team: str, week: int) -> None:
    """Print formatted starters with projections for a single team."""
    team_name = TEAM_NAMES.get(team, team)
    print(f"\n{team_name} -- Week {week} Starters")
    print("=" * 60)

    offense = df[df["side"] == "offense"]
    defense = df[df["side"] == "defense"]

    team_total = 0.0

    if not offense.empty:
        print("\nOFFENSE")
        for _, row in offense.iterrows():
            pts = row.get("projected_points", np.nan)
            floor_pts = row.get("projected_floor", np.nan)
            ceil_pts = row.get("projected_ceiling", np.nan)

            if pd.notna(pts):
                team_total += pts
                proj_str = (
                    f"| {_fmt_points(pts):>5} pts "
                    f"({_fmt_points(floor_pts)} - {_fmt_points(ceil_pts)})"
                )
            else:
                proj_str = "|    -- pts"

            pg = row["position_group"]
            rank_suffix = f"{row['depth_rank']}" if row["depth_rank"] > 1 else ""
            label = f"{pg}{rank_suffix}"
            print(f"  {label:>4}: {row['player_name']:<22} {proj_str}")

    if not defense.empty:
        print("\nDEFENSE")
        for _, row in defense.iterrows():
            pg = row["position_group"]
            rank_suffix = f"{row['depth_rank']}" if row["depth_rank"] > 1 else ""
            label = f"{pg}{rank_suffix}"
            print(f"  {label:>4}: {row['player_name']:<22}")

    if team_total > 0:
        print(f"\nTEAM TOTAL: {team_total:.1f} pts")


def _print_position_summary(df: pd.DataFrame, position: str) -> None:
    """Print all starters at a given position across all teams."""
    # Filter to matching position group
    pos_upper = position.upper()
    filtered = df[df["position_group"] == pos_upper]
    if filtered.empty:
        print(f"No starters found for position: {pos_upper}")
        return

    # Keep only first starters (depth_rank 1) for clean list
    first = filtered[filtered["depth_rank"] == 1].copy()
    first = first.sort_values("team")

    print(f"\n{pos_upper} Starters -- All Teams")
    print("=" * 45)
    for _, row in first.iterrows():
        snap_str = f" ({row['snap_pct']:.0f}%)" if pd.notna(row.get("snap_pct")) else ""
        print(f"  {row['team']:>3}: {row['player_name']:<22}{snap_str}")
    print(f"\n{len(first)} teams listed")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Show NFL team starting lineups from depth charts + snap counts."
    )
    parser.add_argument(
        "--season", type=int, required=True, help="NFL season (e.g. 2024)"
    )
    parser.add_argument("--week", type=int, required=True, help="Week number (1-18)")
    parser.add_argument(
        "--team",
        type=str,
        default=None,
        help="Team abbreviation (e.g. KC, BUF). Omit for all teams.",
    )
    parser.add_argument(
        "--position",
        type=str,
        default=None,
        help="Filter to a position group (e.g. QB, RB, WR, TE, K).",
    )
    parser.add_argument(
        "--projections",
        action="store_true",
        help="Include fantasy projections (half_ppr default).",
    )
    parser.add_argument(
        "--scoring",
        type=str,
        default="half_ppr",
        choices=["ppr", "half_ppr", "standard"],
        help="Scoring format for projections (default: half_ppr).",
    )
    parser.add_argument(
        "--offense-only",
        action="store_true",
        help="Show only offensive starters.",
    )
    args = parser.parse_args()

    if args.position:
        # Position-level view across all teams
        df = get_team_starters(season=args.season, week=args.week, team=args.team)
        if df.empty:
            print("No data found.")
            return
        _print_position_summary(df, args.position)
        return

    if args.team and args.projections:
        # Single team with projections
        df = get_team_lineup_with_projections(
            season=args.season,
            week=args.week,
            team=args.team,
            scoring_format=args.scoring,
        )
        if df.empty:
            print(
                f"No data found for {args.team} season={args.season} week={args.week}"
            )
            return
        if args.offense_only:
            df = df[df["side"] == "offense"]
        _print_team_with_projections(df, args.team.upper(), args.week)
        return

    # Default: starters list (single team or all teams)
    df = get_team_starters(season=args.season, week=args.week, team=args.team)
    if df.empty:
        print("No data found.")
        return

    if args.offense_only:
        df = df[df["side"] == "offense"]

    if args.team:
        _print_team_starters(df, args.team.upper(), args.week)
    else:
        # All teams
        for t in sorted(df["team"].unique()):
            team_df = df[df["team"] == t]
            _print_team_starters(team_df, t, args.week)
        print(f"\n{df['team'].nunique()} teams, {len(df)} starters listed")


if __name__ == "__main__":
    main()
