#!/usr/bin/env python3
"""Swap-and-evaluate: test a candidate model without clobbering production.

Atomically swaps a candidate residual model into the production model path,
runs a Production-Faithful Evaluation via production_eval.py, and then
ALWAYS restores the original model — even on error or keyboard interrupt.

Usage:
    # Test a WR candidate model
    python scripts/swap_and_eval.py \\
        --position wr \\
        --candidate models/residual/_sandbox/wr_candidate.joblib \\
        --experiment wr_ridge_test

    # Test with imputer and meta
    python scripts/swap_and_eval.py \\
        --position wr \\
        --candidate models/residual/_sandbox/wr_candidate.joblib \\
        --imputer models/residual/_sandbox/wr_candidate_imputer.joblib \\
        --meta models/residual/_sandbox/wr_candidate_meta.json \\
        --experiment wr_ridge_test
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESIDUAL_DIR = os.path.join(PROJECT_ROOT, "models", "residual")
BACKUP_DIR = os.path.join(RESIDUAL_DIR, "_backup")
SANDBOX_DIR = os.path.join(RESIDUAL_DIR, "_sandbox")

# Production model file name patterns per position
_MODEL_FILENAMES = {
    "qb": "qb_residual.joblib",
    "rb": "rb_residual.joblib",
    "wr": "wr_residual.joblib",
    "te": "te_residual.joblib",
}

_IMPUTER_FILENAMES = {
    "qb": "qb_residual_imputer.joblib",
    "rb": "rb_residual_imputer.joblib",
    "wr": "wr_residual_imputer.joblib",
    "te": "te_residual_imputer.joblib",
}

_META_FILENAMES = {
    "qb": "qb_residual_meta.json",
    "rb": "rb_residual_meta.json",
    "wr": "wr_residual_meta.json",
    "te": "te_residual_meta.json",
}


def _production_path(position: str, file_type: str = "model") -> str:
    """Return the absolute path to a production model file.

    Args:
        position: Position string ('qb', 'rb', 'wr', 'te').
        file_type: One of 'model', 'imputer', or 'meta'.

    Returns:
        Absolute path to the production file.

    Raises:
        ValueError: If position or file_type is invalid.
    """
    position = position.lower()
    mapping = {
        "model": _MODEL_FILENAMES,
        "imputer": _IMPUTER_FILENAMES,
        "meta": _META_FILENAMES,
    }
    if file_type not in mapping:
        raise ValueError(f"Unknown file_type '{file_type}'. Use model/imputer/meta.")
    if position not in mapping[file_type]:
        raise ValueError(
            f"Unknown position '{position}'. Use one of: {list(mapping[file_type])}"
        )
    return os.path.join(RESIDUAL_DIR, mapping[file_type][position])


def _backup_tag() -> str:
    """Generate a timestamped backup tag.

    Returns:
        String like '20260410_1337'.
    """
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _backup_production_file(
    position: str,
    file_type: str,
    backup_subdir: str,
) -> Optional[str]:
    """Copy one production file to the backup directory.

    Args:
        position: Position string.
        file_type: One of 'model', 'imputer', or 'meta'.
        backup_subdir: Subdirectory under BACKUP_DIR to copy into.

    Returns:
        Path of the backup copy, or None if the source does not exist.
    """
    src = _production_path(position, file_type)
    if not os.path.exists(src):
        logger.debug("Production %s file not found, skipping backup: %s", file_type, src)
        return None

    dest_dir = os.path.join(BACKUP_DIR, backup_subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    shutil.copy2(src, dest)
    logger.debug("Backed up %s → %s", src, dest)
    return dest


def _swap_file(candidate_path: str, production_path: str) -> None:
    """Copy a candidate file into the production path.

    Args:
        candidate_path: Absolute path to the candidate file.
        production_path: Absolute path to the production destination.

    Raises:
        FileNotFoundError: If the candidate file does not exist.
    """
    if not os.path.exists(candidate_path):
        raise FileNotFoundError(
            f"Candidate file not found: {candidate_path}"
        )
    shutil.copy2(candidate_path, production_path)
    logger.info("Swapped %s → %s", candidate_path, production_path)


def _restore_file(backup_path: Optional[str], production_path: str) -> None:
    """Restore a production file from backup.

    If no backup exists (i.e., there was no original), the production file
    is removed to leave the system in the state it was before the swap.

    Args:
        backup_path: Path to the backup copy, or None if there was no original.
        production_path: Absolute path to the production destination to restore.
    """
    if backup_path and os.path.exists(backup_path):
        shutil.copy2(backup_path, production_path)
        logger.info("Restored %s → %s", backup_path, production_path)
    elif os.path.exists(production_path):
        os.remove(production_path)
        logger.info(
            "No backup to restore — removed temporary production file: %s",
            production_path,
        )


def _run_production_eval(
    experiment_name: str,
    seasons: List[int],
    weeks: Optional[str],
    scoring_format: str,
    baseline_name: Optional[str],
    is_gate: bool,
) -> int:
    """Invoke production_eval.py as a subprocess.

    Using a subprocess rather than a direct function call ensures that the
    model files loaded in production_eval.py reflect the swapped state on disk.
    joblib caches would otherwise serve a stale module-level object.

    Args:
        experiment_name: Name for the experiment.
        seasons: List of seasons to evaluate.
        weeks: Week range string (e.g. '3-18'), or None.
        scoring_format: Scoring format string.
        baseline_name: Baseline experiment name, or None.
        is_gate: Whether to pass --gate flag.

    Returns:
        Return code from the subprocess (0 = success).
    """
    script_path = os.path.join(os.path.dirname(__file__), "production_eval.py")
    cmd = [
        sys.executable,
        script_path,
        "--experiment", experiment_name,
        "--seasons", ",".join(str(s) for s in seasons),
        "--scoring", scoring_format,
    ]

    if weeks:
        cmd += ["--weeks", weeks]
    if baseline_name:
        cmd += ["--baseline", baseline_name]
    if is_gate:
        cmd.append("--gate")

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def _load_eval_summary(experiment_name: str) -> Optional[Dict]:
    """Load a saved PFE summary for reporting.

    Args:
        experiment_name: Experiment identifier.

    Returns:
        Parsed summary dict or None if not found.
    """
    eval_dir = os.path.join(PROJECT_ROOT, "output", "eval")
    path = os.path.join(eval_dir, experiment_name, "summary.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as fh:
        return json.load(fh)


def swap_and_eval(
    position: str,
    candidate_model: str,
    experiment_name: str,
    candidate_imputer: Optional[str] = None,
    candidate_meta: Optional[str] = None,
    seasons: Optional[List[int]] = None,
    weeks: Optional[str] = None,
    scoring_format: str = "half_ppr",
    baseline_name: Optional[str] = None,
    is_gate: bool = False,
) -> int:
    """Atomically swap a candidate residual model, run PFE, then restore.

    The original production model is ALWAYS restored in a try/finally block,
    guaranteeing that even an exception, keyboard interrupt, or subprocess
    failure leaves the system in its original state.

    Args:
        position: Which position's model to swap ('qb', 'rb', 'wr', 'te').
        candidate_model: Path to the candidate .joblib model file.
        experiment_name: Name for the PFE run; results saved to
            output/eval/<name>/summary.json.
        candidate_imputer: Optional path to companion imputer .joblib.
        candidate_meta: Optional path to companion meta .json.
        seasons: Seasons to evaluate (default: [2024]).
        weeks: Week range string for PFE (default: 3-18).
        scoring_format: Fantasy scoring format.
        baseline_name: Name of saved baseline experiment for delta comparison.
        is_gate: If True, passes --gate to production_eval.py.

    Returns:
        Return code from production_eval.py (0 = success).

    Raises:
        FileNotFoundError: If the candidate model file does not exist.
        ValueError: If position is invalid.
    """
    if seasons is None:
        seasons = [2024]

    position = position.lower()
    if position not in _MODEL_FILENAMES:
        raise ValueError(
            f"Unknown position '{position}'. Use one of: {sorted(_MODEL_FILENAMES)}"
        )

    candidate_model = os.path.abspath(candidate_model)
    if not os.path.exists(candidate_model):
        raise FileNotFoundError(f"Candidate model not found: {candidate_model}")

    tag = _backup_tag()
    backup_subdir = f"{position}_{experiment_name}_{tag}"

    # Collect which files will be swapped
    swap_plan: List[Tuple[Optional[str], str, str]] = []  # (candidate, production, file_type)

    prod_model = _production_path(position, "model")
    swap_plan.append((candidate_model, prod_model, "model"))

    if candidate_imputer:
        candidate_imputer = os.path.abspath(candidate_imputer)
        prod_imputer = _production_path(position, "imputer")
        swap_plan.append((candidate_imputer, prod_imputer, "imputer"))

    if candidate_meta:
        candidate_meta = os.path.abspath(candidate_meta)
        prod_meta = _production_path(position, "meta")
        swap_plan.append((candidate_meta, prod_meta, "meta"))

    # Backup all production files that will be swapped
    backups: Dict[str, Optional[str]] = {}  # production_path → backup_path

    print(f"\n{'=' * 60}")
    print(f"SWAP-AND-EVAL: position={position.upper()}, experiment={experiment_name}")
    print(f"Backup tag: {backup_subdir}")
    print(f"{'=' * 60}\n")

    for _candidate, prod_path, file_type in swap_plan:
        backup_path = _backup_production_file(position, file_type, backup_subdir)
        backups[prod_path] = backup_path
        if backup_path:
            print(f"  Backed up {file_type}: {prod_path}")
        else:
            print(f"  No existing {file_type} to back up")

    eval_returncode = 1
    try:
        # Perform all swaps
        for candidate_path, prod_path, file_type in swap_plan:
            _swap_file(candidate_path, prod_path)
            print(f"  Swapped {file_type}: {os.path.basename(candidate_path)} → {prod_path}")

        print(f"\n  Running PFE for experiment '{experiment_name}'...\n")
        eval_returncode = _run_production_eval(
            experiment_name=experiment_name,
            seasons=seasons,
            weeks=weeks,
            scoring_format=scoring_format,
            baseline_name=baseline_name,
            is_gate=is_gate,
        )

    finally:
        # ALWAYS restore originals
        print(f"\n  Restoring original production files...")
        for prod_path, backup_path in backups.items():
            _restore_file(backup_path, prod_path)
            status = "restored" if (backup_path and os.path.exists(backup_path)) else "removed (no original)"
            print(f"  {os.path.basename(prod_path)}: {status}")
        print("\n  All production files restored.\n")

    # Print summary of results
    summary = _load_eval_summary(experiment_name)
    if summary:
        print(f"{'=' * 60}")
        print(f"PFE RESULTS: {experiment_name}")
        print(f"{'=' * 60}")
        print(f"  Overall MAE:  {summary.get('overall_mae', 'N/A'):.2f}")
        print(f"  Overall Bias: {summary.get('overall_bias', 0):+.2f}")

        delta = summary.get("delta_vs_baseline")
        if delta:
            print(f"\n  Delta vs baseline '{summary.get('baseline')}':")
            print(
                f"  {'Position':<10} {'Baseline':>10} {'Candidate':>10}"
                f" {'Delta':>8} {'Ship?':>8}"
            )
            print(f"  {'-' * 50}")
            for pos, row in delta.items():
                b = row.get("baseline_mae")
                e = row.get("experiment_mae")
                d = row.get("delta")
                ships = row.get("ship", False)
                b_s = f"{b:.2f}" if b is not None else "N/A"
                e_s = f"{e:.2f}" if e is not None else "N/A"
                d_s = f"{d:+.2f}" if d is not None else "N/A"
                print(
                    f"  {pos:<10} {b_s:>10} {e_s:>10} {d_s:>8} {'YES' if ships else 'NO':>8}"
                )
        print(f"{'=' * 60}\n")

    if eval_returncode != 0:
        print(f"WARNING: production_eval.py exited with code {eval_returncode}")

    return eval_returncode


def main() -> int:
    """CLI entry point for swap_and_eval.py.

    Returns:
        Exit code (0 = success).
    """
    parser = argparse.ArgumentParser(
        description="Swap a candidate residual model, run PFE, restore original"
    )
    parser.add_argument(
        "--position",
        required=True,
        choices=["qb", "rb", "wr", "te"],
        help="Which position's model to swap",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        help="Path to candidate model (.joblib)",
    )
    parser.add_argument(
        "--imputer",
        default=None,
        help="Optional: path to candidate imputer (.joblib)",
    )
    parser.add_argument(
        "--meta",
        default=None,
        help="Optional: path to candidate meta (.json)",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        help="Name for the PFE run; output saved to output/eval/<name>/",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default="2024",
        help="Comma-separated seasons (default: 2024)",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default=None,
        help='Week range for PFE: "3-18" or "1,5,10" (default: 3-18)',
    )
    parser.add_argument(
        "--scoring",
        type=str,
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Name of a previous experiment to compare against",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Sealed holdout mode — run at most once per candidate",
    )
    args = parser.parse_args()

    seasons = [int(s) for s in args.seasons.split(",")]

    return swap_and_eval(
        position=args.position,
        candidate_model=args.candidate,
        experiment_name=args.experiment,
        candidate_imputer=args.imputer,
        candidate_meta=args.meta,
        seasons=seasons,
        weeks=args.weeks,
        scoring_format=args.scoring,
        baseline_name=args.baseline,
        is_gate=args.gate,
    )


if __name__ == "__main__":
    sys.exit(main())
