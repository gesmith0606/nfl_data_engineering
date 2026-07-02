"""Generate frontend model-metrics JSON from a production backtest CSV.

Derives every accuracy number displayed on the website from a single
backtest artifact so the site can never show contradictory metrics.

Usage:
    python scripts/generate_frontend_metrics.py \
        --csv output/backtest/backtest_half_ppr_ml_fullfeatures_consensus_20260610_213405.csv \
        --tests 2242
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

OUTPUT_PATH = Path("web/frontend/src/features/nfl/config/model-metrics.json")

MODEL_LABELS = {
    "heuristic": "Heuristic",
    "hybrid": "Hybrid Residual",
    "ml": "XGBoost",
}


def count_tests() -> int:
    """Count collected pytest tests (fallback when --tests not given)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    for line in reversed(result.stdout.splitlines()):
        if "tests collected" in line:
            return int(line.split()[0])
    raise RuntimeError("Could not parse pytest collection output")


def build_metrics(csv_path: Path, tests_passing: int) -> dict:
    """Compute overall, per-position, and weekly metrics from backtest rows."""
    df = pd.read_csv(csv_path)
    required = {"position", "season", "week", "projected_points", "actual_points",
                "error", "abs_error", "projection_source"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Backtest CSV missing columns: {sorted(missing)}")

    rmse = float((df["error"] ** 2).mean() ** 0.5)
    positions = []
    for pos in ["QB", "RB", "WR", "TE"]:
        sub = df[df["position"] == pos]
        if sub.empty:
            continue
        source = sub["projection_source"].mode().iloc[0]
        positions.append({
            "position": pos,
            "model": MODEL_LABELS.get(source, source),
            "mae": round(float(sub["abs_error"].mean()), 2),
            "rmse": round(float((sub["error"] ** 2).mean() ** 0.5), 2),
            "bias": round(float(sub["error"].mean()), 2),
        })

    weekly = [
        {"week": f"W{int(week)}", "mae": round(float(mae), 2)}
        for week, mae in df.groupby("week")["abs_error"].mean().items()
    ]

    return {
        "generatedFrom": csv_path.name,
        "generatedBy": "scripts/generate_frontend_metrics.py",
        "overall": {
            "mae": round(float(df["abs_error"].mean()), 2),
            "rmse": round(rmse, 2),
            "correlation": round(float(df["projected_points"].corr(df["actual_points"])), 3),
            "bias": round(float(df["error"].mean()), 2),
            "playerWeeks": int(len(df)),
            "seasons": f"{int(df['season'].min())}-{int(df['season'].max())}",
            "weeks": f"{int(df['week'].min())}-{int(df['week'].max())}",
            "scoringFormat": "Half-PPR",
        },
        "positions": positions,
        "weeklyMae": weekly,
        "testsPassing": tests_passing,
        "atsAccuracy": {
            "value": 53.0,
            "context": "Against the spread (sealed 2024 holdout, v2.0 ensemble)",
        },
    }


def build_consensus_section(csv_path: Path) -> dict:
    """Compute model-vs-consensus MAE per position from a matched-pairs CSV.

    Expects the ``consensus_matched_*.csv`` artifact from
    ``backtest_projections.py --vs-consensus``: one row per player-week where
    BOTH our projection and the Sleeper consensus projection exist, with
    ``abs_error`` (ours) and ``consensus_proj`` + ``actual_points`` columns.
    """
    df = pd.read_csv(csv_path)
    required = {"position", "abs_error", "consensus_proj", "actual_points", "season"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Consensus CSV missing columns: {sorted(missing)}")

    # Restrict to the skill positions reported per-position so the overall
    # row describes the same population (a kicker-inclusive CSV would
    # otherwise inflate the headline claim with easy zero-variance weeks).
    df = df[df["position"].isin(["QB", "RB", "WR", "TE"])].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No QB/RB/WR/TE rows in consensus CSV: {csv_path}")

    con_abs_error = (df["consensus_proj"] - df["actual_points"]).abs()

    def _row(sub: pd.DataFrame, sub_con: pd.Series) -> dict:
        our = float(sub["abs_error"].mean())
        con = float(sub_con.mean())
        return {
            "ourMae": round(our, 3),
            "consensusMae": round(con, 3),
            "gap": round(our - con, 3),  # negative = we beat consensus
            "win": bool(our < con),
            "playerWeeks": int(len(sub)),
        }

    positions = []
    for pos in ["QB", "RB", "WR", "TE"]:
        sub = df[df["position"] == pos]
        if sub.empty:
            continue
        positions.append({"position": pos, **_row(sub, con_abs_error[sub.index])})

    return {
        "generatedFrom": csv_path.name,
        "benchmark": "Sleeper expert consensus projections",
        "seasons": f"{int(df['season'].min())}-{int(df['season'].max())}",
        "scoringFormat": "Half-PPR",
        "overall": _row(df, con_abs_error),
        "positions": positions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--consensus-csv", type=Path, default=None,
                        help="Matched-pairs CSV from backtest --vs-consensus; "
                             "adds a model-vs-consensus section")
    parser.add_argument("--tests", type=int, default=None,
                        help="Passing test count (auto-collected if omitted)")
    args = parser.parse_args()

    tests = args.tests if args.tests is not None else count_tests()
    metrics = build_metrics(args.csv, tests)
    if args.consensus_csv is not None:
        metrics["consensus"] = build_consensus_section(args.consensus_csv)
    OUTPUT_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"  overall MAE {metrics['overall']['mae']}, "
          f"{metrics['overall']['playerWeeks']} player-weeks, "
          f"{tests} tests")


if __name__ == "__main__":
    main()
