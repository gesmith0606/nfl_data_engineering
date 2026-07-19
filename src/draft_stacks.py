"""Draft stack hints -- correlation-network-powered stacking signals.

Scans the UC3 stability-gated correlation-edge dataset
(``src/graph_correlation.py``, ``data/gold/correlations/``) for edges that
link a still-available player to a player already on the user's roster, and
surfaces them as draft-time hints: "this available player stacks well with
someone you already drafted" (positive correlation) or "this available
player shares a ceiling with someone you already drafted, so don't expect
both to spike" (negative correlation).

This is a thin product-surface read over the existing UC3 artifact -- it
reuses :func:`src.graph_correlation.load_latest_correlations` as the single
source of truth for the on-disk edge dataset rather than re-deriving the
parquet-loading logic. The rho thresholds below are specific to this
draft-time hint surface (stronger than the general lineup-insight threshold
``graph_correlation.MIN_INSIGHT_RHO`` used by ``compute_stack_insights``),
since a hint interrupting an active draft should only fire on a materially
strong signal.

Fail-open (D-06 contract): no correlation artifact, no roster, or no
matching edges all return an empty list rather than raising.
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

try:
    from graph_correlation import load_latest_correlations
except ImportError:  # pragma: no cover
    from src.graph_correlation import load_latest_correlations

logger = logging.getLogger(__name__)

# Draft-time hint thresholds -- stronger than graph_correlation's general
# MIN_INSIGHT_RHO=0.10 lineup-insight floor.
STACK_BONUS_RHO_MIN: float = 0.25
SHARED_CEILING_RHO_MAX: float = -0.20


def _resolve_team(row: pd.Series) -> Optional[str]:
    team = row.get("recent_team", row.get("team"))
    return str(team) if team not in (None, "") else None


def get_stack_hints(
    available_df: Optional[pd.DataFrame],
    my_roster: List[Dict],
    edges_df: Optional[pd.DataFrame] = None,
) -> List[Dict]:
    """Stack hints for every available player correlated with the roster.

    Args:
        available_df: The session board's available-player pool. Needs
            ``player_id``/``player_name``/``position`` columns; ``team`` or
            ``recent_team`` is used when present.
        my_roster: The session's ``board.my_roster`` -- a list of player
            dicts already drafted by the user.
        edges_df: Optional pre-loaded correlation-edge DataFrame; defaults
            to :func:`load_latest_correlations` (the latest saved Gold
            artifact).

    Returns:
        List of dicts with ``player_name``, ``position``, ``team``,
        ``rostered_player_name``, ``rho``, ``n_games``, ``kind`` (one of
        ``stack_bonus`` / ``shared_ceiling_warning``). Empty list when no
        artifact, no roster, or no qualifying edges exist -- never raises.
    """
    if available_df is None or available_df.empty or not my_roster:
        return []
    if "player_id" not in available_df.columns:
        return []

    roster_names: Dict[str, str] = {
        str(p.get("player_id")): p.get("player_name", "")
        for p in my_roster
        if p.get("player_id")
    }
    if not roster_names:
        return []

    if edges_df is None:
        try:
            edges_df = load_latest_correlations()
        except Exception as exc:  # pragma: no cover -- defensive, D-06
            logger.warning("Stack hints: failed to load correlation edges: %s", exc)
            return []
    if edges_df is None or edges_df.empty:
        return []

    pairs = edges_df[edges_df.get("level") == "pair"]
    if pairs.empty:
        return []

    avail = (
        available_df.assign(_pid=available_df["player_id"].astype(str))
        .drop_duplicates(subset=["_pid"])
        .set_index("_pid")
    )

    hints: List[Dict] = []
    for _, row in pairs.iterrows():
        rho = row.get("rho")
        if rho is None or pd.isna(rho):
            continue
        rho = float(rho)
        if rho >= STACK_BONUS_RHO_MIN:
            kind = "stack_bonus"
        elif rho <= SHARED_CEILING_RHO_MAX:
            kind = "shared_ceiling_warning"
        else:
            continue

        id_a, id_b = str(row.get("player_id_a")), str(row.get("player_id_b"))
        if id_a in roster_names and id_b in avail.index:
            rostered_id, avail_id = id_a, id_b
        elif id_b in roster_names and id_a in avail.index:
            rostered_id, avail_id = id_b, id_a
        else:
            continue

        avail_row = avail.loc[avail_id]
        hints.append(
            {
                "player_name": str(avail_row.get("player_name", "")),
                "position": str(avail_row.get("position", "")),
                "team": _resolve_team(avail_row),
                "rostered_player_name": roster_names[rostered_id],
                "rho": rho,
                "n_games": int(row.get("n_games", 0) or 0),
                "kind": kind,
            }
        )

    return hints


__all__ = [
    "STACK_BONUS_RHO_MIN",
    "SHARED_CEILING_RHO_MAX",
    "get_stack_hints",
]
