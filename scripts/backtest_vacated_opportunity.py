#!/usr/bin/env python3
"""Backtest the vacated-opportunity boost (UC1) on historical preseason runs.

For each target season, generates preseason projections twice from the two
prior seasons of Bronze seasonal data — baseline vs with the UC1 vacated
opportunity multiplier — and scores both against actual season fantasy
points (sum of weekly, weeks 1-18). Consensus anchor and the low-sample
synthesizer are disabled in both arms so the comparison isolates the boost.

Ship gate (.planning/GRAPH_USECASES_2026_07.md): RB Spearman or MAE must
improve without degrading the other positions.

Usage:
    python scripts/backtest_vacated_opportunity.py --seasons 2023 2024 2025
    python scripts/backtest_vacated_opportunity.py --seasons 2024 --scoring ppr
"""

import argparse
import glob
import logging
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_vacated_opportunity import build_vacated_opportunity_data
from projection_engine import generate_preseason_projections
from scoring_calculator import calculate_fantasy_points_df

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")

POSITIONS = ["QB", "RB", "WR", "TE"]

# Minimum actual games played for a player to score in the eval — players
# who missed most of the season (injury) add noise unrelated to preseason
# rank quality.
MIN_ACTUAL_GAMES = 8

# Only evaluate fantasy-relevant projections; deep-bench noise swamps MAE.
TOP_N_PER_POSITION = {"QB": 32, "RB": 60, "WR": 80, "TE": 32}


def _read_bronze(subdir: str, season: int) -> pd.DataFrame:
    """Read latest Bronze parquet for subdir/season (week-partition fallback)."""
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


def load_seasonal(seasons: List[int]) -> pd.DataFrame:
    """Concatenate Bronze seasonal data for the given seasons."""
    dfs = []
    for s in seasons:
        df = _read_bronze("players/seasonal", s)
        if not df.empty:
            if "season" not in df.columns:
                df["season"] = s
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def compute_actuals(target_season: int, scoring: str) -> pd.DataFrame:
    """Actual season fantasy points per player from Bronze weekly data.

    Returns:
        DataFrame with player_id, position, actual_points, games.
    """
    weekly = _read_bronze("players/weekly", target_season)
    if weekly.empty:
        return pd.DataFrame()
    weekly = weekly[weekly["week"] <= 18].copy()
    weekly = calculate_fantasy_points_df(
        weekly, scoring_format=scoring, output_col="_pts"
    )
    actual = weekly.groupby("player_id", as_index=False).agg(
        actual_points=("_pts", "sum"),
        games=("week", "nunique"),
        position=("position", "first"),
    )
    return actual


def score_arm(proj: pd.DataFrame, actual: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Score one projection arm: per-position Spearman + MAE on matched players."""
    merged = proj.merge(
        actual[["player_id", "actual_points", "games"]], on="player_id", how="inner"
    )
    merged = merged[merged["games"] >= MIN_ACTUAL_GAMES]

    out: Dict[str, Dict[str, float]] = {}
    for pos in POSITIONS:
        sub = merged[merged["position"] == pos].copy()
        top_n = TOP_N_PER_POSITION[pos]
        sub = sub.nlargest(top_n, "projected_season_points")
        if len(sub) < 10:
            out[pos] = {"n": len(sub), "spearman": np.nan, "mae": np.nan}
            continue
        rho, _ = spearmanr(sub["projected_season_points"], sub["actual_points"])
        mae = float(
            (sub["projected_season_points"] - sub["actual_points"]).abs().mean()
        )
        out[pos] = {"n": len(sub), "spearman": float(rho), "mae": mae}
    return out


def run_transition(target_season: int, scoring: str) -> Optional[pd.DataFrame]:
    """Run baseline vs vacated-boost preseason projections for one season."""
    prior_two = [target_season - 2, target_season - 1]
    seasonal = load_seasonal(prior_two)
    if seasonal.empty:
        print(f"  !! no seasonal data for {prior_two} — skipping {target_season}")
        return None

    actual = compute_actuals(target_season, scoring)
    if actual.empty:
        print(f"  !! no actuals for {target_season} — skipping")
        return None

    vacated = build_vacated_opportunity_data(target_season)
    if vacated.empty:
        print(f"  !! no vacated features for {target_season} — skipping")
        return None

    base = generate_preseason_projections(
        seasonal, scoring_format=scoring, target_season=target_season
    )
    treated = generate_preseason_projections(
        seasonal,
        scoring_format=scoring,
        target_season=target_season,
        vacated_features_df=vacated,
    )

    base_scores = score_arm(base, actual)
    treated_scores = score_arm(treated, actual)

    rows = []
    for pos in POSITIONS:
        b, t = base_scores[pos], treated_scores[pos]
        rows.append(
            {
                "season": target_season,
                "position": pos,
                "n": b["n"],
                "spearman_base": round(b["spearman"], 4),
                "spearman_treated": round(t["spearman"], 4),
                "spearman_delta": round(t["spearman"] - b["spearman"], 4),
                "mae_base": round(b["mae"], 2),
                "mae_treated": round(t["mae"], 2),
                "mae_delta": round(t["mae"] - b["mae"], 2),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest UC1 vacated-opportunity boost on preseason projections"
    )
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=[2023, 2024, 2025],
        help="Target seasons to evaluate (each uses the two prior seasons)",
    )
    parser.add_argument("--scoring", default="half_ppr")
    args = parser.parse_args()

    all_results = []
    for season in args.seasons:
        print(f"\n=== Target season {season} (transition {season-1} -> {season}) ===")
        result = run_transition(season, args.scoring)
        if result is not None:
            all_results.append(result)
            print(result.to_string(index=False))

    if not all_results:
        print("No transitions evaluated.")
        return

    combined = pd.concat(all_results, ignore_index=True)
    print("\n=== Aggregate (mean across seasons) ===")
    agg = (
        combined.groupby("position")[
            [
                "spearman_base",
                "spearman_treated",
                "spearman_delta",
                "mae_base",
                "mae_treated",
                "mae_delta",
            ]
        ]
        .mean()
        .round(4)
        .reindex(POSITIONS)
    )
    print(agg.to_string())

    rb = agg.loc["RB"]
    others = agg.drop("RB")
    rb_improves = rb["spearman_delta"] > 0 or rb["mae_delta"] < 0
    others_ok = (others["spearman_delta"] >= -0.005).all()
    print(
        f"\nGate: RB improves={rb_improves}, others not degraded={others_ok} "
        f"-> {'SHIP' if rb_improves and others_ok else 'HOLD'}"
    )


if __name__ == "__main__":
    main()
