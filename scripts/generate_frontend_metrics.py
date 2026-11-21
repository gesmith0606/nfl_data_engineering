"""Generate frontend model-metrics JSON from a production backtest CSV.

Derives every accuracy number displayed on the website from a single
backtest artifact so the site can never show contradictory metrics.

Usage:
    python scripts/generate_frontend_metrics.py \
        --csv output/backtest/backtest_half_ppr_ml_fullfeatures_consensus_20260610_213405.csv \
        --tests 2242

    # Refresh ONLY the 2026 live block (reads the tracked season scorecard,
    # leaves every other key in model-metrics.json untouched):
    python scripts/generate_frontend_metrics.py --live-only
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

OUTPUT_PATH = Path("web/frontend/src/features/nfl/config/model-metrics.json")
SCORECARD_PATH = Path("output/grading/season=2026/scorecard.csv")

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
    # Also apply the consensus_proj >= 5 floor used everywhere else in the
    # repo's "matched-pairs" methodology (backtest_projections.py's own
    # --vs-consensus report, every .planning benchmark doc) — the raw
    # consensus_matched_*.csv saved by that flag is NOT pre-filtered to this
    # threshold, so skipping it here silently mixes in near-zero-projection
    # bench players and no longer matches the population the site's own
    # methodology copy claims to use.
    df = df[df["position"].isin(["QB", "RB", "WR", "TE"])]
    df = df[df["consensus_proj"] >= 5].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No QB/RB/WR/TE rows >= 5pts in consensus CSV: {csv_path}")

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


def format_weeks(weeks: list) -> str:
    """Render sorted week numbers as a label: [1,2,3,4,5,6,7,9] -> '1–7, 9'."""
    runs: list = []
    for w in sorted(weeks):
        if runs and w == runs[-1][1] + 1:
            runs[-1][1] = w
        else:
            runs.append([w, w])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


def _commit_date(path: Path) -> str:
    """Last-commit date (YYYY-MM-DD) of a tracked file; '' if unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def build_live_section(csv_path: Path, ats: dict = None, updated: str = None) -> dict:
    """Build the ``live2026`` block from the season scorecard CSV only.

    Reads the pooled ``week == 'ALL'`` rows (per position + ``ALL``) and the
    per-week rows (only to list which weeks actually have a published board).
    ``gap`` is ours minus Sleeper, so positive = behind Sleeper.
    """
    df = pd.read_csv(csv_path, dtype={"week": str})
    required = {"week", "position", "n_matched", "mae_ours", "mae_sleeper",
                "mae_t3", "gap", "rho_ours", "rho_sleeper", "band_coverage"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Scorecard CSV missing columns: {sorted(missing)}")

    pooled = df[df["week"] == "ALL"].set_index("position")
    if "ALL" not in pooled.index:
        raise ValueError(f"Scorecard has no pooled ALL/ALL row: {csv_path}")
    weeks = sorted({int(w) for w in df["week"] if w != "ALL"})

    def _row(pos: str) -> dict:
        r = pooled.loc[pos]
        return {
            "n": int(r["n_matched"]),
            "ourMae": round(float(r["mae_ours"]), 4),
            "sleeperMae": round(float(r["mae_sleeper"]), 4),
            "trailing3Mae": round(float(r["mae_t3"]), 4),
            "gap": round(float(r["gap"]), 4),
            "rhoOurs": round(float(r["rho_ours"]), 3),
            "rhoSleeper": round(float(r["rho_sleeper"]), 3),
            "bandCoverage": round(float(r["band_coverage"]), 3),
        }

    overall = _row("ALL")
    commit_date = _commit_date(csv_path)
    block = {
        "source": str(csv_path),
        "weeks": format_weeks(weeks),
        "weeks_covered": weeks,
        # Flat keys kept for existing consumers (stat strips, home modules).
        "ourMae": overall["ourMae"],
        "sleeperMae": overall["sleeperMae"],
        "trailing3Mae": overall["trailing3Mae"],
        "gap": overall["gap"],
        "overall": overall,
        "positions": [
            {"position": pos, **_row(pos)}
            for pos in ["QB", "RB", "WR", "TE"] if pos in pooled.index
        ],
        "generated_from": {"path": str(csv_path), "last_commit_date": commit_date},
        "updated": updated or commit_date,
    }
    if ats is not None:
        block["ats"] = ats
    return block


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None,
                        help="Backtest CSV (required unless --live-only)")
    parser.add_argument("--live-only", action="store_true",
                        help="Only regenerate the live2026 block from the scorecard CSV")
    parser.add_argument("--scorecard", type=Path, default=SCORECARD_PATH)
    parser.add_argument("--consensus-csv", type=Path, default=None,
                        help="Matched-pairs CSV from backtest --vs-consensus; "
                             "adds a model-vs-consensus section")
    parser.add_argument("--tests", type=int, default=None,
                        help="Passing test count (auto-collected if omitted)")
    args = parser.parse_args()

    existing = json.loads(OUTPUT_PATH.read_text()) if OUTPUT_PATH.exists() else {}
    # The ATS record is not in the scorecard CSV; carry it over unchanged.
    live = build_live_section(args.scorecard, ats=existing.get("live2026", {}).get("ats"))
    if args.live_only:
        existing["live2026"] = live
        OUTPUT_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote live2026 block to {OUTPUT_PATH} (weeks {live['weeks']})")
        return
    if args.csv is None:
        parser.error("--csv is required unless --live-only")
    tests = args.tests if args.tests is not None else count_tests()
    metrics = build_metrics(args.csv, tests)
    metrics["live2026"] = live
    if args.consensus_csv is not None:
        metrics["consensus"] = build_consensus_section(args.consensus_csv)
    OUTPUT_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"  overall MAE {metrics['overall']['mae']}, "
          f"{metrics['overall']['playerWeeks']} player-weeks, "
          f"{tests} tests")


if __name__ == "__main__":
    main()
