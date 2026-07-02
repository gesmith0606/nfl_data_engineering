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
    projections: pd.DataFrame, scoring_settings: Dict[str, Any]
) -> pd.DataFrame:
    """Return a copy of ``projections`` with custom points applied.

    Overwrites ``projected_season_points`` (and ``projected_points`` if present) with
    points computed under ``scoring_settings`` so existing consumers
    (``compute_value_scores``, the engine, the optimizer) use league-accurate values.
    Adds a ``base_season_points`` column preserving the original preset value.

    TE premium (``bonus_rec_te``) adds to receptions for TE rows only.
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

    if "projected_season_points" in df.columns:
        df["base_season_points"] = df["projected_season_points"]
    df["projected_season_points"] = points.round(1)
    if "projected_points" in df.columns:
        df["projected_points"] = points.round(1)
    return df


def unmodeled_offense_keys(scoring_settings: Dict[str, Any]) -> List[str]:
    """List offensive scoring rules present in the league but not modeled.

    Lets the caller disclose what the custom score omits (first downs, 2-pt
    conversions, fumbles) rather than implying full fidelity.
    """
    return sorted(
        k for k in _UNMODELED_OFFENSE if scoring_settings.get(k) not in (None, 0, 0.0)
    )
