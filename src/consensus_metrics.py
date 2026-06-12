"""Shared consensus-benchmark metric functions (ELITE Phase 1.1 / 3.1).

This module extracts the fantasy-accuracy metric primitives that are used by
both the historical backtester (``scripts/backtest_projections.py``) and the
live-season grading dashboard (``scripts/weekly_grading_report.py``).  The
functions here are the SINGLE SOURCE OF TRUTH for:

  - The cons>=5 filter
  - Per-position MAE gap (ours minus consensus)
  - Within-position-week mean Spearman rank correlation
  - Top-N hit rate

Metric definitions are frozen as of the MODEL_AUDIT_2026_06_12 final standing
(n=7,009 matched player-weeks; QB −0.386, RB +0.264, WR −0.075, TE −0.428,
OVERALL −0.086 MAE gap vs Sleeper half-PPR, weeks 3-18, cons>=5).

A+ gates (ELITE 3.1):
  - Fantasy A+: cumulative matched-MAE ≤ Sleeper over 2026 w3-18,
    rank-corr within 0.01 of consensus.
  - Fantasy A: within 0.1 MAE of consensus.

Callers MUST NOT implement these metrics independently — import from here.
``backtest_projections.py`` re-exports them verbatim (no logic duplication).

Exports:
    CONSENSUS_MIN_PTS: float — minimum consensus projection for inclusion.
    CONSENSUS_POSITIONS: list[str] — positions evaluated.
    TOP_N: dict[str, int] — position→N for top-N hit rate.
    compute_mae_gap: per-position and overall MAE gap table.
    compute_spearman_rank_corr: mean within-position-week Spearman.
    compute_top_n_hit_rate: fraction of actual top-N captured in projected top-N.
    apply_consensus_filter: subset to the evaluation population.
    build_position_table: produce the full stats dict for one position slice.
    build_cumulative_table: season-to-date rolling gap per position.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical constants — never change without a note in MODEL_AUDIT / CLAUDE.md
# ---------------------------------------------------------------------------

#: Minimum consensus projection (pts) required to include a player-week.
CONSENSUS_MIN_PTS: float = 5.0

#: Skill positions evaluated in all consensus reports.
CONSENSUS_POSITIONS: List[str] = ["QB", "RB", "WR", "TE"]

#: Top-N thresholds per position (actual top-N vs projected top-N).
TOP_N: Dict[str, int] = {"QB": 12, "TE": 12, "RB": 24, "WR": 24}


# ---------------------------------------------------------------------------
# Primitive metrics
# ---------------------------------------------------------------------------


def apply_consensus_filter(
    df: pd.DataFrame,
    min_consensus_pts: float = CONSENSUS_MIN_PTS,
    weeks: Optional[tuple] = (3, 18),
) -> pd.DataFrame:
    """Return the evaluation population: cons>=min_pts, w3-18, skill positions.

    Args:
        df: DataFrame with columns ``consensus_proj``, ``week``, ``position``.
        min_consensus_pts: Minimum consensus projection to include.
        weeks: (min_week, max_week) inclusive range.  Pass None to skip filter.

    Returns:
        Filtered copy; may be empty.
    """
    mask = (
        df["consensus_proj"].notna()
        & (df["consensus_proj"] >= min_consensus_pts)
        & df["position"].isin(CONSENSUS_POSITIONS)
    )
    if weeks is not None:
        lo, hi = weeks
        mask = mask & (df["week"] >= lo) & (df["week"] <= hi)
    return df[mask].copy()


def compute_spearman_rank_corr(
    df: pd.DataFrame,
    proj_col: str,
    actual_col: str,
    position: str = "",
) -> float:
    """Compute mean within-position-week Spearman rank correlation.

    For each (season, week) group with ≥3 players, compute the Spearman rank
    correlation between ``proj_col`` and ``actual_col``.  Returns the mean
    across all qualifying weeks.

    This is the primary rank-ordering metric (start/sit relevance).  The A+
    gate requires this to be within 0.01 of the Sleeper consensus value over
    the full season.

    Args:
        df: DataFrame with ``proj_col``, ``actual_col``, ``season``, ``week``.
        proj_col: Column name for projected points.
        actual_col: Column name for actual points.
        position: Optional label used for debug logging only.

    Returns:
        Mean Spearman rank correlation as a float; NaN if not computable.
    """
    week_corrs: List[float] = []
    for (season, week), grp in df.groupby(["season", "week"]):
        if len(grp) < 3:
            continue
        rho, _ = scipy_stats.spearmanr(grp[proj_col], grp[actual_col])
        if not np.isnan(rho):
            week_corrs.append(rho)
    if not week_corrs:
        logger.debug("compute_spearman_rank_corr: no valid weeks for %s", position)
        return float("nan")
    return float(np.mean(week_corrs))


def compute_top_n_hit_rate(
    df: pd.DataFrame,
    proj_col: str,
    actual_col: str,
    position: str,
) -> float:
    """Compute Top-N hit rate: fraction of actual top-N appearing in projected top-N.

    For each (season, week) group with ≥N players, take the top-N actual scorers
    and compute what fraction appear in the projected top-N.  Average across weeks.

    N is looked up from ``TOP_N`` by ``position``; defaults to 12 for unknown
    positions.

    Args:
        df: DataFrame with ``proj_col``, ``actual_col``, ``season``, ``week``.
        proj_col: Column name for projected points.
        actual_col: Column name for actual points.
        position: Position used to look up N in ``TOP_N``.

    Returns:
        Mean hit rate in [0, 1]; NaN if not computable.
    """
    n = TOP_N.get(position, 12)
    week_rates: List[float] = []
    for (season, week), grp in df.groupby(["season", "week"]):
        if len(grp) < n:
            continue
        actual_top = set(grp.nlargest(n, actual_col).index)
        proj_top = set(grp.nlargest(n, proj_col).index)
        overlap = len(actual_top & proj_top)
        week_rates.append(overlap / n)
    if not week_rates:
        return float("nan")
    return float(np.mean(week_rates))


def compute_mae_gap(
    df: pd.DataFrame,
    our_col: str = "projected_points",
    consensus_col: str = "consensus_proj",
    actual_col: str = "actual_points",
) -> Dict[str, float]:
    """Compute per-position and overall MAE gap (ours minus consensus).

    Negative = we beat consensus; positive = consensus beats us.

    Args:
        df: Filtered DataFrame (post-``apply_consensus_filter``) with
            ``our_col``, ``consensus_col``, ``actual_col``, ``position``.
        our_col: Column name for our projected points.
        consensus_col: Column name for consensus projected points.
        actual_col: Column name for actual points.

    Returns:
        Dict mapping position label and ``"OVERALL"`` to MAE gap value.
        Missing positions return NaN.  E.g.::

            {
                "QB": -0.386,
                "RB": +0.264,
                "WR": -0.075,
                "TE": -0.428,
                "OVERALL": -0.086,
            }
    """
    result: Dict[str, float] = {}
    pos_list = CONSENSUS_POSITIONS + ["OVERALL"]

    for pos in pos_list:
        if pos == "OVERALL":
            sub = df[df["position"].isin(CONSENSUS_POSITIONS)]
        else:
            sub = df[df["position"] == pos]

        if sub.empty:
            result[pos] = float("nan")
            continue

        our_mae = (sub[our_col] - sub[actual_col]).abs().mean()
        con_mae = (sub[consensus_col] - sub[actual_col]).abs().mean()
        result[pos] = float(our_mae - con_mae)

    return result


def build_position_table(
    df: pd.DataFrame,
    our_col: str = "projected_points",
    consensus_col: str = "consensus_proj",
    actual_col: str = "actual_points",
) -> List[Dict]:
    """Build a full stats record for each position and OVERALL.

    Returns a list of dicts suitable for JSON serialisation and for building
    the markdown grading table.  Each dict contains:

        pos, n, our_mae, con_mae, mae_gap,
        our_spearman, con_spearman, spearman_gap,
        our_topn, con_topn.

    ``spearman_gap`` (ours − consensus) is the A+ rank-corr gate metric.
    Spearman and top-N are set to NaN for ``"OVERALL"`` (undefined across
    multiple positions).

    Args:
        df: Filtered DataFrame (output of ``apply_consensus_filter``).
        our_col: Column name for our projected points.
        consensus_col: Column name for consensus projected points.
        actual_col: Column name for actual points.

    Returns:
        List of per-position dicts ordered: QB, RB, WR, TE, OVERALL.
    """
    rows: List[Dict] = []

    for pos in CONSENSUS_POSITIONS + ["OVERALL"]:
        if pos == "OVERALL":
            sub = df[df["position"].isin(CONSENSUS_POSITIONS)]
            is_overall = True
        else:
            sub = df[df["position"] == pos]
            is_overall = False

        if sub.empty:
            rows.append({"pos": pos, "n": 0})
            continue

        our_mae = float((sub[our_col] - sub[actual_col]).abs().mean())
        con_mae = float((sub[consensus_col] - sub[actual_col]).abs().mean())
        mae_gap = float(our_mae - con_mae)

        if is_overall:
            our_spearman = float("nan")
            con_spearman = float("nan")
            spearman_gap = float("nan")
            our_topn = float("nan")
            con_topn = float("nan")
        else:
            our_spearman = compute_spearman_rank_corr(sub, our_col, actual_col, pos)
            con_spearman = compute_spearman_rank_corr(sub, consensus_col, actual_col, pos)
            spearman_gap = (
                float(our_spearman - con_spearman)
                if not (np.isnan(our_spearman) or np.isnan(con_spearman))
                else float("nan")
            )
            our_topn = compute_top_n_hit_rate(sub, our_col, actual_col, pos)
            con_topn = compute_top_n_hit_rate(sub, consensus_col, actual_col, pos)

        rows.append(
            {
                "pos": pos,
                "n": int(len(sub)),
                "our_mae": our_mae,
                "con_mae": con_mae,
                "mae_gap": mae_gap,
                "our_spearman": our_spearman,
                "con_spearman": con_spearman,
                "spearman_gap": spearman_gap,
                "our_topn": our_topn,
                "con_topn": con_topn,
            }
        )

    return rows


def build_cumulative_table(
    matched_df: pd.DataFrame,
    target_season: int,
    target_week: int,
    our_col: str = "projected_points",
    consensus_col: str = "consensus_proj",
    actual_col: str = "actual_points",
) -> List[Dict]:
    """Build the season-to-date cumulative gap table (weeks 3 through target_week).

    Filters to ``season == target_season`` and ``week ∈ [3, target_week]``,
    applies the standard consensus filter, and computes running totals.  Used
    in the grading report to track progress toward the A+ gate.

    A+ gate reminder:
        cumulative matched-MAE ≤ Sleeper over 2026 w3-18,
        rank-corr within 0.01 of consensus.

    Args:
        matched_df: DataFrame with ``season``, ``week``, ``projected_points``,
            ``consensus_proj``, ``actual_points``, ``position``.
        target_season: Season year to restrict to.
        target_week: Most recent completed week (inclusive upper bound).
        our_col: Column name for our projected points.
        consensus_col: Column name for consensus projected points.
        actual_col: Column name for actual points.

    Returns:
        List of per-position dicts from ``build_position_table`` for the
        season-to-date slice, plus a ``"weeks_completed"`` entry and
        ``"aplus_gate_fantasy"`` boolean (True = currently beating A+ on both
        MAE gap ≤ 0 AND spearman_gap ≥ −0.01 overall).
    """
    season_df = matched_df[
        (matched_df["season"] == target_season)
        & (matched_df["week"] >= 3)
        & (matched_df["week"] <= target_week)
    ].copy()

    if season_df.empty:
        return []

    filtered = apply_consensus_filter(season_df, weeks=None)  # week filter already applied
    if filtered.empty:
        return []

    table = build_position_table(filtered, our_col, consensus_col, actual_col)
    weeks_completed = int(season_df["week"].nunique())

    # Compute A+ gate status on the current cumulative slice.
    overall_row = next((r for r in table if r["pos"] == "OVERALL"), None)
    aplus_mae = (overall_row is not None and overall_row.get("mae_gap", 1) <= 0.0)

    # Rank-corr gate: check each position has spearman_gap >= -0.01
    pos_rows = [r for r in table if r["pos"] in CONSENSUS_POSITIONS and r.get("n", 0) > 0]
    aplus_spearman = all(
        (not np.isnan(r.get("spearman_gap", float("nan"))))
        and r.get("spearman_gap", -999) >= -0.01
        for r in pos_rows
    ) if pos_rows else False

    for row in table:
        row["weeks_completed"] = weeks_completed
        row["aplus_gate_fantasy"] = bool(aplus_mae and aplus_spearman)
        row["season"] = int(target_season)

    return table
