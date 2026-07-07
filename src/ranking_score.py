"""Ranking score module — ordering nudges decoupled from projected_points.

Rankings and point projections are currently the same number. This module
introduces a ``ranking_score`` column that equals ``projected_points`` plus
small, capped ordering nudges derived from lagged graph features (QB-WR
chemistry, red-zone share, etc.). ``ranking_score`` is used **only** for
within-position and overall ordering; displayed points, floor, ceiling, and
VORP remain the MAE-optimal ``projected_points``.

Key design:
- Nudges are additive (not multiplicative) to preserve interpretability and
  simplify the cap invariant.
- Each signal's contribution is ``alpha * z`` where ``z`` is the signal's
  z-score within the (position, season, week) group (zero-centred,
  unit-variance after clipping at ±3).
- The total nudge per player is capped to
  ``[-RANKING_NUDGE_CAP, +RANKING_NUDGE_CAP]`` (default 1.5 pts) regardless
  of how many signals are active.
- Missing graph data → ``ranking_score = projected_points`` (no nudge).
- When ``USE_RANKING_SCORE=False`` (or graph_df is absent), the column is
  still added but equals ``projected_points`` so downstream consumers never
  branch on column existence.

Config flags (module-level constants, mirror the USE_* pattern in
projection_engine.py):

    USE_RANKING_SCORE: bool   — master switch (default True).
    RANKING_NUDGE_CAP: float  — hard cap on total nudge in fantasy points.
    RANKING_SIGNAL_PARAMS: dict[str, dict[str, float]]
        Per-position mapping of ``{signal_column: alpha}`` chosen from the
        ``sweep-ranking-score`` experiment.

Chosen params (from sweep-ranking-score 2022-24 offline evaluation,
``output/heuristic_lab_cache/sweep_ranking_score.csv``):

    WR:
        qb_wr_chemistry_epa_roll3:  0.30   (W2; peak of Spearman curve, +0.011 WR12)
        rz_target_share_roll3:      0.10   (W1; joint lift +0.007 WR1324; non-degrading)
        WR12 formal gate MISS (+0.011 vs +0.025); shipped as best non-degrading.
    RB:
        No RB signal ships — all tested RB signals degrade the 25+ Spearman band
        (> -0.005) at any useful alpha. RB ranking_score = projected_points.
        RB gates MISS; honest recording per plan rule.

    Inversion_rate_1_5 = 0.00% for all evaluated configs (well below 2% gate).

All signal columns are shift(1)-lagged in their source modules
(graph_qb_wr_chemistry.py, graph_red_zone.py, graph_game_script.py) — safe
for projected-week evaluation.

Usage::

    from src.ranking_score import apply_ranking_scores

    # projections_df: output of generate_weekly_projections (already has
    # projected_points, position, player_id, season, week)
    # graph_df: concatenated graph_all_features parquet for the season(s)
    projections_df = apply_ranking_scores(
        projections_df, graph_df, season=2026, week=3
    )
    # projections_df now has a 'ranking_score' column.
    # position_rank should be recomputed from ranking_score by the caller.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Master switch.  When False, apply_ranking_scores is a no-op that only adds
#: ranking_score = projected_points.
USE_RANKING_SCORE: bool = True

#: Maximum absolute nudge in fantasy points added to any player's score.
RANKING_NUDGE_CAP: float = 1.5

#: Per-position signal parameters: {position: {signal_column: alpha}}.
#: Chosen from sweep-ranking-score 2022-24 evaluation (see module docstring).
#: Only WR and RB have active signals; QB/TE default to no-nudge.
#:
#: Selection rationale (offline eval on consensus_matched_half_ppr_20260611_235925.csv,
#: n=7009, 2022-24 w3-18 half-PPR, cons>=5):
#:
#:   WR:
#:     W2 (qb_wr_chemistry_epa_roll3) α=0.30 — peak of Spearman curve (+0.011 WR12);
#:       monotonic improvement from 0.20→0.30, flattens/reverses after 0.35.
#:     W1 (rz_target_share_roll3) α=0.10 — marginal joint lift (+0.001 WR12 on top
#:       of W2); non-degrading, adds WR1324 improvement (+0.007).
#:     WR12 gate: MISS (+0.011 vs +0.025 required); shipped as best non-degrading
#:       per plan rule ("decoupled nudges are free — record honestly which gates miss").
#:     Inversion_rate_1_5: 0.00% (all WR configs).
#:
#:   RB:
#:     No RB signal passes all-band non-degradation check (gate: no band degrades >0.005).
#:     rz_carry_share_roll3: at alpha>=0.08, the 25+ band degrades >0.006.
#:     At alpha=0.05 the 25+ is borderline (-0.003) but RB12 also regresses.
#:     R4 (predicted_script_boost) degraded RB1324 at all tested alphas.
#:     Conclusion: no RB nudge ships. RB ranking_score = projected_points.
#:     RB12 gate: MISS; honest recording per plan rule.
RANKING_SIGNAL_PARAMS: Dict[str, Dict[str, float]] = {
    "WR": {
        "qb_wr_chemistry_epa_roll3": 0.30,
        "rz_target_share_roll3": 0.10,
    },
    "RB": {},  # No non-degrading RB signal found; ordering = projected_points
}

# ---------------------------------------------------------------------------
# Warn-once guard (mirrors projection_engine._warn_once pattern)
# ---------------------------------------------------------------------------

_RANKING_WARNINGS_EMITTED: set = set()


def _warn_once(key: str, message: str) -> None:
    """Emit a ranking-score warning once per process.

    Args:
        key: Deduplification key (emitted at most once per process lifetime).
        message: Warning text sent to the module logger.
    """
    if key not in _RANKING_WARNINGS_EMITTED:
        _RANKING_WARNINGS_EMITTED.add(key)
        logger.warning(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _zscore_within_group(
    series: pd.Series,
    group_keys: pd.Series,
    clip_sigma: float = 3.0,
    min_group_size: int = 3,
) -> pd.Series:
    """Z-score a signal within groups, clipped to ±clip_sigma.

    Players in groups smaller than ``min_group_size`` receive NaN so they
    get zero nudge (insufficient peers to rank).

    Args:
        series: Raw signal values (float, may contain NaN).
        group_keys: Group identifier series aligned with ``series``.
        clip_sigma: Symmetric clip bound after standardisation.
        min_group_size: Minimum group size to compute a z-score.

    Returns:
        Float Series of z-scores, NaN where group is too small or all-NaN.
    """
    z = pd.Series(np.nan, index=series.index, dtype=float)
    for key, idx in series.groupby(group_keys).groups.items():
        grp = series.loc[idx]
        valid = grp.dropna()
        if len(valid) < min_group_size:
            continue
        mu = float(valid.mean())
        sigma = float(valid.std())
        if sigma == 0 or not np.isfinite(sigma):
            continue
        z_vals = (grp - mu) / sigma
        z.loc[idx] = z_vals.clip(-clip_sigma, clip_sigma)
    return z


def _compute_position_nudge(
    df: pd.DataFrame,
    graph_df: pd.DataFrame,
    position: str,
    signal_params: Dict[str, float],
) -> pd.Series:
    """Compute total ranking nudge for one position.

    For each signal column in ``signal_params`` the function:
    1. Joins graph values onto the projections rows for this position.
    2. Z-scores the signal within (season, week).
    3. Multiplies by ``alpha``.
    Contributions are summed, then the total is capped to
    ``[-RANKING_NUDGE_CAP, +RANKING_NUDGE_CAP]``.

    Args:
        df: Projections DataFrame (all positions, so we filter here).
        graph_df: Graph features with player_id / season / week columns.
        position: Position label (e.g. 'WR').
        signal_params: Mapping of {signal_column: alpha} for this position.

    Returns:
        Series aligned to df.index with nudge values; 0.0 where no graph data
        or position does not match.
    """
    nudge = pd.Series(0.0, index=df.index, dtype=float)
    pos_mask = df["position"] == position
    if not pos_mask.any():
        return nudge

    pos_df = df.loc[pos_mask, ["player_id", "season", "week"]].copy()

    for col, alpha in signal_params.items():
        if col not in graph_df.columns:
            logger.debug("Signal column '%s' not in graph_df — skipping", col)
            continue

        # Build lookup: (player_id, season, week) -> signal value.
        # Dedupe the key — a duplicate row in graph features would fan out the
        # left merge and break the index restore below with a length mismatch.
        gf_sub = (
            graph_df[["player_id", "season", "week", col]]
            .rename(columns={col: "_sig"})
            .drop_duplicates(subset=["player_id", "season", "week"], keep="last")
        )
        merged = pos_df.merge(gf_sub, on=["player_id", "season", "week"], how="left")
        merged.index = pos_df.index  # restore original index

        group_keys = (
            merged["season"].astype(str) + "_" + merged["week"].astype(str)
        )
        z = _zscore_within_group(merged["_sig"], group_keys)

        contribution = (alpha * z).fillna(0.0)
        nudge.loc[pos_mask] += contribution.values

    return nudge


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_ranking_scores(
    projections_df: pd.DataFrame,
    graph_df: Optional[pd.DataFrame],
    season: int,
    week: int,
    position_params: Optional[Dict[str, Dict[str, float]]] = None,
) -> pd.DataFrame:
    """Add a ``ranking_score`` column for ordering players within position.

    ``ranking_score`` equals ``projected_points`` plus a small capped nudge
    derived from lagged graph features.  It is intended **only** for
    ``position_rank`` / ``overall_rank`` ordering — ``projected_points``,
    ``projected_floor``, ``projected_ceiling``, and ``vorp`` must not be
    modified.

    When ``USE_RANKING_SCORE=False`` or ``graph_df`` is absent or empty, the
    column is added but set equal to ``projected_points`` (no reordering).

    Args:
        projections_df: Weekly projections with at minimum columns
            ``[player_id, position, projected_points]``.  ``season`` and
            ``week`` columns are expected; if absent they are derived from the
            ``season``/``week`` parameters.
        graph_df: Concatenated ``graph_all_features`` parquet for the relevant
            season(s).  May be None or empty — function degrades gracefully.
        season: The projected season (used for graph feature filtering if
            ``projections_df`` lacks a ``season`` column).
        week: The projected week (same).
        position_params: Override ``RANKING_SIGNAL_PARAMS``.  Defaults to
            module-level constant.

    Returns:
        ``projections_df`` with ``ranking_score`` column added (in-place
        mutation avoided — a copy is returned).

    Examples::

        df = apply_ranking_scores(projections_df, graph_df, season=2026, week=3)
        df["position_rank"] = (
            df.groupby("position")["ranking_score"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
    """
    out = projections_df.copy()

    # Ensure season/week present (backtest callers may not include them)
    if "season" not in out.columns:
        out["season"] = season
    if "week" not in out.columns:
        out["week"] = week

    # Default: ranking_score = projected_points (no nudge)
    out["ranking_score"] = out["projected_points"].copy()

    # Disable path: flag off or no graph data
    if not USE_RANKING_SCORE:
        return out

    if graph_df is None or (hasattr(graph_df, "empty") and graph_df.empty):
        _warn_once(
            "ranking_score_no_graph",
            "USE_RANKING_SCORE=True but graph_df is absent or empty — "
            "ranking_score will equal projected_points (no reordering).",
        )
        return out

    params = position_params if position_params is not None else RANKING_SIGNAL_PARAMS

    total_nudge = pd.Series(0.0, index=out.index, dtype=float)
    for pos, sig_params in params.items():
        if not sig_params:
            continue
        total_nudge += _compute_position_nudge(out, graph_df, pos, sig_params)

    # Apply cap
    total_nudge = total_nudge.clip(-RANKING_NUDGE_CAP, RANKING_NUDGE_CAP)

    out["ranking_score"] = (out["projected_points"] + total_nudge).clip(lower=0.0)

    n_nudged = int((total_nudge.abs() > 0.001).sum())
    logger.info(
        "apply_ranking_scores: nudged %d / %d players (season=%d week=%d)",
        n_nudged,
        len(out),
        season,
        week,
    )
    return out
