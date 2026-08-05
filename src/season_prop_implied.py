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

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm, poisson

try:
    from src.prop_implied import (
        american_to_prob,
        apply_props_blend,
        compute_prop_implied_points,
    )
    from src.utils import normalize_player_name
except ImportError:
    from prop_implied import (
        american_to_prob,
        apply_props_blend,
        compute_prop_implied_points,
    )
    from utils import normalize_player_name

logger = logging.getLogger(__name__)

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

# Rookie Milestones ladder markets -> the season O/U market they price.
# Implied rows are recorded under the SEASON key so the coverage gate and
# the (player, stat) dedup treat rookie-derived stats identically; the
# two-way O/U number wins whenever both exist for a player (sharper —
# milestone ladders carry full one-sided vig on every rung).
ROOKIE_TO_SEASON_MARKET: Dict[str, str] = {
    "rookie_pass_yds": "season_pass_yds",
    "rookie_pass_tds": "season_pass_tds",
    "rookie_rush_yds": "season_rush_yds",
    "rookie_rush_tds": "season_rush_tds",
    "rookie_rec_yds": "season_rec_yds",
    "rookie_rec_tds": "season_rec_tds",
}

# Flat vig haircut on one-sided milestone prices — same convention as the
# weekly module's anytime-TD handling (~7% typical one-sided juice).
MILESTONE_VIG_HAIRCUT = 0.93

# Stats fitted with a Poisson ladder (low-count TD totals); everything
# else uses the Normal(mu, cv*mu) model shared with the O/U inversion.
COUNT_STATS = frozenset({"passing_tds", "rushing_tds", "receiving_tds"})


def invert_milestone_ladder(
    thresholds: List[float],
    fair_probs: List[float],
    cv: float,
    count: bool = False,
) -> Optional[float]:
    """Fit an implied mean through a ladder of exceedance probabilities.

    Given fair P(X >= t_i) for milestone thresholds t_i, finds the single
    mean that best explains the ladder under the market's distribution
    model — Normal(mu, cv*mu) for yardage, Poisson(mu) for TD counts —
    by minimising squared error in probability space.

    Args:
        thresholds: Milestone thresholds (e.g. [750, 1000, 1250]).
        fair_probs: De-vigged P(X >= threshold) per rung, same order.
        cv: Coefficient of variation for the Normal model (ignored for
            Poisson).
        count: Fit a Poisson instead of a Normal (TD-count ladders).

    Returns:
        Implied mean, or None when no usable rungs exist or the fit
        degenerates.
    """
    pairs = [
        (t, p)
        for t, p in zip(thresholds, fair_probs)
        if t is not None and p is not None and not np.isnan(p) and 0.0 < p < 1.0
    ]
    if not pairs:
        return None
    ts = np.array([t for t, _ in pairs], dtype=float)
    ps = np.array([p for _, p in pairs], dtype=float)

    if count:

        def sse(mu: float) -> float:
            model = poisson.sf(ts - 1, mu)  # P(N >= t)
            return float(((model - ps) ** 2).sum())

    else:

        def sse(mu: float) -> float:
            sigma = max(cv * mu, 1e-6)
            model = norm.sf(ts, loc=mu, scale=sigma)  # P(X >= t)
            return float(((model - ps) ** 2).sum())

    # Mean is bracketed well inside [~0, 2x top rung]: a mean above the
    # highest threshold would imply P >= 50% at that rung, which longshot
    # ladder prices never show.
    result = minimize_scalar(
        sse, bounds=(1e-3, float(ts.max()) * 2.0), method="bounded"
    )
    if not result.success or not np.isfinite(result.x):
        return None
    return float(result.x)


def compute_rookie_milestone_implied(
    milestone_df: pd.DataFrame,
) -> pd.DataFrame:
    """Convert rookie milestone ladder rows into implied season stats.

    Per (player, market): de-vig each rung's one-sided price with the flat
    ``MILESTONE_VIG_HAIRCUT``, then fit the implied mean through the
    ladder via :func:`invert_milestone_ladder`.

    Args:
        milestone_df: Bronze rows whose ``market`` is in
            ``ROOKIE_TO_SEASON_MARKET`` (one row per threshold rung).

    Returns:
        Long frame with columns ``name_key`` / ``player_name`` /
        ``market`` (mapped to the season key) / ``stat`` / ``implied``.
        Empty frame when no ladders are fittable.
    """
    cols = ["name_key", "player_name", "market", "stat", "implied"]
    if milestone_df is None or milestone_df.empty:
        return pd.DataFrame(columns=cols)

    df = milestone_df[milestone_df["market"].isin(ROOKIE_TO_SEASON_MARKET)].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)

    if "snapshot_ts" in df.columns:
        df = df.sort_values("snapshot_ts").drop_duplicates(
            subset=["player_name", "market", "bookmaker", "line"], keep="last"
        )
    df["name_key"] = df["player_name"].map(normalize_player_name)

    rows = []
    for (name_key, market), group in df.groupby(["name_key", "market"]):
        season_market = ROOKIE_TO_SEASON_MARKET[market]
        stat = SEASON_MARKET_TO_STAT[season_market]
        fair = [
            american_to_prob(p) * MILESTONE_VIG_HAIRCUT for p in group["price_over"]
        ]
        implied = invert_milestone_ladder(
            list(group["line"]),
            fair,
            cv=SEASON_MARKET_CV[season_market],
            count=stat in COUNT_STATS,
        )
        if implied is None:
            logger.warning(
                "Milestone ladder unfittable for %s / %s — skipping",
                group["player_name"].iloc[0],
                market,
            )
            continue
        rows.append(
            {
                "name_key": name_key,
                "player_name": group["player_name"].iloc[0],
                "market": season_market,
                "stat": stat,
                "implied": round(implied, 2),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def compute_season_prop_implied_points(
    season_props_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Aggregate a season-props snapshot into implied season fantasy points.

    Two-way O/U markets go through
    :func:`prop_implied.compute_prop_implied_points` with the season
    market/CV maps; rookie milestone ladders go through
    :func:`compute_rookie_milestone_implied` and fill in stats/players the
    O/U markets do not cover (the O/U number wins any overlap — it is the
    sharper quote). The output ``prop_implied_points`` column is on the
    season-total scale (matches ``projected_season_points``).

    Args:
        season_props_df: Bronze season-props frame
            (``SEASON_PROPS_SCHEMA_COLS`` shape), O/U and milestone rows
            mixed.
        scoring_format:  Fantasy scoring format for the implied points.

    Returns:
        One row per player with implied season stats, ``prop_markets``,
        ``prop_market_count`` and ``prop_implied_points``.
    """
    try:
        from src.scoring_calculator import calculate_fantasy_points_df
    except ImportError:
        from scoring_calculator import calculate_fantasy_points_df

    if season_props_df is None or season_props_df.empty:
        return compute_prop_implied_points(
            season_props_df,
            scoring_format=scoring_format,
            market_to_stat=SEASON_MARKET_TO_STAT,
            market_cv=SEASON_MARKET_CV,
        )

    is_milestone = season_props_df["market"].isin(ROOKIE_TO_SEASON_MARKET)
    wide = compute_prop_implied_points(
        season_props_df[~is_milestone],
        scoring_format=scoring_format,
        market_to_stat=SEASON_MARKET_TO_STAT,
        market_cv=SEASON_MARKET_CV,
    )
    long_ms = compute_rookie_milestone_implied(season_props_df[is_milestone])
    if long_ms.empty:
        return wide

    wide_ms = long_ms.pivot_table(
        index="name_key", columns="stat", values="implied", aggfunc="first"
    ).reset_index()
    name_lookup = long_ms.groupby("name_key")["player_name"].first()
    wide_ms.insert(1, "player_name", wide_ms["name_key"].map(name_lookup))
    markets_ms = long_ms.groupby("name_key")["market"].agg(set)

    if wide.empty:
        merged = wide_ms.set_index("name_key")
        merged["prop_markets"] = merged.index.map(markets_ms)
    else:
        # O/U values win any (player, stat) overlap; milestone rows fill
        # the gaps and contribute rookie-only players.
        merged = wide.set_index("name_key").combine_first(wide_ms.set_index("name_key"))
        # combine_first cannot union the set-valued markets column — do it
        # explicitly (players present in both sources get the union).
        ou_markets = wide.set_index("name_key")["prop_markets"]
        merged["prop_markets"] = [
            (ou_markets.get(k) or set()) | (markets_ms.get(k) or set())
            for k in merged.index
        ]

    merged = merged.reset_index()
    merged["prop_market_count"] = merged["prop_markets"].map(len)
    scored = calculate_fantasy_points_df(
        merged.copy(), scoring_format=scoring_format, output_col="_pts"
    )
    merged["prop_implied_points"] = scored["_pts"].clip(lower=0.0).round(2)
    return merged


def latest_season_props_path(season: int, project_root: str) -> Optional[str]:
    """Return the newest Bronze season-props parquet for a season, or None.

    Args:
        season: NFL season year.
        project_root: Absolute path of the repo root.

    Returns:
        Path string of the latest ``season_props_*.parquet``, or None when
        no snapshot exists.
    """
    import glob
    import os

    files = sorted(
        glob.glob(
            os.path.join(
                project_root,
                "data",
                "bronze",
                "dk",
                "season_props",
                f"season={season}",
                "season_props_*.parquet",
            )
        )
    )
    return files[-1] if files else None


def attach_market_columns(
    proj_df: pd.DataFrame,
    season: int,
    project_root: str,
    scoring_format: str = "half_ppr",
    points_col: str = "projected_season_points",
) -> Tuple[pd.DataFrame, int]:
    """Attach market provenance columns WITHOUT blending the projections.

    Loads the latest Bronze season-props snapshot and adds
    ``prop_implied_points`` (market's implied season total) and
    ``prop_anchor_gap`` (model − market) so downstream consumers — the
    draft assistant board in particular — can flag players where the model
    and the market disagree. Projections themselves are untouched.

    Args:
        proj_df:        Projections with ``player_name`` and ``points_col``.
        season:         NFL season year (snapshot partition).
        project_root:   Absolute repo root path.
        scoring_format: Fantasy scoring format for implied points.
        points_col:     Season-total points column for the gap.

    Returns:
        Tuple of (frame with the two columns attached, count of players
        matched to a market number). The input frame is returned unchanged
        (plus empty columns) when no snapshot exists.
    """
    proj = proj_df.copy()
    proj["prop_implied_points"] = np.nan
    proj["prop_anchor_gap"] = np.nan

    path = latest_season_props_path(season, project_root)
    if path is None or points_col not in proj.columns:
        return proj, 0

    implied = compute_season_prop_implied_points(
        pd.read_parquet(path), scoring_format=scoring_format
    )
    if implied.empty:
        return proj, 0

    lookup = implied.drop_duplicates("name_key").set_index("name_key")
    keys = proj["player_name"].map(normalize_player_name)
    proj["prop_implied_points"] = keys.map(lookup["prop_implied_points"])
    proj["prop_anchor_gap"] = (proj[points_col] - proj["prop_implied_points"]).round(2)
    return proj, int(proj["prop_implied_points"].notna().sum())


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
