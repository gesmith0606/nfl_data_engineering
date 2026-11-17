#!/usr/bin/env python3
"""
check_ml_output.py — Lightweight sanity gate for the weekly hybrid ML run.

Checks that the most-recently-written Gold weekly projection file for a given
season/week/scoring triple satisfies four invariants:

  1. The file exists and is readable.
  2. It has >= 50 skill-position rows (fewer usually means empty Silver input).
  3. Every routed position (QB, RB, WR, TE - HYBRID_POSITIONS in the router)
     that has a residual model on disk was actually corrected, or says why not.
     The board carries ``residual_correction_applied`` (per row) and
     ``residual_skip_reason``; ``projection_source == 'hybrid'`` is only
     allowed on corrected rows. Rows skipped on purpose by the serve-time
     feature-coverage guard (``coverage_guard``) are a WARNING (the guard has
     already printed its own ``::warning::``); rows skipped for any other
     reason (``no_model``, ``no_feature_rows``, blank) are a FAILURE when they
     exceed 5% of a position (the residual silently failed), and so is a
     ``hybrid`` label on an uncorrected row. ``no_features`` (a player with no
     populated feature, e.g. a fresh rookie) is tolerated up to 40% of the
     startable (>= 5 pt) rows. Boards
     written before the applied flag existed fall back to the legacy
     ``projection_source == 'hybrid'`` share check for WR/TE.
     ``consensus_fallback`` rows (players the engine had no basis for) are
     excluded from every share.
  4. No skill position has ALL projected_points equal to zero.  An all-zero
     position means the projection engine produced zero variance outputs -
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


# Positions routed through a residual model when its files are present.
# Matches HYBRID_POSITIONS in ml_projection_router (QB/RB joined WR/TE in v4.4).
_HYBRID_POSITIONS = {"QB", "RB", "WR", "TE"}

# Legacy check (boards without the applied flag) still only covers these two.
_LEGACY_HYBRID_POSITIONS = {"WR", "TE"}

# Unexplained non-corrections above this share of a position fail the check.
_MAX_UNEXPLAINED_SHARE = 0.05
# A player with no populated feature is legitimately uncorrected (fresh
# rookies, spot starters); only a position-wide collapse is a failure.
_MAX_NO_FEATURES_SHARE = 0.40

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
    # Check 3: every routed position was corrected, or says why not
    # ------------------------------------------------------------------
    residual_dir = os.path.join(PROJECT_ROOT, "models", "residual")
    expected = {
        pos
        for pos in _HYBRID_POSITIONS
        if os.path.exists(os.path.join(residual_dir, f"{pos.lower()}_residual.joblib"))
    }
    bye_mask = (
        df["is_bye_week"].fillna(False).astype(bool)
        if "is_bye_week" in df.columns
        else pd.Series(False, index=df.index)
    )
    src = df["projection_source"] if "projection_source" in df.columns else None
    fallback_mask = (
        src == "consensus_fallback" if src is not None else pd.Series(False, index=df.index)
    )

    if "residual_correction_applied" in df.columns and "position" in df.columns:
        applied = df["residual_correction_applied"].fillna(False).astype(bool)
        reason = (
            df["residual_skip_reason"].fillna("")
            if "residual_skip_reason" in df.columns
            else pd.Series("", index=df.index)
        )
        for pos in sorted(expected):
            rows = (df["position"] == pos) & ~bye_mask & ~fallback_mask
            n = int(rows.sum())
            if n == 0:
                continue
            n_app = int((rows & applied).sum())
            # truthful label: 'hybrid' only on a corrected row
            if src is not None:
                bad = int((rows & (src == "hybrid") & ~applied).sum())
                if bad:
                    failures.append(
                        f"CHECK3 FAIL: {bad} {pos} row(s) are labelled "
                        f"projection_source='hybrid' but residual_correction_applied "
                        f"is False - the label is not telling the truth."
                    )
            skipped = rows & ~applied
            parts = []
            for why, cnt in reason[skipped].replace("", "(blank)").value_counts().items():
                parts.append(f"{why}={cnt}")
                share = cnt / n
                if why == "coverage_guard":
                    warnings.append(
                        f"CHECK3 WARN: {pos} residual skipped by the feature-coverage "
                        f"guard for {cnt}/{n} rows - board is heuristic-only for {pos}"
                    )
                elif why == "no_features":
                    # Judge on startable rows: deep-bench players (projected < 5)
                    # routinely have no feature row (43% of RB rows on 2026
                    # boards) while only 7-15% of startable rows do.
                    startable = rows & (df["projected_points"] >= 5)
                    if int(startable.sum()) >= 5:
                        share = float((startable & skipped & (reason == "no_features")).sum() / startable.sum())
                    if share > _MAX_NO_FEATURES_SHARE:
                        failures.append(
                            f"CHECK3 FAIL: {share:.0%} of non-bye {pos} rows have no "
                            f"populated model feature (n={n}); feature assembly collapsed"
                        )
                elif share > _MAX_UNEXPLAINED_SHARE:
                    failures.append(
                        f"CHECK3 FAIL: {share:.0%} of non-bye {pos} rows were not "
                        f"residual-corrected for reason {why!r} (n={n}); the residual "
                        f"silently failed although models/residual/{pos.lower()}_residual.joblib exists"
                    )
            print(
                f"  [{'PASS' if not skipped.any() else 'INFO'}] {pos}: residual applied "
                f"{n_app}/{n}" + (f" (not applied: {', '.join(parts)})" if parts else "")
            )
    elif src is not None:
        warnings.append(
            "CHECK3 WARN: 'residual_correction_applied' absent from Gold file "
            "(board written by older code); falling back to the legacy "
            "projection_source='hybrid' share check for WR/TE"
        )
        hybrid_rows = df[src == "hybrid"]
        found = set(hybrid_rows["position"].unique()) if not hybrid_rows.empty else set()
        legacy = expected & _LEGACY_HYBRID_POSITIONS
        absent = legacy - found
        if absent:
            failures.append(
                f"CHECK3 FAIL: residual model files exist for {sorted(legacy)} but "
                f"projection_source='hybrid' is absent for positions: {sorted(absent)}. "
                f"Residual correction was silently skipped."
            )
        else:
            for pos in sorted(legacy):
                pos_rows = df[(df["position"] == pos) & ~bye_mask & ~fallback_mask]
                if pos_rows.empty:
                    continue
                frac = float((pos_rows["projection_source"] == "hybrid").mean())
                if frac < 0.95:
                    failures.append(
                        f"CHECK3 FAIL: only {frac:.0%} of non-bye {pos} rows are "
                        f"projection_source='hybrid' (n={len(pos_rows)}); expected "
                        f"~100% when the residual model is present - routing partially failed."
                    )
    else:
        warnings.append(
            "CHECK3 WARN: neither 'residual_correction_applied' nor "
            "'projection_source' present in Gold file; cannot verify residual routing"
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
