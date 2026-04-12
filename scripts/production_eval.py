#!/usr/bin/env python3
"""Production-Faithful Evaluation (PFE) tool.

Wraps backtest_projections.py with:
- Named experiments and baselines
- Cached feature assembly across runs
- Single-line delta reporting vs a named baseline
- JSON summary output for programmatic comparison

Usage:
    # Run iteration eval (2024)
    python scripts/production_eval.py --experiment ridge_60f --seasons 2024

    # Run sealed ship-gate eval (2025)
    python scripts/production_eval.py --experiment ridge_60f --seasons 2025 --gate

    # Compare two experiments
    python scripts/production_eval.py --compare ridge_60f lgb_60f
"""

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import the production backtest — this is the single source of truth
sys.path.insert(0, os.path.dirname(__file__))
from backtest_projections import run_backtest  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EVAL_OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "output", "eval"
)

# Ship gate thresholds per the PFE protocol spec
SHIP_GATE_MIN_MAE_IMPROVEMENT = 0.10  # pts — minimum improvement per position
SHIP_GATE_MAX_BIAS_ITER = 0.5  # pts — max bias magnitude on iteration (2024) set
SHIP_GATE_MAX_BIAS_GATE = 1.0  # pts — max bias magnitude on sealed gate (2025)

POSITIONS = ["QB", "RB", "WR", "TE"]


def _summary_path(experiment_name: str) -> str:
    """Return absolute path to the summary JSON for a named experiment.

    Args:
        experiment_name: Short identifier for the experiment.

    Returns:
        Absolute path string for the summary JSON file.
    """
    return os.path.join(EVAL_OUTPUT_DIR, experiment_name, "summary.json")


def _load_summary(experiment_name: str) -> Optional[Dict]:
    """Load a saved experiment summary from disk.

    Args:
        experiment_name: Short identifier for the experiment.

    Returns:
        Parsed summary dict, or None if the file does not exist.
    """
    path = _summary_path(experiment_name)
    if not os.path.exists(path):
        return None
    with open(path, "r") as fh:
        return json.load(fh)


def _extract_metrics(results_df: pd.DataFrame) -> Dict:
    """Compute position-level and overall MAE / bias from backtest results.

    Args:
        results_df: DataFrame returned by run_backtest() containing
            ``abs_error``, ``error``, ``position``, and optionally
            ``projection_source`` columns.

    Returns:
        Dict with keys: overall_mae, overall_bias, position_mae,
        position_bias, by_source.
    """
    overall_mae = float(results_df["abs_error"].mean())
    overall_bias = float(results_df["error"].mean())

    position_mae: Dict[str, float] = {}
    position_bias: Dict[str, float] = {}
    for pos in POSITIONS:
        pos_df = results_df[results_df["position"] == pos]
        if pos_df.empty:
            continue
        position_mae[pos] = float(pos_df["abs_error"].mean())
        position_bias[pos] = float(pos_df["error"].mean())

    by_source: Dict[str, float] = {}
    if "projection_source" in results_df.columns:
        for src in sorted(results_df["projection_source"].unique()):
            src_df = results_df[results_df["projection_source"] == src]
            by_source[str(src)] = float(src_df["abs_error"].mean())

    return {
        "overall_mae": overall_mae,
        "overall_bias": overall_bias,
        "position_mae": position_mae,
        "position_bias": position_bias,
        "by_source": by_source,
    }


def _save_summary(
    experiment_name: str,
    metrics: Dict,
    seasons: List[int],
    is_gate: bool,
    baseline_name: Optional[str],
    delta: Optional[Dict],
) -> str:
    """Persist experiment summary to JSON.

    Args:
        experiment_name: Short identifier for the experiment.
        metrics: Dict from _extract_metrics().
        seasons: Seasons evaluated.
        is_gate: Whether this was a sealed gate run.
        baseline_name: Name of the baseline experiment, if any.
        delta: Delta dict from _compute_delta(), if any.

    Returns:
        Path to the written summary file.
    """
    summary = {
        "experiment": experiment_name,
        "timestamp": datetime.utcnow().isoformat(),
        "seasons": seasons,
        "is_gate": is_gate,
        "overall_mae": metrics["overall_mae"],
        "overall_bias": metrics["overall_bias"],
        "position_mae": metrics["position_mae"],
        "position_bias": metrics["position_bias"],
        "by_source": metrics["by_source"],
        "baseline": baseline_name,
        "delta_vs_baseline": delta,
    }

    path = _summary_path(experiment_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(summary, fh, indent=2)
    return path


def _compute_delta(
    baseline_summary: Dict,
    experiment_metrics: Dict,
    is_gate: bool,
) -> Dict:
    """Compute per-position MAE deltas between a baseline and new experiment.

    Negative delta means improvement (lower MAE). Ship verdict is positive
    when delta <= -SHIP_GATE_MIN_MAE_IMPROVEMENT and bias within bounds.

    Args:
        baseline_summary: Previously saved summary dict for the baseline.
        experiment_metrics: Metrics from the current experiment run.
        is_gate: Whether this is a sealed gate evaluation.

    Returns:
        Dict mapping position to {baseline_mae, experiment_mae, delta, ship}.
    """
    baseline_pos_mae = baseline_summary.get("position_mae", {})
    experiment_pos_mae = experiment_metrics.get("position_mae", {})
    experiment_pos_bias = experiment_metrics.get("position_bias", {})

    max_bias = SHIP_GATE_MAX_BIAS_GATE if is_gate else SHIP_GATE_MAX_BIAS_ITER
    delta: Dict[str, Dict] = {}

    all_positions = sorted(
        set(baseline_pos_mae.keys()) | set(experiment_pos_mae.keys())
    )
    for pos in all_positions:
        b_mae = baseline_pos_mae.get(pos)
        e_mae = experiment_pos_mae.get(pos)
        e_bias = experiment_pos_bias.get(pos)

        if b_mae is None or e_mae is None:
            delta[pos] = {
                "baseline_mae": b_mae,
                "experiment_mae": e_mae,
                "delta": None,
                "ship": False,
                "reason": "missing data",
            }
            continue

        diff = e_mae - b_mae
        bias_ok = e_bias is not None and abs(e_bias) <= max_bias
        improves_enough = diff <= -SHIP_GATE_MIN_MAE_IMPROVEMENT

        reasons = []
        if not improves_enough:
            reasons.append(
                f"delta {diff:+.3f} does not meet -{SHIP_GATE_MIN_MAE_IMPROVEMENT} threshold"
            )
        if not bias_ok:
            reasons.append(
                f"bias {e_bias:+.3f} exceeds +/-{max_bias} limit"
            )

        delta[pos] = {
            "baseline_mae": round(b_mae, 4),
            "experiment_mae": round(e_mae, 4),
            "delta": round(diff, 4),
            "ship": improves_enough and bias_ok,
            "reason": "; ".join(reasons) if reasons else "all gates pass",
        }

    return delta


def _print_comparison_table(
    exp1_name: str,
    exp1: Dict,
    exp2_name: str,
    exp2: Dict,
) -> None:
    """Print a side-by-side comparison table for two named experiments.

    Args:
        exp1_name: Display name for experiment 1 (baseline).
        exp1: Loaded summary dict for experiment 1.
        exp2_name: Display name for experiment 2 (candidate).
        exp2: Loaded summary dict for experiment 2.
    """
    positions = sorted(
        set(exp1.get("position_mae", {}).keys())
        | set(exp2.get("position_mae", {}).keys())
    )

    header = (
        f"\n{'=' * 75}\n"
        f"COMPARISON: {exp1_name} vs {exp2_name}\n"
        f"{'=' * 75}"
    )
    print(header)
    print(
        f"  {'Position':<10} {'Baseline MAE':>14} {'Experiment MAE':>16}"
        f" {'Delta':>10} {'Ship?':>8}"
    )
    print(f"  {'-' * 63}")

    for pos in positions:
        b_mae = exp1.get("position_mae", {}).get(pos)
        e_mae = exp2.get("position_mae", {}).get(pos)
        e_bias = exp2.get("position_bias", {}).get(pos)

        if b_mae is None or e_mae is None:
            print(f"  {pos:<10} {'N/A':>14} {'N/A':>16} {'N/A':>10} {'N/A':>8}")
            continue

        diff = e_mae - b_mae
        bias_ok = e_bias is not None and abs(e_bias) <= SHIP_GATE_MAX_BIAS_ITER
        ships = diff <= -SHIP_GATE_MIN_MAE_IMPROVEMENT and bias_ok
        ship_label = f"YES (>{SHIP_GATE_MIN_MAE_IMPROVEMENT})" if ships else f"NO (<{SHIP_GATE_MIN_MAE_IMPROVEMENT})"
        print(
            f"  {pos:<10} {b_mae:>14.2f} {e_mae:>16.2f} {diff:>+10.2f} {ship_label:>8}"
        )

    print()
    b_overall = exp1.get("overall_mae")
    e_overall = exp2.get("overall_mae")
    if b_overall is not None and e_overall is not None:
        overall_diff = e_overall - b_overall
        print(
            f"  {'Overall':<10} {b_overall:>14.2f} {e_overall:>16.2f} {overall_diff:>+10.2f}"
        )
    print(f"{'=' * 75}\n")


def _print_delta_report(
    experiment_name: str,
    baseline_name: str,
    delta: Dict,
    metrics: Dict,
) -> None:
    """Print delta table comparing experiment to baseline.

    Args:
        experiment_name: Name of the candidate experiment.
        baseline_name: Name of the baseline experiment.
        delta: Output from _compute_delta().
        metrics: Experiment metrics dict from _extract_metrics().
    """
    print(f"\n{'=' * 75}")
    print(f"DELTA REPORT: {experiment_name} vs baseline={baseline_name}")
    print(f"{'=' * 75}")
    print(
        f"  {'Position':<10} {'Baseline MAE':>14} {'Experiment MAE':>16}"
        f" {'Delta':>10} {'Ship?':>8}"
    )
    print(f"  {'-' * 63}")
    for pos, row in delta.items():
        b = row.get("baseline_mae")
        e = row.get("experiment_mae")
        d = row.get("delta")
        ships = row.get("ship", False)

        b_str = f"{b:.2f}" if b is not None else "N/A"
        e_str = f"{e:.2f}" if e is not None else "N/A"
        d_str = f"{d:+.2f}" if d is not None else "N/A"
        ship_str = "YES" if ships else "NO"
        print(
            f"  {pos:<10} {b_str:>14} {e_str:>16} {d_str:>10} {ship_str:>8}"
        )
    print()
    print(f"  Overall MAE:  {metrics['overall_mae']:.2f}")
    print(f"  Overall Bias: {metrics['overall_bias']:+.2f}")
    print(f"{'=' * 75}\n")


def run_experiment(
    experiment_name: str,
    seasons: List[int],
    weeks: Optional[List[int]],
    scoring_format: str,
    baseline_name: Optional[str],
    is_gate: bool,
    use_ml: bool,
    full_features: bool,
) -> Dict:
    """Execute a PFE run, save results, and print summary.

    Calls run_backtest() using the production-faithful feature assembly and
    heuristic path, then persists and returns the summary dict.

    Args:
        experiment_name: Short identifier saved to output/eval/<name>/.
        seasons: List of NFL seasons to evaluate.
        weeks: Optional explicit week list; defaults to weeks 3-18.
        scoring_format: Fantasy scoring format (e.g. "half_ppr").
        baseline_name: If provided, load this experiment's summary for delta.
        is_gate: If True, treat as sealed gate; enforces stricter bias limit
            and prints prominent warnings about single-use semantics.
        use_ml: Whether to activate the ML projection router.
        full_features: Whether to assemble the full feature vector for residual
            correction (requires local Silver data).

    Returns:
        The summary dict that was written to disk.
    """
    if is_gate:
        warnings.warn(
            "\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "  SEALED GATE RUN — this uses the holdout set.\n"
            "  Run this at most ONCE per candidate model.\n"
            "  Repeated gate runs invalidate the holdout.\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n",
            stacklevel=2,
        )
        print(
            "\nWARNING: --gate flag active. This is the SEALED HOLDOUT set.\n"
            "         Run at most once per candidate model.\n"
        )

    season_label = ",".join(str(s) for s in seasons)
    mode_label = "ML + Full Features" if (use_ml and full_features) else (
        "ML" if use_ml else "Heuristic"
    )
    print(f"\n{'=' * 60}")
    print(f"PFE Run: experiment={experiment_name}")
    print(f"Seasons: {season_label} | Mode: {mode_label} | Gate: {is_gate}")
    print(f"{'=' * 60}\n")

    results_df = run_backtest(
        seasons=seasons,
        weeks=weeks,
        scoring_format=scoring_format,
        use_ml=use_ml,
        apply_constraints=False,
        full_features=full_features,
    )

    if results_df.empty:
        print("ERROR: no backtest results produced — check data availability.")
        sys.exit(1)

    metrics = _extract_metrics(results_df)

    # Load baseline for delta computation
    baseline_summary = None
    delta = None
    if baseline_name:
        baseline_summary = _load_summary(baseline_name)
        if baseline_summary is None:
            print(
                f"WARNING: baseline '{baseline_name}' not found at "
                f"{_summary_path(baseline_name)}. Skipping delta."
            )
        else:
            delta = _compute_delta(baseline_summary, metrics, is_gate)
            _print_delta_report(experiment_name, baseline_name, delta, metrics)

    # Print overall metrics if no delta (delta already prints them)
    if delta is None:
        print(f"\nOverall MAE:  {metrics['overall_mae']:.2f}")
        print(f"Overall Bias: {metrics['overall_bias']:+.2f}")
        print("\nPer-Position MAE:")
        for pos, mae in metrics["position_mae"].items():
            bias = metrics["position_bias"].get(pos, float("nan"))
            print(f"  {pos}: {mae:.2f} (bias {bias:+.2f})")
        if metrics["by_source"]:
            print("\nBy Projection Source:")
            for src, mae in metrics["by_source"].items():
                print(f"  {src}: {mae:.2f}")

    summary_path = _save_summary(
        experiment_name,
        metrics,
        seasons,
        is_gate,
        baseline_name,
        delta,
    )
    print(f"\nSummary saved to: {summary_path}\n")

    return _load_summary(experiment_name)  # return what was written


def compare_experiments(exp1_name: str, exp2_name: str) -> None:
    """Load two saved summaries and print a side-by-side comparison table.

    Args:
        exp1_name: Name of experiment 1 (treated as the baseline).
        exp2_name: Name of experiment 2 (treated as the candidate).
    """
    exp1 = _load_summary(exp1_name)
    exp2 = _load_summary(exp2_name)

    missing = []
    if exp1 is None:
        missing.append(f"'{exp1_name}' ({_summary_path(exp1_name)})")
    if exp2 is None:
        missing.append(f"'{exp2_name}' ({_summary_path(exp2_name)})")
    if missing:
        print(f"ERROR: could not load summaries: {', '.join(missing)}")
        sys.exit(1)

    _print_comparison_table(exp1_name, exp1, exp2_name, exp2)


def parse_weeks(weeks_str: str) -> List[int]:
    """Parse '1-10' or '1,5,10' into a list of ints.

    Args:
        weeks_str: Week range string.

    Returns:
        List of week integers.
    """
    if "-" in weeks_str:
        start, end = weeks_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in weeks_str.split(",")]


def main() -> int:
    """CLI entry point for production_eval.py.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Production-Faithful Evaluation (PFE) tool"
    )
    parser.add_argument(
        "--experiment",
        type=str,
        help="Name for this run; results saved to output/eval/<name>/summary.json",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Name of a previous experiment to compare against",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default="2024",
        help="Comma-separated seasons (default: 2024 iteration set)",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default=None,
        help='Week range: "3-18" or "1,5,10" (default: 3-18)',
    )
    parser.add_argument(
        "--scoring",
        type=str,
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            "Sealed holdout mode. Prints warnings about single-use semantics. "
            "Use at most once per candidate model."
        ),
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("EXP1", "EXP2"),
        help="Compare two saved experiments side-by-side (no new backtest run)",
    )
    parser.add_argument(
        "--ml",
        action="store_true",
        default=True,
        help="Use ML projection router (default: True for PFE)",
    )
    parser.add_argument(
        "--no-ml",
        dest="ml",
        action="store_false",
        help="Disable ML router; use heuristic only",
    )
    parser.add_argument(
        "--full-features",
        action="store_true",
        default=True,
        help="Assemble full feature vector for residual correction (default: True)",
    )
    parser.add_argument(
        "--no-full-features",
        dest="full_features",
        action="store_false",
        help="Skip full feature assembly",
    )

    args = parser.parse_args()

    if args.compare:
        compare_experiments(args.compare[0], args.compare[1])
        return 0

    if not args.experiment:
        parser.error("--experiment is required unless using --compare")

    seasons = [int(s) for s in args.seasons.split(",")]
    weeks = parse_weeks(args.weeks) if args.weeks else None

    run_experiment(
        experiment_name=args.experiment,
        seasons=seasons,
        weeks=weeks,
        scoring_format=args.scoring,
        baseline_name=args.baseline,
        is_gate=args.gate,
        use_ml=args.ml,
        full_features=args.full_features,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
