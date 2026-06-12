#!/usr/bin/env python3
"""ELITE 3.1 — Weekly Graded-Season Dashboard.

Produces a per-week grading report comparing our published Gold projections
against Sleeper consensus and actuals, and our game-prediction line-capture
vs the open-proxy/close spread.

The script grades one (season, week) at a time.  The Tuesday pipeline runs
it for the *previous* week once actuals are final.  All metrics match the
``scripts/backtest_projections.py --vs-consensus`` path exactly.

Usage
-----
::

    # Grade 2024 week 10 (smoke-test; all data exists locally)
    python scripts/weekly_grading_report.py --season 2024 --week 10

    # Grade the previous week from the live 2026 season
    python scripts/weekly_grading_report.py --season 2026 --week 3

    # Override data root for testing
    python scripts/weekly_grading_report.py --season 2024 --week 10 \\
        --data-root /tmp/test_data

Outputs
-------
- ``output/grading/season=YYYY/week=WW_report.md``  — human-readable markdown
- ``output/grading/season=YYYY/week=WW_report.json`` — machine-readable JSON
- stdout compact summary (always, even on partial data)

Exit codes
----------
- 0: Report produced (may have partial sections if data is missing).
- 1: Argument error.
- 2: Critical I/O failure (no Gold projections found).

Fail-open design: missing consensus data → fantasy section skipped with a
warning; missing odds snapshots → spread section skipped with a warning.
The script never blocks the pipeline for missing upstream data.
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import logging
import math
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if os.path.join(_PROJECT_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from consensus_metrics import (  # noqa: E402
    CONSENSUS_MIN_PTS,
    CONSENSUS_POSITIONS,
    TOP_N,
    apply_consensus_filter,
    build_cumulative_table,
    build_position_table,
)
from prediction_backtester import (  # noqa: E402
    compute_line_capture_summary,
    evaluate_line_capture,
)
from odds_snapshot_loader import load_open_close_lines  # noqa: E402
from scoring_calculator import calculate_fantasy_points_df  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# A+ gate constants (ELITE 3.1 — never change without updating CLAUDE.md)
# ---------------------------------------------------------------------------
_APLUS_MEAN_CAPTURE_PTS: float = 0.3   # spread line capture gate
_APLUS_N_PICKS: int = 150              # minimum picks for kill criterion
_APLUS_N_PICKS_GATE: int = 150         # picks needed for A+ gate verdict
_APLUS_N_PICKS_INTERIM: int = 100      # interim check threshold
_SPREAD_KILL_THRESHOLD: float = 0.0    # capture ≤ 0 at n ≥ 150 = no edge


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _latest_parquet(directory: str) -> Optional[str]:
    """Return the lexicographically last .parquet file in ``directory``, or None."""
    files = sorted(globmod.glob(os.path.join(directory, "*.parquet")))
    return files[-1] if files else None


def _load_gold_projections(
    data_root: str,
    season: int,
    week: int,
    scoring: str = "half_ppr",
) -> pd.DataFrame:
    """Load our published Gold projections for (season, week).

    Reads the latest parquet from
    ``data/gold/projections/season=YYYY/week=WW/``.

    Args:
        data_root: Root data directory (default: ``data/``).
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format string (filters by filename convention).

    Returns:
        DataFrame with at least ``player_id``, ``player_name``, ``position``,
        ``projected_points``.  Empty if not found.
    """
    week_dir = os.path.join(
        data_root, "gold", "projections", f"season={season}", f"week={week}"
    )
    if not os.path.isdir(week_dir):
        logger.warning("Gold projections not found: %s", week_dir)
        return pd.DataFrame()

    # Prefer scoring-specific file; fall back to any parquet.
    scoring_files = sorted(
        globmod.glob(os.path.join(week_dir, f"*{scoring}*.parquet"))
    )
    all_files = sorted(globmod.glob(os.path.join(week_dir, "*.parquet")))
    files = scoring_files if scoring_files else all_files

    if not files:
        logger.warning("No parquet files in %s", week_dir)
        return pd.DataFrame()

    df = pd.read_parquet(files[-1])
    df["season"] = int(season)
    df["week"] = int(week)
    return df


def _load_consensus(
    data_root: str,
    season: int,
    week: int,
    scoring: str = "half_ppr",
    source: str = "sleeper",
) -> pd.DataFrame:
    """Load Silver consensus projections for (season, week).

    Reads from ``data/silver/external_projections/season=YYYY/week=WW/``.

    Args:
        data_root: Root data directory.
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format to filter on.
        source: Source label to filter on (default "sleeper").

    Returns:
        DataFrame with ``player_id``, ``player_name``, ``consensus_proj``,
        ``season``, ``week``.  Empty if not found.
    """
    week_str = f"{week:02d}"
    week_dir = os.path.join(
        data_root,
        "silver",
        "external_projections",
        f"season={season}",
        f"week={week_str}",
    )
    if not os.path.isdir(week_dir):
        logger.warning("Silver consensus not found: %s", week_dir)
        return pd.DataFrame()

    latest = _latest_parquet(week_dir)
    if latest is None:
        return pd.DataFrame()

    try:
        df = pd.read_parquet(latest)
    except Exception as exc:
        logger.warning("Could not read consensus parquet %s: %s", latest, exc)
        return pd.DataFrame()

    # Filter to requested source and scoring.
    if "source" in df.columns:
        df = df[df["source"] == source].copy()
    if "scoring_format" in df.columns and scoring in df["scoring_format"].values:
        df = df[df["scoring_format"] == scoring].copy()

    if df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"projected_points": "consensus_proj"})
    df["season"] = int(season)
    df["week"] = int(week)
    keep = [c for c in ["player_id", "player_name", "season", "week", "consensus_proj"] if c in df.columns]
    return df[keep]


def _load_actuals(
    data_root: str,
    season: int,
    week: int,
    scoring: str = "half_ppr",
) -> pd.DataFrame:
    """Load actual fantasy points from Bronze weekly data for (season, week).

    Args:
        data_root: Root data directory.
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format for fantasy point calculation.

    Returns:
        DataFrame with ``player_id``, ``player_name``, ``position``,
        ``actual_points``.  Empty if not found.
    """
    bronze_dir = os.path.join(data_root, "bronze", "players", "weekly")
    season_dir = os.path.join(bronze_dir, f"season={season}")
    if not os.path.isdir(season_dir):
        logger.warning("Bronze weekly not found: %s", season_dir)
        return pd.DataFrame()

    latest = _latest_parquet(season_dir)
    if latest is None:
        return pd.DataFrame()

    try:
        weekly_df = pd.read_parquet(latest)
    except Exception as exc:
        logger.warning("Could not read weekly parquet: %s", exc)
        return pd.DataFrame()

    # Handle air_yards column rename.
    if "air_yards" not in weekly_df.columns and "receiving_air_yards" in weekly_df.columns:
        weekly_df = weekly_df.copy()
        weekly_df["air_yards"] = weekly_df["receiving_air_yards"].fillna(0)

    week_df = weekly_df[
        (weekly_df["season"] == season) & (weekly_df["week"] == week)
    ].copy()

    if week_df.empty:
        return pd.DataFrame()

    week_df = calculate_fantasy_points_df(week_df, scoring_format=scoring, output_col="actual_points")

    keep = [c for c in ["player_id", "player_name", "position", "actual_points"] if c in week_df.columns]
    return week_df[keep]


def _load_game_predictions(
    data_root: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Load our published Gold game predictions for (season, week).

    Args:
        data_root: Root data directory.
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame with game-prediction columns; empty if not found.
    """
    week_dir = os.path.join(
        data_root, "gold", "predictions", f"season={season}", f"week={week}"
    )
    if not os.path.isdir(week_dir):
        return pd.DataFrame()

    latest = _latest_parquet(week_dir)
    if latest is None:
        return pd.DataFrame()

    try:
        return pd.read_parquet(latest)
    except Exception as exc:
        logger.warning("Could not read predictions parquet: %s", exc)
        return pd.DataFrame()


def _load_schedules(
    data_root: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Load schedule data for a given (season, week) to get actual game results.

    Args:
        data_root: Root data directory.
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame filtered to the target week.  Empty if not found or if the
        week has not completed yet (no result columns present).
    """
    bronze_dir = os.path.join(data_root, "bronze")

    # Try games first, then schedules (two naming conventions in the repo).
    for sub in ("games", "schedules"):
        season_dir = os.path.join(bronze_dir, sub, f"season={season}")
        if not os.path.isdir(season_dir):
            continue
        latest = _latest_parquet(season_dir)
        if latest is None:
            continue
        try:
            df = pd.read_parquet(latest)
            if "season" not in df.columns:
                df["season"] = int(season)
            week_df = df[df["week"] == week].copy()
            if not week_df.empty:
                return week_df
        except Exception as exc:
            logger.warning("Could not read schedule: %s", exc)

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_fantasy_section(
    gold_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    season: int,
    week: int,
    scoring: str,
) -> Dict[str, Any]:
    """Build the fantasy consensus-gap section for the grading report.

    Joins Gold projections, consensus, and actuals on ``player_id``.
    Applies the standard cons>=5, w3-18 population.

    Args:
        gold_df: Our published projections for this week.
        consensus_df: Sleeper consensus projections.
        actuals_df: Actual fantasy points.
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format string.

    Returns:
        Dict with keys: ``status`` ("ok" | "skipped"), ``reason`` (if skipped),
        ``week_table`` (list of per-position dicts), ``n_matched``,
        ``n_after_filter``, ``match_rate``.
    """
    empty_result: Dict[str, Any] = {
        "status": "skipped",
        "reason": "",
        "week_table": [],
        "n_matched": 0,
        "n_after_filter": 0,
        "match_rate": float("nan"),
    }

    if gold_df.empty:
        empty_result["reason"] = "No Gold projections found"
        return empty_result

    if actuals_df.empty:
        empty_result["reason"] = "No actuals found (week not yet complete?)"
        return empty_result

    if consensus_df.empty:
        empty_result["reason"] = "No Sleeper consensus data in Silver"
        return empty_result

    # Step 1: join projections with actuals on player_id.
    has_pid_gold = "player_id" in gold_df.columns
    has_pid_act = "player_id" in actuals_df.columns

    if has_pid_gold and has_pid_act:
        gold_copy = gold_df.copy()
        act_copy = actuals_df.copy()
        gold_copy["player_id"] = gold_copy["player_id"].astype(str).str.strip()
        act_copy["player_id"] = act_copy["player_id"].astype(str).str.strip()
        act_copy = act_copy.sort_values("actual_points", ascending=False).drop_duplicates(
            subset=["player_id"], keep="first"
        )
        proj_act = gold_copy.merge(
            act_copy[["player_id", "actual_points", "position"]],
            on="player_id",
            how="inner",
            suffixes=("", "_act"),
        )
        # Prefer position from actuals (more reliable) but fall back to gold.
        if "position_act" in proj_act.columns:
            proj_act["position"] = proj_act["position_act"].combine_first(proj_act["position"])
            proj_act = proj_act.drop(columns=["position_act"])
    else:
        # Name-based fallback.
        act_copy = actuals_df.copy()
        act_copy = act_copy.sort_values("actual_points", ascending=False).drop_duplicates(
            subset=["player_name"], keep="first"
        )
        proj_act = gold_df.merge(
            act_copy[["player_name", "actual_points", "position"]],
            on="player_name",
            how="inner",
            suffixes=("", "_act"),
        )
        if "position_act" in proj_act.columns:
            proj_act["position"] = proj_act["position_act"].combine_first(proj_act["position"])
            proj_act = proj_act.drop(columns=["position_act"])

    if proj_act.empty:
        empty_result["reason"] = "No player-weeks matched between projections and actuals"
        return empty_result

    proj_act["season"] = int(season)
    proj_act["week"] = int(week)

    # Step 2: join consensus.
    has_pid_cons = "player_id" in consensus_df.columns
    if has_pid_gold and has_pid_cons:
        proj_act_copy = proj_act.copy()
        cons_copy = consensus_df.copy()
        proj_act_copy["player_id"] = proj_act_copy["player_id"].astype(str).str.strip()
        cons_copy["player_id"] = cons_copy["player_id"].astype(str).str.strip()
        matched = proj_act_copy.merge(
            cons_copy[["player_id", "consensus_proj"]],
            on="player_id",
            how="inner",
        )
    else:
        # Name fallback.
        proj_act_copy = proj_act.copy()
        cons_copy = consensus_df.copy()
        proj_act_copy["_name_norm"] = proj_act_copy["player_name"].str.strip().str.lower()
        cons_copy["_name_norm"] = cons_copy["player_name"].str.strip().str.lower()
        matched = proj_act_copy.merge(
            cons_copy[["_name_norm", "consensus_proj"]],
            on="_name_norm",
            how="inner",
        ).drop(columns=["_name_norm"])

    if matched.empty:
        empty_result["reason"] = "No player-weeks matched consensus on player_id/name"
        return empty_result

    n_matched = len(matched)
    # Match rate relative to our projections (denominator = our eligible rows).
    n_ours = len(proj_act[proj_act["position"].isin(CONSENSUS_POSITIONS)])
    match_rate = n_matched / n_ours if n_ours > 0 else float("nan")

    # Step 3: apply the standard evaluation filter (cons>=5, positions).
    # Note: week filter not applied here because this is a single-week call.
    filtered = apply_consensus_filter(matched, weeks=None)
    n_after_filter = len(filtered)

    if filtered.empty:
        empty_result["reason"] = (
            f"No player-weeks survive cons>={CONSENSUS_MIN_PTS} filter "
            f"(n_matched={n_matched})"
        )
        return empty_result

    week_table = build_position_table(filtered)

    return {
        "status": "ok",
        "reason": "",
        "week_table": week_table,
        "n_matched": int(n_matched),
        "n_after_filter": int(n_after_filter),
        "match_rate": float(match_rate),
        "scoring": scoring,
    }


def _build_cumulative_section(
    data_root: str,
    season: int,
    week: int,
    scoring: str = "half_ppr",
) -> Dict[str, Any]:
    """Build the season-to-date cumulative gap table.

    Loads all available weeks for the season up to (and including) ``week``,
    joins consensus and actuals, and calls ``build_cumulative_table``.

    Args:
        data_root: Root data directory.
        season: NFL season year.
        week: Current completed week.
        scoring: Scoring format string.

    Returns:
        Dict with ``status``, ``cumulative_table`` (list of per-position dicts),
        ``weeks_loaded``, ``reason`` (if skipped).
    """
    empty_result: Dict[str, Any] = {
        "status": "skipped",
        "reason": "",
        "cumulative_table": [],
        "weeks_loaded": 0,
    }

    # Collect matched data for all completed weeks in the season.
    all_frames: List[pd.DataFrame] = []
    for w in range(3, week + 1):
        gold_df = _load_gold_projections(data_root, season, w, scoring)
        consensus_df = _load_consensus(data_root, season, w, scoring)
        actuals_df = _load_actuals(data_root, season, w, scoring)

        if gold_df.empty or actuals_df.empty or consensus_df.empty:
            continue

        section = _build_fantasy_section(gold_df, consensus_df, actuals_df, season, w, scoring)
        if section["status"] != "ok":
            continue

        # Reconstruct the matched+filtered frame from the section data.
        # Re-run the join to get the raw matched frame for aggregation.
        # (Cheaper than caching all frames in _build_fantasy_section.)
        has_pid_gold = "player_id" in gold_df.columns
        has_pid_act = "player_id" in actuals_df.columns
        has_pid_cons = "player_id" in consensus_df.columns

        if has_pid_gold and has_pid_act:
            g = gold_df.copy()
            a = actuals_df.copy()
            g["player_id"] = g["player_id"].astype(str).str.strip()
            a["player_id"] = a["player_id"].astype(str).str.strip()
            a = a.sort_values("actual_points", ascending=False).drop_duplicates(
                subset=["player_id"], keep="first"
            )
            pa = g.merge(a[["player_id", "actual_points", "position"]], on="player_id", how="inner", suffixes=("", "_act"))
            if "position_act" in pa.columns:
                pa["position"] = pa["position_act"].combine_first(pa.get("position", pa.get("position_act")))
                pa = pa.drop(columns=["position_act"])
        else:
            a = actuals_df.copy()
            a = a.sort_values("actual_points", ascending=False).drop_duplicates(subset=["player_name"], keep="first")
            pa = gold_df.merge(a[["player_name", "actual_points", "position"]], on="player_name", how="inner", suffixes=("", "_act"))
            if "position_act" in pa.columns:
                pa["position"] = pa["position_act"].combine_first(pa.get("position", pa.get("position_act")))
                pa = pa.drop(columns=["position_act"])

        if pa.empty:
            continue

        pa["season"] = int(season)
        pa["week"] = int(w)

        if has_pid_gold and has_pid_cons:
            pa_c = pa.copy()
            c = consensus_df.copy()
            pa_c["player_id"] = pa_c["player_id"].astype(str).str.strip()
            c["player_id"] = c["player_id"].astype(str).str.strip()
            merged = pa_c.merge(c[["player_id", "consensus_proj"]], on="player_id", how="inner")
        else:
            pa_c = pa.copy()
            c = consensus_df.copy()
            pa_c["_nm"] = pa_c["player_name"].str.strip().str.lower()
            c["_nm"] = c["player_name"].str.strip().str.lower()
            merged = pa_c.merge(c[["_nm", "consensus_proj"]], on="_nm", how="inner").drop(columns=["_nm"])

        if not merged.empty:
            all_frames.append(merged)

    if not all_frames:
        empty_result["reason"] = "No weeks with complete data (projections + consensus + actuals)"
        return empty_result

    combined = pd.concat(all_frames, ignore_index=True)
    weeks_loaded = int(combined["week"].nunique())

    cumulative_table = build_cumulative_table(combined, season, week)

    return {
        "status": "ok",
        "reason": "",
        "cumulative_table": cumulative_table,
        "weeks_loaded": weeks_loaded,
    }


def _build_spread_section(
    predictions_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    season: int,
    week: int,
    snapshot_dir: str,
) -> Dict[str, Any]:
    """Build the spread line-capture section.

    Loads Bronze odds-API snapshots for the season, derives open/close lines,
    joins to our published picks, and calls ``evaluate_line_capture`` +
    ``compute_line_capture_summary``.

    The section is informational when n < _APLUS_N_PICKS_INTERIM; a verdict
    is rendered at n ≥ _APLUS_N_PICKS_GATE.

    Args:
        predictions_df: Our Gold game predictions DataFrame.
        schedules_df: Schedule data for this week (used for actual margins).
        season: NFL season year.
        week: NFL week number.
        snapshot_dir: Path to ``data/bronze/odds_api/snapshots`` root.

    Returns:
        Dict with ``status``, ``n``, ``mean_capture``, ``tier_breakdown``,
        ``season_to_date_n``, ``gate_status``, ``reason`` (if skipped).
    """
    empty_result: Dict[str, Any] = {
        "status": "skipped",
        "reason": "",
        "n": 0,
        "mean_capture": float("nan"),
        "tier_breakdown": [],
        "gate_status": "insufficient_data",
    }

    if predictions_df.empty:
        empty_result["reason"] = "No Gold game predictions found"
        return empty_result

    # Load open/close lines from Bronze snapshots.
    lines_df = load_open_close_lines(
        season=season,
        market="spreads",
        snapshot_dir=snapshot_dir,
    )

    if lines_df.empty:
        empty_result["reason"] = (
            "No odds-API snapshots found (ODDS_API_KEY not yet set or season "
            "not captured).  Line-capture grading deferred to 2026 w1."
        )
        return empty_result

    # Join predictions to open/close lines on (home_team, away_team).
    # Predictions use ``home_team`` / ``away_team`` columns.
    required_pred_cols = {"home_team", "away_team"}
    if not required_pred_cols.issubset(predictions_df.columns):
        empty_result["reason"] = "Predictions missing home_team/away_team columns"
        return empty_result

    picks = predictions_df.copy()
    lines = lines_df.copy()

    # Normalise team abbreviations for join.
    picks["_home"] = picks["home_team"].str.strip().str.upper()
    picks["_away"] = picks["away_team"].str.strip().str.upper()
    lines["_home"] = lines["home_team_nfl"].str.strip().str.upper()
    lines["_away"] = lines["away_team_nfl"].str.strip().str.upper()

    joined = picks.merge(
        lines[["_home", "_away", "open_spread", "close_spread"]],
        on=["_home", "_away"],
        how="left",
    ).drop(columns=["_home", "_away"])

    # Map ATS pick to pick_side: if ats_pick == home_team → "home", else "away".
    if "ats_pick" in joined.columns and "home_team" in joined.columns:
        joined["pick_side"] = joined.apply(
            lambda r: "home" if str(r.get("ats_pick", "")).strip().upper() == str(r.get("home_team", "")).strip().upper() else "away",
            axis=1,
        )
    else:
        empty_result["reason"] = "Predictions missing ats_pick column"
        return empty_result

    # The snapshot loader returns open_spread/close_spread in SPORTSBOOK sign
    # convention (negative = home favoured).  evaluate_line_capture expects this.
    result_df = evaluate_line_capture(
        joined,
        open_col="open_spread",
        close_col="close_spread",
        pick_side_col="pick_side",
        market="spread",
    )

    # Compute edge_col if available (for tier breakdown).
    edge_col: Optional[str] = None
    if "spread_edge" in result_df.columns:
        edge_col = "spread_edge"
    elif "predicted_spread" in result_df.columns and "vegas_spread" in result_df.columns:
        result_df["_edge"] = (result_df["predicted_spread"] - result_df["vegas_spread"]).abs()
        edge_col = "_edge"

    summary = compute_line_capture_summary(result_df, edge_col=edge_col)
    n = int(summary["n"])
    mean_capture = float(summary.get("mean_capture", float("nan")))

    # Gate status.
    if n == 0:
        gate_status = "insufficient_data"
    elif n >= _APLUS_N_PICKS_GATE:
        gate_status = (
            "aplus"
            if mean_capture > _APLUS_MEAN_CAPTURE_PTS
            else "kill" if mean_capture <= _SPREAD_KILL_THRESHOLD else "trailing"
        )
    elif n >= _APLUS_N_PICKS_INTERIM:
        gate_status = "interim_check"
    else:
        gate_status = "accumulating"

    tier_breakdown = summary.get("by_tier", [])

    return {
        "status": "ok",
        "reason": "",
        "n": n,
        "mean_capture": mean_capture,
        "median_capture": float(summary.get("median_capture", float("nan"))),
        "pct_captured": float(summary.get("pct_captured", float("nan"))),
        "std_capture": float(summary.get("std_capture", float("nan"))),
        "tier_breakdown": tier_breakdown,
        "gate_status": gate_status,
        "aplus_gate": mean_capture > _APLUS_MEAN_CAPTURE_PTS,
        "kill_criterion": (
            n >= _APLUS_N_PICKS and mean_capture <= _SPREAD_KILL_THRESHOLD
        ),
    }


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------


def _json_safe(obj: Any) -> Any:
    """Recursively convert numpy types and NaN to JSON-safe Python types."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    return obj


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

_REPORT_SEPARATOR = "=" * 72


def _fmt_float(v: Any, fmt: str = ".3f", default: str = "N/A") -> str:
    """Format a float, handling NaN/None gracefully."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    return format(float(v), fmt)


def _fmt_gap(v: Any) -> str:
    """Format a MAE gap with sign; negative (win) rendered with '✓' marker."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    fv = float(v)
    sign = f"{fv:+.3f}"
    return f"{sign} (win)" if fv < -0.01 else (f"{sign} (tie)" if abs(fv) <= 0.01 else sign)


def render_markdown(report: Dict[str, Any]) -> str:
    """Render the complete grading report as a markdown string.

    Args:
        report: Full report dict from ``build_report()``.

    Returns:
        Markdown string suitable for writing to a ``.md`` file.
    """
    season = report["season"]
    week = report["week"]
    scoring = report.get("scoring", "half_ppr")
    generated_at = report.get("generated_at", "unknown")

    lines: List[str] = [
        f"# ELITE Grading Report — Season {season} Week {week}",
        f"",
        f"*Generated*: {generated_at}  ",
        f"*Scoring*: {scoring.upper()}  ",
        f"*Filter*: cons >= {CONSENSUS_MIN_PTS} pts, weeks 3-18, positions: "
        + ", ".join(CONSENSUS_POSITIONS),
        f"",
        _REPORT_SEPARATOR,
        f"",
    ]

    # --- Fantasy section ---
    fantasy = report.get("fantasy", {})
    lines += [f"## Fantasy Consensus Gap (Week {week})", ""]

    if fantasy.get("status") != "ok":
        reason = fantasy.get("reason", "unknown")
        lines += [f"**SKIPPED**: {reason}", ""]
    else:
        n_matched = fantasy.get("n_matched", 0)
        n_filt = fantasy.get("n_after_filter", 0)
        match_rate = fantasy.get("match_rate", float("nan"))
        lines += [
            f"Matched player-weeks: **{n_matched}** | After filter: **{n_filt}** "
            f"| Match rate: {_fmt_float(match_rate, '.1%')}",
            "",
            f"| Pos | Sys | MAE | GAP (ours − cons) | SpearmanR | Top-N HR | n |",
            f"|-----|-----|-----|-------------------|-----------|----------|---|",
        ]
        for row in fantasy.get("week_table", []):
            pos = row.get("pos", "?")
            n = row.get("n", 0)
            if n == 0:
                continue
            our_mae = _fmt_float(row.get("our_mae"), ".2f")
            con_mae = _fmt_float(row.get("con_mae"), ".2f")
            gap = _fmt_gap(row.get("mae_gap"))
            our_sp = _fmt_float(row.get("our_spearman"), ".3f")
            con_sp = _fmt_float(row.get("con_spearman"), ".3f")
            our_tn = _fmt_float(row.get("our_topn"), ".3f")
            con_tn = _fmt_float(row.get("con_topn"), ".3f")
            sp_gap = _fmt_float(row.get("spearman_gap"), "+.3f")
            lines += [
                f"| {pos} | Ours | {our_mae} | {gap} | {our_sp} | {our_tn} | {n:,} |",
                f"| | Sleeper | {con_mae} | | {con_sp} | {con_tn} | |",
                f"| | *Δ SpearmanR* | | | *{sp_gap}* | | |",
            ]
        lines += [""]

    # --- Cumulative section ---
    cumulative = report.get("cumulative", {})
    lines += [
        f"## Cumulative Season-to-Date (weeks 3–{week})",
        "",
    ]

    if cumulative.get("status") != "ok":
        reason = cumulative.get("reason", "unknown")
        lines += [f"**SKIPPED**: {reason}", ""]
    else:
        weeks_loaded = cumulative.get("weeks_loaded", 0)
        lines += [f"*Weeks with complete data*: {weeks_loaded}", ""]

        # A+ gate status from last row.
        ctable = cumulative.get("cumulative_table", [])
        aplus = next((r.get("aplus_gate_fantasy", False) for r in ctable if r.get("pos") == "OVERALL"), False)
        gate_label = "**ON TRACK**" if aplus else "trailing"
        lines += [f"A+ gate (MAE ≤ Sleeper + rank-corr within 0.01): {gate_label}", ""]

        lines += [
            f"| Pos | Our MAE | Cons MAE | Gap | SpearmanR | Δ Spear | n |",
            f"|-----|---------|----------|-----|-----------|---------|---|",
        ]
        for row in ctable:
            pos = row.get("pos", "?")
            n = row.get("n", 0)
            if n == 0:
                continue
            our_mae = _fmt_float(row.get("our_mae"), ".3f")
            con_mae = _fmt_float(row.get("con_mae"), ".3f")
            gap = _fmt_gap(row.get("mae_gap"))
            sp = _fmt_float(row.get("our_spearman"), ".3f")
            sp_gap = _fmt_float(row.get("spearman_gap"), "+.3f")
            lines += [f"| {pos} | {our_mae} | {con_mae} | {gap} | {sp} | {sp_gap} | {n:,} |"]
        lines += [""]

    # --- Spread line capture section ---
    spread = report.get("spread", {})
    lines += [f"## Spread Line Capture (Season-to-Date)", ""]

    if spread.get("status") != "ok":
        reason = spread.get("reason", "unknown")
        lines += [f"**SKIPPED**: {reason}", ""]
    else:
        n = spread.get("n", 0)
        mean_cap = _fmt_float(spread.get("mean_capture"), "+.3f")
        gate_status = spread.get("gate_status", "accumulating")
        lines += [
            f"Picks with capture data: **{n}**  ",
            f"Mean signed capture: **{mean_cap} pts**  ",
            f"Gate status: *{gate_status}*  ",
            f"A+ gate: mean > +{_APLUS_MEAN_CAPTURE_PTS} pts at n≥{_APLUS_N_PICKS_GATE} picks  ",
            f"Kill criterion: capture ≤ 0 at n≥{_APLUS_N_PICKS} picks  ",
            "",
        ]
        if spread.get("tier_breakdown"):
            lines += [
                "| Tier | n | Mean Capture | % Captured |",
                "|------|---|--------------|------------|",
            ]
            for tier in spread.get("tier_breakdown", []):
                lines += [
                    f"| {tier['tier']} | {tier['n']} "
                    f"| {_fmt_float(tier.get('mean_capture'), '+.3f')} "
                    f"| {_fmt_float(tier.get('pct_captured'), '.1%')} |"
                ]
            lines += [""]
        else:
            lines += ["*No tier breakdown available.*", ""]

    # --- Footer ---
    lines += [
        _REPORT_SEPARATOR,
        "",
        "### A+ Gates Reference (ELITE 3.1)",
        "",
        f"| Metric | Gate |",
        f"|--------|------|",
        f"| Fantasy A+ | Cumulative matched-MAE ≤ Sleeper, w3–18, rank-corr within 0.01 |",
        f"| Spread A+ | Mean line capture > +{_APLUS_MEAN_CAPTURE_PTS} pts, n≥{_APLUS_N_PICKS_GATE} |",
        f"| Spread Kill | Capture ≤ 0 at n≥{_APLUS_N_PICKS} → no betting edge |",
        "",
        "_Auto-generated by `scripts/weekly_grading_report.py`._",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level report builder
# ---------------------------------------------------------------------------


def build_report(
    season: int,
    week: int,
    scoring: str = "half_ppr",
    data_root: Optional[str] = None,
    snapshot_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the full grading report for (season, week).

    Fail-open: each section is individually wrapped so a failure in one section
    never blocks the others.

    Args:
        season: NFL season year.
        week: NFL week number (completed week to grade).
        scoring: Scoring format string.
        data_root: Project data root (default: ``data/`` relative to project root).
        snapshot_dir: Odds-API snapshot dir (default: standard Bronze path).

    Returns:
        Full report dict with keys:
            ``season``, ``week``, ``scoring``, ``generated_at``,
            ``fantasy``, ``cumulative``, ``spread``.
    """
    if data_root is None:
        data_root = os.path.join(_PROJECT_ROOT, "data")
    if snapshot_dir is None:
        snapshot_dir = os.path.join(
            data_root, "bronze", "odds_api", "snapshots"
        )

    generated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    report: Dict[str, Any] = {
        "season": int(season),
        "week": int(week),
        "scoring": scoring,
        "generated_at": generated_at,
    }

    # ---- Load shared data (errors are non-fatal) ----
    print(f"Loading data for {season} week {week}…")

    gold_df = _load_gold_projections(data_root, season, week, scoring)
    print(f"  Gold projections: {len(gold_df)} rows" if not gold_df.empty else "  Gold projections: NOT FOUND")

    consensus_df = _load_consensus(data_root, season, week, scoring)
    print(f"  Consensus: {len(consensus_df)} rows" if not consensus_df.empty else "  Consensus: NOT FOUND")

    actuals_df = _load_actuals(data_root, season, week, scoring)
    print(f"  Actuals: {len(actuals_df)} rows" if not actuals_df.empty else "  Actuals: NOT FOUND")

    predictions_df = _load_game_predictions(data_root, season, week)
    print(f"  Game predictions: {len(predictions_df)} rows" if not predictions_df.empty else "  Game predictions: NOT FOUND")

    schedules_df = _load_schedules(data_root, season, week)

    # ---- Section 1: Fantasy consensus gap ----
    print("\nBuilding fantasy consensus-gap section…")
    try:
        fantasy_section = _build_fantasy_section(
            gold_df, consensus_df, actuals_df, season, week, scoring
        )
    except Exception as exc:
        logger.error("Fantasy section failed: %s", exc, exc_info=True)
        fantasy_section = {"status": "error", "reason": str(exc), "week_table": []}
    report["fantasy"] = fantasy_section

    # ---- Section 2: Cumulative season-to-date ----
    print("Building cumulative season-to-date section…")
    try:
        cumulative_section = _build_cumulative_section(data_root, season, week, scoring)
    except Exception as exc:
        logger.error("Cumulative section failed: %s", exc, exc_info=True)
        cumulative_section = {"status": "error", "reason": str(exc), "cumulative_table": []}
    report["cumulative"] = cumulative_section

    # ---- Section 3: Spread line capture ----
    print("Building spread line-capture section…")
    try:
        spread_section = _build_spread_section(
            predictions_df, schedules_df, season, week, snapshot_dir
        )
    except Exception as exc:
        logger.error("Spread section failed: %s", exc, exc_info=True)
        spread_section = {"status": "error", "reason": str(exc), "n": 0}
    report["spread"] = spread_section

    return report


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def write_outputs(report: Dict[str, Any], output_root: str = "output/grading") -> Dict[str, str]:
    """Write markdown and JSON reports to disk.

    Args:
        report: Report dict from ``build_report()``.
        output_root: Root output directory.

    Returns:
        Dict with keys ``md_path`` and ``json_path``.
    """
    season = report["season"]
    week = report["week"]

    season_dir = os.path.join(output_root, f"season={season}")
    os.makedirs(season_dir, exist_ok=True)

    week_label = f"week={week:02d}"
    md_path = os.path.join(season_dir, f"{week_label}_report.md")
    json_path = os.path.join(season_dir, f"{week_label}_report.json")

    # Markdown.
    md_text = render_markdown(report)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_text)

    # JSON.
    json_data = _json_safe(report)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(json_data, fh, indent=2)

    return {"md_path": md_path, "json_path": json_path}


def print_compact_summary(report: Dict[str, Any]) -> None:
    """Print a compact one-screen summary to stdout.

    Always prints regardless of section status so the pipeline always gets
    a visible confirmation.

    Args:
        report: Report dict from ``build_report()``.
    """
    season = report["season"]
    week = report["week"]
    scoring = report.get("scoring", "half_ppr").upper()

    print(f"\n{'=' * 60}")
    print(f"ELITE GRADING REPORT — {season} Week {week} ({scoring})")
    print(f"{'=' * 60}")

    # Fantasy.
    fantasy = report.get("fantasy", {})
    f_status = fantasy.get("status", "skipped")
    if f_status == "ok":
        f_table = fantasy.get("week_table", [])
        overall = next((r for r in f_table if r.get("pos") == "OVERALL"), {})
        gap = overall.get("mae_gap", float("nan"))
        n_filt = fantasy.get("n_after_filter", 0)
        print(f"\nFantasy (this week, n={n_filt}):")
        for row in [r for r in f_table if r.get("pos") in CONSENSUS_POSITIONS]:
            pos = row["pos"]
            g = row.get("mae_gap", float("nan"))
            print(f"  {pos}: gap={_fmt_gap(g)}")
        print(f"  OVERALL: gap={_fmt_gap(gap)}")
    else:
        print(f"\nFantasy: SKIPPED — {fantasy.get('reason', 'unknown')}")

    # Cumulative.
    cumulative = report.get("cumulative", {})
    c_status = cumulative.get("status", "skipped")
    if c_status == "ok":
        ctable = cumulative.get("cumulative_table", [])
        overall_c = next((r for r in ctable if r.get("pos") == "OVERALL"), {})
        c_gap = overall_c.get("mae_gap", float("nan"))
        aplus = overall_c.get("aplus_gate_fantasy", False)
        wks = cumulative.get("weeks_loaded", 0)
        gate_lbl = "ON TRACK" if aplus else "trailing"
        print(f"\nCumulative (w3–{week}, {wks} weeks loaded):")
        print(f"  OVERALL gap: {_fmt_gap(c_gap)} | A+ gate: {gate_lbl}")
        for row in [r for r in ctable if r.get("pos") in CONSENSUS_POSITIONS]:
            pos = row["pos"]
            g = row.get("mae_gap", float("nan"))
            sp_gap = row.get("spearman_gap", float("nan"))
            print(f"  {pos}: MAE gap={_fmt_gap(g)}, SpearΔ={_fmt_float(sp_gap, '+.3f')}")
    else:
        print(f"\nCumulative: SKIPPED — {cumulative.get('reason', 'unknown')}")

    # Spread.
    spread = report.get("spread", {})
    s_status = spread.get("status", "skipped")
    if s_status == "ok":
        n = spread.get("n", 0)
        mc = spread.get("mean_capture", float("nan"))
        gate = spread.get("gate_status", "accumulating")
        print(f"\nSpread line capture: n={n}, mean={_fmt_float(mc, '+.3f')} pts | {gate}")
        if spread.get("kill_criterion"):
            print("  *** KILL CRITERION MET — no betting edge ***")
        elif spread.get("aplus_gate"):
            print(f"  A+ GATE MET (>{_APLUS_MEAN_CAPTURE_PTS} pts)")
    else:
        print(f"\nSpread: SKIPPED — {spread.get('reason', 'unknown')}")

    print(f"\n{'=' * 60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point for the weekly grading report script.

    Returns:
        Exit code: 0=success, 1=argument error, 2=critical I/O failure.
    """
    parser = argparse.ArgumentParser(
        description="ELITE 3.1 — Weekly Graded-Season Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="NFL season year (e.g. 2024).",
    )
    parser.add_argument(
        "--week",
        type=int,
        required=True,
        help="NFL week number (1-18).  The week being graded (must be complete).",
    )
    parser.add_argument(
        "--scoring",
        type=str,
        default="half_ppr",
        choices=["half_ppr", "ppr", "standard"],
        help="Fantasy scoring format (default: half_ppr).",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default=None,
        help="Root data directory (default: data/ relative to project root).",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=str,
        default=None,
        help="Odds-API snapshot directory (default: data/bronze/odds_api/snapshots).",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=None,
        help="Output root directory (default: output/grading relative to project root).",
    )
    args = parser.parse_args()

    if not (1 <= args.week <= 18):
        print(f"ERROR: --week must be 1-18, got {args.week}", file=sys.stderr)
        return 1
    if not (1999 <= args.season <= 2030):
        print(f"ERROR: --season out of range, got {args.season}", file=sys.stderr)
        return 1

    output_root = args.output_root or os.path.join(_PROJECT_ROOT, "output", "grading")

    print(f"\nELITE Weekly Grading Report")
    print(f"Season: {args.season} | Week: {args.week} | Scoring: {args.scoring.upper()}")
    print(f"Data root: {args.data_root or os.path.join(_PROJECT_ROOT, 'data')}")
    print(f"Output root: {output_root}")
    print("=" * 60)

    report = build_report(
        season=args.season,
        week=args.week,
        scoring=args.scoring,
        data_root=args.data_root,
        snapshot_dir=args.snapshot_dir,
    )

    print_compact_summary(report)

    paths = write_outputs(report, output_root=output_root)
    print(f"\nReport written:")
    print(f"  Markdown: {paths['md_path']}")
    print(f"  JSON:     {paths['json_path']}")

    # Exit 2 only if Gold projections are truly missing (critical blocker).
    fantasy_status = report.get("fantasy", {}).get("status", "skipped")
    if fantasy_status == "skipped" and "No Gold projections found" in report.get("fantasy", {}).get("reason", ""):
        print(
            "\n::warning::weekly_grading_report: No Gold projections found for "
            f"{args.season} w{args.week} — grading incomplete.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
