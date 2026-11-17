"""Re-score projections under a league's custom Sleeper scoring (Phase 91).

Generic projections are computed with a preset (half-PPR). Dynasty/custom leagues
often use full PPR, TE premium, 6-point passing TDs, first-down bonuses, etc., which
reorder player value. This module recomputes per-player points from the per-stat
projection columns using a league's raw Sleeper ``scoring_settings`` dict, so all
downstream value (VORP, ranks, lineup, drops, recommendations) reflects the real league.

Only offensive stats we actually project are scored. Rules we can't model from the
available columns (first downs, 2-pt conversions, fumbles, kicker, DST) are reported via
:func:`unmodeled_offense_keys` so the caller can disclose the gap rather than hide it.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

# Sleeper scoring key -> projection column (offensive stats we project).
_STAT_MAP: Dict[str, str] = {
    "pass_yd": "passing_yards",
    "pass_td": "passing_tds",
    "pass_int": "interceptions",
    "rush_yd": "rushing_yards",
    "rush_td": "rushing_tds",
    "rec": "receptions",
    "rec_yd": "receiving_yards",
    "rec_td": "receiving_tds",
}

# First downs are not on any board, but they are a stable function of the stat we do
# project. Fit on 2016-2025 regular-season Bronze weekly (65,610 player-weeks):
# receiving first downs per reception and rushing first downs per rushing yard.
FD_PER_RECEPTION: Dict[str, float] = {"QB": 0.39, "RB": 0.35, "WR": 0.61, "TE": 0.54}
FD_PER_RUSH_YARD: Dict[str, float] = {
    "QB": 0.075,
    "RB": 0.052,
    "WR": 0.048,
    "TE": 0.096,
}

# Offensive scoring keys we recognize but cannot model (no projection column).
_UNMODELED_OFFENSE = {
    "rec_fd",
    "rush_fd",
    "pass_2pt",
    "rush_2pt",
    "rec_2pt",
    "fum_lost",
    "fum",
}


def score_with_settings(
    projections: pd.DataFrame,
    scoring_settings: Dict[str, Any],
    model_first_downs: bool = False,
) -> pd.DataFrame:
    """Return a copy of ``projections`` with custom points applied.

    Overwrites ``projected_season_points`` (and ``projected_points`` if present) with
    points computed under ``scoring_settings`` so existing consumers
    (``compute_value_scores``, the engine, the optimizer) use league-accurate values.
    Adds a ``base_season_points`` column preserving the original preset value.

    TE premium (``bonus_rec_te``) adds to receptions for TE rows only.

    ``model_first_downs=True`` also scores ``rec_fd`` / ``rush_fd`` from the
    projected receptions / rushing yards (:data:`FD_PER_RECEPTION`,
    :data:`FD_PER_RUSH_YARD`). Off by default so existing callers (waivers,
    draft) keep their numbers; the lineup tool turns it on.
    """
    if projections is None or projections.empty or not scoring_settings:
        return projections
    df = projections.copy()

    points = pd.Series(0.0, index=df.index)
    for key, col in _STAT_MAP.items():
        weight = scoring_settings.get(key)
        if weight and col in df.columns:
            points = points + df[col].fillna(0) * float(weight)

    te_bonus = scoring_settings.get("bonus_rec_te")
    if te_bonus and "receptions" in df.columns and "position" in df.columns:
        is_te = df["position"].astype(str).str.upper() == "TE"
        points = points + is_te.astype(float) * df["receptions"].fillna(0) * float(
            te_bonus
        )

    if model_first_downs and "position" in df.columns:
        pos = df["position"].astype(str).str.upper()
        rec_fd, rush_fd = scoring_settings.get("rec_fd"), scoring_settings.get(
            "rush_fd"
        )
        if rec_fd and "receptions" in df.columns:
            rate = pos.map(FD_PER_RECEPTION).fillna(0.0)
            points = points + df["receptions"].fillna(0) * rate * float(rec_fd)
        if rush_fd and "rushing_yards" in df.columns:
            rate = pos.map(FD_PER_RUSH_YARD).fillna(0.0)
            points = points + df["rushing_yards"].fillna(0).clip(
                lower=0
            ) * rate * float(rush_fd)

    if "projected_season_points" in df.columns:
        df["base_season_points"] = df["projected_season_points"]
    df["projected_season_points"] = points.round(1)
    if "projected_points" in df.columns:
        df["projected_points"] = points.round(1)
    return df


def unmodeled_offense_keys(
    scoring_settings: Dict[str, Any], model_first_downs: bool = False
) -> List[str]:
    """List offensive scoring rules present in the league but not modeled.

    Lets the caller disclose what the custom score omits (first downs, 2-pt
    conversions, fumbles) rather than implying full fidelity. With
    ``model_first_downs`` the first-down rules are not omitted.
    """
    skip = {"rec_fd", "rush_fd"} if model_first_downs else set()
    return sorted(
        k
        for k in _UNMODELED_OFFENSE - skip
        if scoring_settings.get(k) not in (None, 0, 0.0)
    )


# config.SCORING_CONFIGS keys -> the Sleeper scoring keys score_with_settings reads.
_CONFIG_TO_SLEEPER = {
    "reception": "rec",
    "rush_yd": "rush_yd",
    "rec_yd": "rec_yd",
    "rush_td": "rush_td",
    "rec_td": "rec_td",
    "pass_yd": "pass_yd",
    "pass_td": "pass_td",
    "interception": "pass_int",
    "fumble_lost": "fum_lost",
}


def scoring_from_format(scoring_format: str) -> Dict[str, float]:
    """Sleeper-keyed scoring dict for a ``config.SCORING_CONFIGS`` preset."""
    from src.config import SCORING_CONFIGS

    base = SCORING_CONFIGS[scoring_format]
    return {
        _CONFIG_TO_SLEEPER[k]: v for k, v in base.items() if k in _CONFIG_TO_SLEEPER
    }
