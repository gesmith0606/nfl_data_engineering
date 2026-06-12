#!/usr/bin/env python3
"""
check_ml_output.py — Lightweight sanity gate for the weekly hybrid ML run.

Checks that the most-recently-written Gold weekly projection file for a given
season/week/scoring triple satisfies three invariants:

  1. The file exists and is non-empty (>= 50 rows for skill positions).
  2. At least one of the HYBRID_POSITIONS (WR, TE) appears in
     ``projection_source`` with value ``'hybrid'``.  If the residual models
     loaded successfully the TE/WR rows will all carry this tag; if they
     loaded but produced no rows it indicates a structural failure.
  3. No skill position has ALL projected_points equal to zero.  An all-zero
     position means the projection engine produced zero variance outputs —
     either a dead multiplier or missing Silver inputs that silently zeroed
     the heuristic.

Exit codes:
  0 — all checks passed; --ml output is safe to publish.
  1 — one or more checks failed; caller should re-run with heuristic-only.

Usage:
    python scripts/check_ml_output.py --season 2026 --week 5 --scoring half_ppr
"""

import argparse
import glob as globmod
import os
import sys
from typing import List, Tuple

import pandas as pd


# Positions that must appear as 'hybrid' in projection_source when the
# residual models are present.  Matches HYBRID_POSITIONS in ml_projection_router.
_HYBRID_POSITIONS = {"WR", "TE"}

# Minimum number of rows for the sanity check to be meaningful.
# Fewer than this usually means the Silver input was empty or nearly empty.
_MIN_ROWS = 50

# Skill positions checked for the all-zero invariant.
_SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")


def _find_latest_gold(season: int, week: int, scoring: str) -> str:
    """Return the path of the most-recently-written weekly Gold projection file.

    Looks in the canonical Gold path:
        data/gold/projections/season={season}/week={week}/

    Args:
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format (e.g. ``'half_ppr'``).

    Returns:
        Absolute path to the latest matching parquet file, or empty string
        when none is found.
    """
    pattern = os.path.join(
        GOLD_DIR,
        f"projections/season={season}/week={week}",
        f"projections_{scoring}_*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    return files[-1] if files else ""


def run_checks(
    season: int, week: int, scoring: str
) -> Tuple[List[str], List[str]]:
    """Run all sanity checks on the latest Gold weekly projection file.

    Args:
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format string.

    Returns:
        ``(failures, warnings)`` — lists of human-readable messages.
        An empty ``failures`` list means all checks passed.
    """
    failures: List[str] = []
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # Check 1: file exists
    # ------------------------------------------------------------------
    gold_path = _find_latest_gold(season, week, scoring)
    if not gold_path:
        failures.append(
            f"CHECK1 FAIL: no Gold weekly projection file found for "
            f"season={season} week={week} scoring={scoring} under {GOLD_DIR}"
        )
        return failures, warnings

    print(f"  Checking: {os.path.basename(gold_path)}")

    # ------------------------------------------------------------------
    # Check 2: non-trivial row count
    # ------------------------------------------------------------------
    try:
        df = pd.read_parquet(gold_path)
    except Exception as exc:
        failures.append(f"CHECK2 FAIL: cannot read {gold_path}: {exc}")
        return failures, warnings

    skill_df = df[df["position"].isin(_SKILL_POSITIONS)] if "position" in df.columns else df
    if len(skill_df) < _MIN_ROWS:
        failures.append(
            f"CHECK2 FAIL: only {len(skill_df)} skill-position rows "
            f"(expected >= {_MIN_ROWS}); Silver inputs may be empty"
        )

    # ------------------------------------------------------------------
    # Check 3: hybrid positions present when models are on-disk
    # ------------------------------------------------------------------
    if "projection_source" in df.columns:
        hybrid_rows = df[df["projection_source"] == "hybrid"]
        hybrid_positions_found = (
            set(hybrid_rows["position"].unique()) if not hybrid_rows.empty else set()
        )

        # Only flag when the residual model files actually exist — if the
        # runner never had them we'd expect all-heuristic output.
        residual_dir = os.path.join(PROJECT_ROOT, "models", "residual")
        missing_models = {
            pos
            for pos in _HYBRID_POSITIONS
            if not os.path.exists(
                os.path.join(residual_dir, f"{pos.lower()}_residual.joblib")
            )
        }
        expected_hybrid = _HYBRID_POSITIONS - missing_models

        if expected_hybrid:
            absent_hybrid = expected_hybrid - hybrid_positions_found
            if absent_hybrid:
                failures.append(
                    f"CHECK3 FAIL: residual model files exist for "
                    f"{sorted(expected_hybrid)} but projection_source='hybrid' "
                    f"is absent for positions: {sorted(absent_hybrid)}. "
                    f"Residual correction was silently skipped."
                )
            else:
                hybrid_counts = (
                    hybrid_rows.groupby("position").size().to_dict()
                )
                print(
                    f"  [PASS] hybrid rows by position: "
                    + ", ".join(f"{p}={n}" for p, n in sorted(hybrid_counts.items()))
                )
    else:
        warnings.append(
            "CHECK3 WARN: 'projection_source' column absent from Gold file; "
            "cannot verify hybrid routing"
        )

    # ------------------------------------------------------------------
    # Check 4: no all-zero skill position
    # ------------------------------------------------------------------
    if "projected_points" in df.columns and "position" in df.columns:
        for pos in _SKILL_POSITIONS:
            pos_df = df[(df["position"] == pos) & (~df.get("is_bye_week", pd.Series(False)).fillna(False))]
            if pos_df.empty:
                continue
            # Allow zeros only if every player is on bye or injured-out
            non_bye = pos_df[~pos_df.get("is_bye_week", pd.Series(False)).fillna(False)]
            if non_bye.empty:
                continue
            all_zero = (non_bye["projected_points"].fillna(0) == 0).all()
            if all_zero:
                failures.append(
                    f"CHECK4 FAIL: ALL {len(non_bye)} {pos} non-bye rows have "
                    f"projected_points == 0; dead multiplier or missing Silver "
                    f"inputs likely"
                )
            else:
                mean_pts = non_bye["projected_points"].mean()
                print(f"  [PASS] {pos}: mean={mean_pts:.2f}, n={len(non_bye)} non-bye rows")

    return failures, warnings


def main() -> int:
    """Entry point for the ML output sanity gate.

    Returns:
        0 on pass, 1 on any failure.
    """
    parser = argparse.ArgumentParser(
        description="Sanity-check the hybrid ML Gold output before publishing."
    )
    parser.add_argument("--season", type=int, required=True, help="NFL season year")
    parser.add_argument("--week", type=int, required=True, help="NFL week number")
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    args = parser.parse_args()

    print(
        f"\nML output sanity check — season={args.season} "
        f"week={args.week} scoring={args.scoring}"
    )
    print("-" * 60)

    failures, warnings = run_checks(args.season, args.week, args.scoring)

    for w in warnings:
        print(f"  [WARN] {w}")

    if failures:
        print()
        for f in failures:
            print(f"  [FAIL] {f}")
        print(f"\nRESULT: FAIL ({len(failures)} check(s) failed)")
        return 1

    print(f"\nRESULT: PASS — ML output is valid for season={args.season} week={args.week}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
