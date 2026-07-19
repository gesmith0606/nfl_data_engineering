"""Sleepers tab data -- undervalued-vs-ADP players plus the UC1
vacated-opportunity signal.

Surfaces available (skill-position) players where either:

* our model ranks them materially better than consensus ADP, or
* the UC1 vacated-opportunity network (``src/graph_vacated_opportunity.py``)
  flags them as absorbing real offseason-vacated target/carry share,

with a human-readable ``reason`` string built only from real signals -- no
fabricated numbers. The vacated-opportunity boost magnitude reuses the exact
multiplier constants (`VACATED_OPPORTUNITY_BETA`/`_MULT_MAX`) applied by
``src/projection_engine.py`` so the reported "+X% boost" always matches what
the projection pipeline would actually apply, even though the preseason
Gold parquet itself does not persist a `vacated` column (the multiplier is
baked into `projected_season_points` and the raw share is dropped).
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

try:
    from projection_engine import (
        VACATED_OPPORTUNITY_BETA,
        VACATED_OPPORTUNITY_MULT_MAX,
    )
except ImportError:  # pragma: no cover
    from src.projection_engine import (
        VACATED_OPPORTUNITY_BETA,
        VACATED_OPPORTUNITY_MULT_MAX,
    )

logger = logging.getLogger(__name__)

# Matches src.draft_optimizer.UNDERVALUED_THRESHOLD -- the same "materially
# better than ADP" bar the board's own value_tier already uses.
ADP_GAP_THRESHOLD: float = 15.0

EXCLUDED_POSITIONS = {"K", "DST"}


def _vacated_boost_pct(absorbed_share: float) -> float:
    """Boost percentage for a given vacancy_absorbed_share, per the exact
    multiplier formula ``src.projection_engine`` applies at generation time.
    """
    mult = min(
        1.0 + VACATED_OPPORTUNITY_BETA * max(absorbed_share, 0.0),
        VACATED_OPPORTUNITY_MULT_MAX,
    )
    return round((mult - 1.0) * 100.0, 1)


def build_sleeper_rows(
    available_df: Optional[pd.DataFrame],
    limit: int = 20,
    vacated_df: Optional[pd.DataFrame] = None,
) -> List[Dict]:
    """Build sleeper rows for the session's currently-available player pool.

    Args:
        available_df: The session board's available-player pool (needs
            ``player_name``/``position``/``model_rank``; ``adp_rank``/
            ``adp_diff``/``projected_points`` used when present).
        limit: Max rows to return.
        vacated_df: Optional UC1 features from
            :func:`src.graph_vacated_opportunity.build_vacated_opportunity_data`
            for the target season. ``None`` (or empty / missing columns)
            simply disables the vacated-opportunity half of the signal --
            never raises.

    Returns:
        List of dicts: ``player_name``, ``position``, ``team``,
        ``model_rank``, ``adp_rank``, ``adp_gap``, ``projected_points``,
        ``reason``. Sorted by blend (adp_gap + vacated bonus) descending.
    """
    if available_df is None or available_df.empty:
        return []

    df = available_df.copy()
    if "position" in df.columns:
        df = df[~df["position"].astype(str).str.upper().isin(EXCLUDED_POSITIONS)]
    if df.empty:
        return []

    pts_col = (
        "projected_season_points"
        if "projected_season_points" in df.columns
        else "projected_points"
    )

    vac_map: Dict[str, float] = {}
    if (
        vacated_df is not None
        and not vacated_df.empty
        and "player_id" in vacated_df.columns
        and "vacancy_absorbed_share" in vacated_df.columns
    ):
        vac_map = dict(
            zip(
                vacated_df["player_id"].astype(str),
                pd.to_numeric(vacated_df["vacancy_absorbed_share"], errors="coerce"),
            )
        )

    rows: List[Dict] = []
    for _, row in df.iterrows():
        pid = str(row.get("player_id", ""))
        model_rank = row.get("model_rank")
        adp_rank = row.get("adp_rank")
        adp_diff = row.get("adp_diff")
        adp_gap = (
            float(adp_diff) if adp_diff is not None and pd.notna(adp_diff) else None
        )

        absorbed = vac_map.get(pid) or 0.0
        vacated_fires = absorbed > 0.0
        meets_adp = adp_gap is not None and adp_gap >= ADP_GAP_THRESHOLD

        if not meets_adp and not vacated_fires:
            continue

        reasons: List[str] = []
        if (
            adp_gap is not None
            and adp_rank is not None
            and pd.notna(adp_rank)
            and model_rank is not None
            and pd.notna(model_rank)
        ):
            reasons.append(
                f"Our rank {int(model_rank)} vs ADP {float(adp_rank):.0f} "
                f"({adp_gap:+.0f})"
            )

        vacated_bonus = 0.0
        if vacated_fires:
            boost_pct = _vacated_boost_pct(absorbed)
            vacated_bonus = boost_pct
            reasons.append(f"vacated-opportunity profile: +{boost_pct:.0f}% boost applied")

        if not reasons:
            reasons.append("Undervalued relative to consensus ADP.")

        rows.append(
            {
                "player_name": str(row.get("player_name", "")),
                "position": str(row.get("position", "")),
                "team": str(row.get("recent_team", row.get("team", ""))) or None,
                "model_rank": (
                    int(model_rank)
                    if model_rank is not None and pd.notna(model_rank)
                    else None
                ),
                "adp_rank": (
                    float(adp_rank)
                    if adp_rank is not None and pd.notna(adp_rank)
                    else None
                ),
                "adp_gap": adp_gap,
                "projected_points": (
                    round(float(row[pts_col]), 1)
                    if pts_col in row.index and pd.notna(row.get(pts_col))
                    else None
                ),
                "reason": " | ".join(reasons),
                "_blend": (adp_gap or 0.0) + vacated_bonus,
            }
        )

    rows.sort(key=lambda r: r["_blend"], reverse=True)
    for r in rows:
        r.pop("_blend", None)
    return rows[:limit]


__all__ = [
    "ADP_GAP_THRESHOLD",
    "EXCLUDED_POSITIONS",
    "build_sleeper_rows",
]
