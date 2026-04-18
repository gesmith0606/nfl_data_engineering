#!/usr/bin/env python3
"""
Backtest Event Adjustments vs Baseline Heuristic
=================================================

Runs the projection pipeline twice per (season, week):

    baseline   — heuristic projections only (no event adjustments)
    treatment  — heuristic projections + apply_event_adjustments()

Then reports per-position MAE/RMSE/bias and emits a SHIP / SKIP verdict.

Per Phase 61 D-03 the ship gate is strict: events may only ship to
production default-on if treatment MAE is within +0.05 of baseline MAE
for every position across the backtest window.  Phase 54 taught us that
walk-forward CV wins do not reliably translate to production — so this
backtest uses the full production code path end-to-end.

Usage
-----

    source venv/bin/activate
    python scripts/backtest_event_adjustments.py \
        --seasons 2022 2023 2024 --scoring half_ppr

    python scripts/backtest_event_adjustments.py \
        --seasons 2024 --positions qb rb wr te

Output
------

    * Per-position metrics to stdout
    * Markdown report to `.planning/phases/61-news-sentiment-live/61-03-backtest.md`
    * Final verdict line ``verdict=SHIP`` or ``verdict=SKIP`` (machine-parseable)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Shared imports — reuse patterns from backtest_projections.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from projection_engine import (  # noqa: E402
    apply_event_adjustments,
    generate_weekly_projections,
    load_latest_sentiment,
)
from backtest_projections import (  # noqa: E402
    _compute_week_implied_totals,
    _load_local_parquet,
    _prepare_weekly,
    build_silver_features,
    compute_actuals,
)
from player_analytics import compute_opponent_rankings  # noqa: E402
from nfl_data_integration import NFLDataFetcher  # noqa: E402
from scoring_calculator import list_scoring_formats  # noqa: E402


logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRONZE_DIR = PROJECT_ROOT / "data" / "bronze"
BACKTEST_MD = (
    PROJECT_ROOT
    / ".planning"
    / "phases"
    / "61-news-sentiment-live"
    / "61-03-backtest.md"
)

# Production baseline MAE at the time of writing this phase — see
# MEMORY.md / PROJECT.md.  The backtest summary makes this explicit.
_PRODUCTION_BASELINE_MAE: float = 5.05

# Strict ship slack per D-03: treatment MAE may exceed baseline by at most
# this many fantasy points on any one position before we SKIP.
_MAE_SLACK: float = 0.05


@dataclass(frozen=True)
class _BacktestRow:
    """A single (season, week, position) result row."""

    season: int
    week: int
    position: str
    n_players: int
    baseline_mae: float
    treatment_mae: float
    delta: float
    verdict: str


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------


def _project_week(
    weekly_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str,
) -> Optional[pd.DataFrame]:
    """Generate heuristic projections for a given (season, week).

    Returns ``None`` if features are unavailable.
    """
    silver_df = build_silver_features(weekly_df, season, up_to_week=week)
    if silver_df.empty:
        return None

    try:
        opp_rankings = compute_opponent_rankings(weekly_df, schedules_df)
    except Exception:  # pragma: no cover — defensive
        opp_rankings = pd.DataFrame()

    implied_totals = None
    sched_for_week = None
    if not schedules_df.empty:
        week_sched = (
            schedules_df[
                schedules_df.get("season", pd.Series(dtype=int)).eq(season)
            ]
            if "season" in schedules_df.columns
            else schedules_df
        )
        implied_totals = _compute_week_implied_totals(week_sched, week)
        if implied_totals:
            sched_for_week = week_sched

    try:
        return generate_weekly_projections(
            silver_df,
            opp_rankings,
            season=season,
            week=week,
            scoring_format=scoring_format,
            schedules_df=(
                sched_for_week
                if sched_for_week is not None
                else (schedules_df if not schedules_df.empty else None)
            ),
            implied_totals=implied_totals,
            apply_constraints=False,
        )
    except Exception as exc:
        logger.debug("projection failure %s W%s: %s", season, week, exc)
        return None


def _merge_actuals(
    projections: pd.DataFrame,
    actuals: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Inner-join projections → actuals and attach error columns."""
    merged = projections.merge(
        actuals[["player_name", "actual_points"]],
        on="player_name",
        how="inner",
    )
    if merged.empty:
        return merged
    merged = merged.copy()
    merged["season"] = season
    merged["week"] = week
    merged["error"] = merged["projected_points"] - merged["actual_points"]
    merged["abs_error"] = merged["error"].abs()
    return merged


def _metrics_by_position(
    baseline: pd.DataFrame,
    treatment: pd.DataFrame,
    positions: List[str],
) -> List[Tuple[str, int, float, float, float]]:
    """Return (position, n_players, baseline_mae, treatment_mae, delta) rows."""
    rows: List[Tuple[str, int, float, float, float]] = []
    for pos in positions:
        pos_u = pos.upper()
        b = baseline[baseline["position"] == pos_u]
        t = treatment[treatment["position"] == pos_u]
        if b.empty or t.empty:
            continue
        b_mae = float(b["abs_error"].mean())
        t_mae = float(t["abs_error"].mean())
        rows.append((pos_u, len(b), b_mae, t_mae, t_mae - b_mae))
    return rows


def run_backtest(
    seasons: List[int],
    scoring_format: str,
    positions: List[str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (baseline_df, treatment_df) across all (season, week) pairs.

    Both frames share ``season``, ``week``, ``position``, ``player_name``,
    ``projected_points``, ``actual_points``, ``error``, ``abs_error`` columns.
    """
    fetcher = NFLDataFetcher()
    all_seasons = list(set(seasons + [s - 1 for s in seasons]))

    print(f"Loading weekly data for seasons: {all_seasons}")
    dfs = []
    for s in sorted(all_seasons):
        local = _load_local_parquet(
            str(BRONZE_DIR), f"players/weekly/season={s}/*.parquet"
        )
        if not local.empty:
            dfs.append(local)
    if dfs:
        weekly_df = pd.concat(dfs, ignore_index=True)
        print(f"Loaded {len(weekly_df):,} weekly rows from local Bronze")
    else:
        weekly_df = fetcher.fetch_player_weekly(all_seasons)
        print(f"Loaded {len(weekly_df):,} weekly rows from nfl-data-py")

    weekly_df = _prepare_weekly(weekly_df)

    sched_dfs = []
    for s in sorted(all_seasons):
        local = _load_local_parquet(
            str(BRONZE_DIR), f"games/season={s}/*.parquet"
        )
        if local.empty:
            local = _load_local_parquet(
                str(BRONZE_DIR), f"schedules/season={s}/*.parquet"
            )
        if not local.empty:
            if "season" not in local.columns:
                local["season"] = s
            sched_dfs.append(local)
    schedules_df = (
        pd.concat(sched_dfs, ignore_index=True) if sched_dfs else pd.DataFrame()
    )
    if not schedules_df.empty:
        print(f"Loaded {len(schedules_df):,} schedule rows")

    positions_upper = [p.upper() for p in positions]

    baseline_rows: List[pd.DataFrame] = []
    treatment_rows: List[pd.DataFrame] = []
    total_weeks = 0
    events_available_weeks = 0

    for season in seasons:
        for week in range(3, 19):
            print(
                f"  Backtesting {season} Week {week}...", end=" ", flush=True
            )
            projections = _project_week(
                weekly_df, schedules_df, season, week, scoring_format
            )
            if projections is None or projections.empty:
                print("SKIP (no projections)")
                continue

            projections = projections[
                projections["position"].isin(positions_upper)
            ]
            if projections.empty:
                print("SKIP (no positions)")
                continue

            actuals = compute_actuals(weekly_df, season, week, scoring_format)
            if actuals.empty:
                print("SKIP (no actuals)")
                continue

            baseline = _merge_actuals(projections, actuals, season, week)
            if baseline.empty:
                print("SKIP (no merges)")
                continue

            # Treatment: apply events on the same projection set
            events_df = load_latest_sentiment(season, week)
            if not events_df.empty:
                events_available_weeks += 1
            treated_proj = apply_event_adjustments(projections, events_df)
            treatment = _merge_actuals(treated_proj, actuals, season, week)

            baseline_rows.append(baseline)
            treatment_rows.append(treatment)
            total_weeks += 1
            print(
                f"OK (events={'yes' if not events_df.empty else 'none'}, "
                f"n={len(baseline)})"
            )

    if not baseline_rows:
        return pd.DataFrame(), pd.DataFrame()

    baseline_df = pd.concat(baseline_rows, ignore_index=True)
    treatment_df = pd.concat(treatment_rows, ignore_index=True)

    print(
        f"\nBacktest complete: {total_weeks} weeks processed "
        f"({events_available_weeks} had Gold events data)"
    )
    return baseline_df, treatment_df


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _compute_per_week_rows(
    baseline_df: pd.DataFrame,
    treatment_df: pd.DataFrame,
    positions: List[str],
) -> List[_BacktestRow]:
    """Per-(season, week, position) breakdown for the markdown table."""
    out: List[_BacktestRow] = []
    key = ["season", "week", "position"]
    grouped_baseline = baseline_df.groupby(key)
    grouped_treatment = treatment_df.groupby(key)

    pos_upper = {p.upper() for p in positions}
    seen = sorted(set(grouped_baseline.groups) & set(grouped_treatment.groups))
    for season, week, pos in seen:
        if pos not in pos_upper:
            continue
        b = grouped_baseline.get_group((season, week, pos))
        t = grouped_treatment.get_group((season, week, pos))
        b_mae = float(b["abs_error"].mean())
        t_mae = float(t["abs_error"].mean())
        delta = t_mae - b_mae
        verdict = "PASS" if delta <= _MAE_SLACK else "REGRESS"
        out.append(
            _BacktestRow(
                season=int(season),
                week=int(week),
                position=str(pos),
                n_players=len(b),
                baseline_mae=round(b_mae, 3),
                treatment_mae=round(t_mae, 3),
                delta=round(delta, 3),
                verdict=verdict,
            )
        )
    return out


def _overall_verdict(
    baseline_df: pd.DataFrame,
    treatment_df: pd.DataFrame,
    positions: List[str],
) -> Tuple[str, List[Tuple[str, float, float, float]]]:
    """Compute the SHIP / SKIP verdict and per-position aggregates."""
    per_pos = _metrics_by_position(baseline_df, treatment_df, positions)
    verdict = "SHIP"
    for _, _, b_mae, t_mae, delta in per_pos:
        if delta > _MAE_SLACK:
            verdict = "SKIP"
            break
    return verdict, [(p, b, t, d) for p, _, b, t, d in per_pos]


def _write_markdown(
    per_week_rows: List[_BacktestRow],
    per_pos: List[Tuple[str, float, float, float]],
    verdict: str,
    seasons: List[int],
    scoring_format: str,
    events_weeks: int,
    total_weeks: int,
) -> None:
    """Persist a machine- and human-readable report to 61-03-backtest.md."""
    BACKTEST_MD.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: List[str] = []
    lines.append(f"# Phase 61-03 Event Adjustments Backtest\n")
    lines.append(
        f"Generated: {ts}  |  Seasons: {seasons}  |  Scoring: "
        f"{scoring_format}  |  Weeks with events data: "
        f"{events_weeks}/{total_weeks}\n"
    )
    lines.append(
        "Production baseline at time of Phase 61 planning: "
        f"**{_PRODUCTION_BASELINE_MAE:.2f} MAE** "
        "(2022-2024 half_ppr, per MEMORY.md).\n"
    )
    lines.append(
        "Ship rule (D-03): treatment MAE may not exceed baseline MAE by "
        f"more than **{_MAE_SLACK:.2f}** fantasy points on any position.\n"
    )

    lines.append("\n## Per-position aggregate\n")
    lines.append(
        "| Position | Baseline MAE | Treatment MAE | Delta | Verdict |"
    )
    lines.append("|----------|-------------:|--------------:|------:|---------|")
    for pos, b, t, d in per_pos:
        v = "PASS" if d <= _MAE_SLACK else "REGRESS"
        lines.append(
            f"| {pos} | {b:.3f} | {t:.3f} | {d:+.3f} | {v} |"
        )

    lines.append("\n## Per-(season, week, position)\n")
    lines.append(
        "| Season | Week | Position | n | Baseline MAE | Treatment MAE | Delta | Verdict |"
    )
    lines.append(
        "|-------:|-----:|----------|--:|-------------:|--------------:|------:|---------|"
    )
    for row in per_week_rows:
        lines.append(
            f"| {row.season} | {row.week} | {row.position} | {row.n_players} "
            f"| {row.baseline_mae:.3f} | {row.treatment_mae:.3f} "
            f"| {row.delta:+.3f} | {row.verdict} |"
        )

    lines.append(f"\n## Final verdict\n\n`verdict={verdict}`\n")

    if verdict == "SHIP":
        lines.append(
            "\nTreatment did not regress beyond the slack threshold on any "
            "position — events may default to ON in "
            "``scripts/generate_projections.py``.\n"
        )
    else:
        lines.append(
            "\nAt least one position regressed more than the slack threshold. "
            "Keep ``--use-events`` opt-in; do not default to True.\n"
        )

    if events_weeks == 0:
        lines.append(
            "\n> **Note:** Zero weeks had Gold sentiment/event data for the "
            "backtest window. Treatment equals baseline by construction, so "
            "the verdict is structurally SHIP (no regression possible). "
            "This reflects the data pipeline state at time of backtest — "
            "sentiment Gold Parquet is only populated for 2025 W1 as of "
            "Phase 61-02.  Re-run the backtest after the sentiment pipeline "
            "has produced Gold data for 2022-2024 before relying on the "
            "verdict for a ship decision.\n"
        )

    BACKTEST_MD.write_text("\n".join(lines) + "\n")
    print(f"Backtest report written to {BACKTEST_MD}")


def _print_summary(
    per_pos: List[Tuple[str, float, float, float]],
    verdict: str,
) -> None:
    print(f"\n{'=' * 70}")
    print("EVENT ADJUSTMENT BACKTEST — PER-POSITION")
    print(f"{'=' * 70}")
    print(
        f"{'Position':<10}{'Baseline MAE':>15}"
        f"{'Treatment MAE':>18}{'Delta':>12}"
    )
    print("-" * 55)
    for pos, b, t, d in per_pos:
        print(f"{pos:<10}{b:>15.3f}{t:>18.3f}{d:>+12.3f}")
    print("-" * 55)
    print(
        f"Production baseline at plan time: "
        f"{_PRODUCTION_BASELINE_MAE:.2f} MAE"
    )
    print(f"\nverdict={verdict}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    formats = list_scoring_formats()
    parser = argparse.ArgumentParser(
        description="Backtest event adjustments vs baseline heuristic"
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2022, 2023, 2024],
        help="Seasons to backtest (default: 2022 2023 2024)",
    )
    parser.add_argument(
        "--scoring",
        choices=formats,
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["qb", "rb", "wr", "te"],
        help="Positions to evaluate (default: qb rb wr te)",
    )
    args = parser.parse_args()

    print("NFL Projection Event Adjustment Backtest")
    print(
        f"Seasons: {args.seasons} | Scoring: {args.scoring.upper()} | "
        f"Positions: {[p.upper() for p in args.positions]}"
    )
    print("=" * 70)

    baseline_df, treatment_df = run_backtest(
        args.seasons, args.scoring, args.positions
    )

    if baseline_df.empty:
        print("ERROR: no backtest rows produced")
        return 1

    verdict, per_pos = _overall_verdict(
        baseline_df, treatment_df, args.positions
    )
    per_week = _compute_per_week_rows(
        baseline_df, treatment_df, args.positions
    )

    # Recompute events coverage from the per-week rows already collected.
    # If treatment != baseline anywhere we had events data for that week.
    events_weeks = int(
        ((baseline_df["projected_points"] != treatment_df["projected_points"]))
        .groupby([baseline_df["season"], baseline_df["week"]])
        .any()
        .sum()
    )
    total_weeks = int(baseline_df[["season", "week"]].drop_duplicates().shape[0])

    _write_markdown(
        per_week,
        per_pos,
        verdict,
        args.seasons,
        args.scoring,
        events_weeks,
        total_weeks,
    )
    _print_summary(per_pos, verdict)

    return 0


if __name__ == "__main__":
    sys.exit(main())
