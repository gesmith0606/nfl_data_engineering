"""Season prop-implied projections — season-long lines → implied season points.

Season player futures (regular-season yardage/TD/reception over-unders from
``scripts/bronze_season_props_ingestion.py``) are the market's full-season
per-player consensus, published before Week 1 — exactly the horizon the
preseason draft projections predict. This module converts those lines into
implied *season-total* fantasy points and blends ``projected_season_points``
toward them, reusing the weekly machinery in ``src/prop_implied.py``
(de-vig → Normal inversion → median across books → score).

Two deliberate differences from the weekly path:

1. **Units are season totals.** ``generate_preseason_projections`` scales to
   a 17-game season; season lines are priced on the same season-total scale,
   so no per-game conversion is needed.
2. **Availability is priced in.** A sportsbook season line embeds expected
   missed games (injury history, suspension, committee risk) while our
   17-game scaling assumes full health. The market number is therefore the
   better draft-value estimate for availability-risky players, and the blend
   pulls us toward it; ``prop_anchor_gap`` (model − market) stays the
   research signal for where we disagree.

The blend ships OFF by default: ``--season-props-blend`` on
``generate_projections.py --preseason`` opts in. Lambdas below are
PROVISIONAL — no historical season-line archive exists to backtest against,
so the gate is forward-looking: accumulate snapshots (offseason cron),
evaluate the 2026 season-end implied-vs-actual error against the model's,
then re-weight for 2027.

Coefficient-of-variation priors: season totals aggregate ~17 weekly
outcomes, so relative spread is far tighter than single-game props. With
balanced juice the implied mean equals the line regardless of CV; CV only
scales the shading adjustment when books lean one side.
"""

from typing import Dict, Optional

import pandas as pd

try:
    from src.prop_implied import apply_props_blend, compute_prop_implied_points
except ImportError:
    from prop_implied import apply_props_blend, compute_prop_implied_points

# Season market key (bronze_season_props_ingestion.SEASON_MARKETS) ->
# nflverse stat column it prices.
SEASON_MARKET_TO_STAT: Dict[str, str] = {
    "season_pass_yds": "passing_yards",
    "season_pass_tds": "passing_tds",
    "season_rush_yds": "rushing_yards",
    "season_rush_tds": "rushing_tds",
    "season_rec_yds": "receiving_yards",
    "season_rec_tds": "receiving_tds",
    "season_receptions": "receptions",
}

SEASON_MARKET_CV: Dict[str, float] = {
    "season_pass_yds": 0.15,
    "season_pass_tds": 0.30,
    "season_rush_yds": 0.30,
    "season_rush_tds": 0.40,
    "season_rec_yds": 0.30,
    "season_rec_tds": 0.40,
    "season_receptions": 0.25,
}

# A position's projection may only be blended when the market prices its
# core volume stat — a partial stat line (e.g. an RB with only a rushing-TD
# future) understates implied season points and would drag the blend down.
SEASON_CORE_MARKETS_BY_POS: Dict[str, set] = {
    "QB": {"season_pass_yds"},
    "RB": {"season_rush_yds"},
    "WR": {"season_rec_yds"},
    "TE": {"season_rec_yds"},
}

# PROVISIONAL preseason blend weights (no season-line backtest archive
# exists yet — see module docstring). RB heaviest per the v4.3 audit (the
# one position losing to consensus); QB lightest because passing lines
# cover only ~25 starters and our QB heuristic already beats consensus.
SEASON_PROPS_BLEND_LAMBDAS: Dict[str, float] = {
    "QB": 0.25,
    "RB": 0.40,
    "WR": 0.30,
    "TE": 0.30,
}


def compute_season_prop_implied_points(
    season_props_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Aggregate a season-props snapshot into implied season fantasy points.

    Thin wrapper over :func:`prop_implied.compute_prop_implied_points` with
    the season market/CV maps. The output ``prop_implied_points`` column is
    on the season-total scale (matches ``projected_season_points``).

    Args:
        season_props_df: Bronze season-props frame
            (``SEASON_PROPS_SCHEMA_COLS`` shape).
        scoring_format:  Fantasy scoring format for the implied points.

    Returns:
        One row per player with implied season stats and
        ``prop_implied_points`` (see the wrapped function for columns).
    """
    return compute_prop_implied_points(
        season_props_df,
        scoring_format=scoring_format,
        market_to_stat=SEASON_MARKET_TO_STAT,
        market_cv=SEASON_MARKET_CV,
    )


def apply_season_props_blend(
    proj_df: pd.DataFrame,
    implied_df: pd.DataFrame,
    lambdas: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Blend preseason projections toward season prop-implied points.

    ``proj' = (1−λ)·proj + λ·implied`` on ``projected_season_points`` for
    players whose market coverage includes the position's core season
    market; everyone else keeps the pure model. Adds provenance columns
    ``prop_implied_points`` and ``prop_anchor_gap`` (model − market,
    pre-blend) on the season-total scale.

    Args:
        proj_df:    Preseason projections with ``player_name``,
                    ``position`` and ``projected_season_points``.
        implied_df: Output of :func:`compute_season_prop_implied_points`.
        lambdas:    Per-position blend weights (default
                    ``SEASON_PROPS_BLEND_LAMBDAS`` — provisional).

    Returns:
        The projections frame with blended points and provenance columns.
    """
    return apply_props_blend(
        proj_df,
        implied_df,
        lambdas=lambdas if lambdas is not None else SEASON_PROPS_BLEND_LAMBDAS,
        points_col="projected_season_points",
        core_markets=SEASON_CORE_MARKETS_BY_POS,
    )
