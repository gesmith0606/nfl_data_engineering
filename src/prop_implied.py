"""Prop-implied projections — market lines → implied stats → fantasy points.

Implements the machinery pre-registered in ``.planning/PROP_IMPLIED_DECISION.md``:
player props are the sharpest per-player consensus available (a pure
FanDuel-prop ranking beat DraftSharks 4.76 vs 4.84 MAE over 13 weeks of 2025),
and per-player market information is the project's largest unused data source.
The RB position is the primary target — it is the one position still losing to
Sleeper consensus (+0.26 matched gap, v4.3 audit).

Named features (memo section "Named features"):

1. ``prop_implied_points`` — de-vig each over/under prop (fair probability from
   the two-way prices), invert the line + fair probability to an implied stat
   mean under a Normal model, take the median across books per market, then
   score the implied stat line through ``scoring_calculator``.
2. ``prop_anchor_gap`` — our projection minus ``prop_implied_points``; the
   "we disagree with the market" signal.

The blend (``proj' = (1−λ)·proj + λ·prop_implied``) ships OFF by default:
``--props-blend`` on ``generate_projections.py`` opts in, and the per-position
lambdas below are PROVISIONAL pending the pre-registered backtest gate
(memo "Backtest plan": SHIP if WR/RB MAE gap improves ≥0.05 or Spearman gap
narrows ≥0.02, no QB/TE regression; KILL if <0.02 everywhere). Sweep the
lambdas in the heuristic lab once Sunday prop snapshots accumulate (Sept+).

Input schema: the Bronze props parquet written by
``scripts/bronze_props_ingestion.py`` (snapshot_ts / bookmaker / market /
player_name / line / price_over / price_under / ...).
"""

import logging
import math
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

try:
    from src.utils import normalize_player_name
    from src.scoring_calculator import calculate_fantasy_points_df
except ImportError:
    from utils import normalize_player_name
    from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

# Over/under prop market -> nflverse stat column it prices.
MARKET_TO_STAT: Dict[str, str] = {
    "player_rush_yds": "rushing_yards",
    "player_reception_yds": "receiving_yards",
    "player_receptions": "receptions",
    "player_pass_yds": "passing_yards",
    "player_pass_tds": "passing_tds",
}

# Binary (yes/no) markets. Anytime-TD converts to an expected TD count via a
# Poisson inversion rather than the Normal line model.
ANYTIME_TD_MARKET = "player_anytime_td"

# Coefficient of variation per market: sigma ≈ CV × mean for the Normal
# inversion of the de-vigged over probability. Values are stat-shape priors
# (yardage props are noisier than receptions; passing yards are the most
# stable). Exact values matter little — with balanced juice the implied mean
# equals the line regardless of CV; CV only scales the adjustment when the
# books shade one side.
MARKET_CV: Dict[str, float] = {
    "player_rush_yds": 0.55,
    "player_reception_yds": 0.60,
    "player_receptions": 0.45,
    "player_pass_yds": 0.25,
    "player_pass_tds": 0.55,
}

# Markets that must be present before a position's projection may be blended —
# a partial stat line (e.g. an RB with only a receptions prop) understates
# implied points and would drag the blend down artificially.
CORE_MARKETS_BY_POS: Dict[str, set] = {
    "QB": {"player_pass_yds"},
    "RB": {"player_rush_yds"},
    "WR": {"player_reception_yds"},
    "TE": {"player_reception_yds"},
}

# PROVISIONAL pre-gate blend weights (memo Step 2 sweeps these properly).
# RB first per the audit; WR secondary. QB/TE stay 0 until the gate shows
# no regression. Only consulted when --props-blend is passed.
PROPS_BLEND_LAMBDAS: Dict[str, float] = {
    "QB": 0.0,
    "RB": 0.5,
    "WR": 0.3,
    "TE": 0.0,
}


def american_to_prob(odds: float) -> float:
    """Convert American odds to the implied (vigged) probability.

    Args:
        odds: American odds (e.g. -110, +150).

    Returns:
        Implied probability in (0, 1); ``nan`` for null/zero input.
    """
    if odds is None or pd.isna(odds) or odds == 0:
        return float("nan")
    odds = float(odds)
    if odds < 0:
        return -odds / (-odds + 100.0)
    return 100.0 / (odds + 100.0)


def devig_two_way(price_over: float, price_under: float) -> float:
    """Return the fair (de-vigged) probability of the Over.

    Standard multiplicative de-vig: normalize the two implied probabilities
    so they sum to 1. Returns ``nan`` when either side is missing — a one-
    sided quote cannot be de-vigged.

    Args:
        price_over: American odds on the Over.
        price_under: American odds on the Under.

    Returns:
        Fair P(over) in (0, 1), or ``nan``.
    """
    p_over = american_to_prob(price_over)
    p_under = american_to_prob(price_under)
    if math.isnan(p_over) or math.isnan(p_under):
        return float("nan")
    total = p_over + p_under
    if total <= 0:
        return float("nan")
    return p_over / total


def implied_mean_from_line(line: float, p_over: float, cv: float) -> float:
    """Invert a prop line + fair over-probability to an implied stat mean.

    Models the stat as Normal(mu, cv·mu). From P(X > line) = p_over:

        (line − mu) / (cv·mu) = Φ⁻¹(1 − p_over)   →   mu = line / (1 − cv·z)

    with z = Φ⁻¹(p_over). With balanced juice (p_over = 0.5, z = 0) the
    implied mean is exactly the line; shading toward the Over raises it.
    z is clamped to [−1, 1] so the denominator stays comfortably positive
    (≥ 0.4 at every MARKET_CV) — extreme one-sided juice on an over/under
    market is a data problem, not signal. The 0.1 floor below is a
    defensive backstop for out-of-range CV values, unreachable today.

    Args:
        line:   The posted over/under line.
        p_over: Fair probability of the Over (de-vigged).
        cv:     Coefficient of variation for the market.

    Returns:
        Implied mean, or ``nan`` on missing inputs.
    """
    if line is None or pd.isna(line) or math.isnan(p_over):
        return float("nan")
    z = float(norm.ppf(min(max(p_over, 0.01), 0.99)))
    z = min(max(z, -1.0), 1.0)
    denom = 1.0 - cv * z
    if denom <= 0.1:
        denom = 0.1
    return float(line) / denom


def implied_td_mean(p_anytime: float) -> float:
    """Convert a fair anytime-TD probability to an expected TD count.

    Poisson inversion: P(N ≥ 1) = 1 − e^(−λ)  →  λ = −ln(1 − p).

    Args:
        p_anytime: Fair probability of scoring at least one TD.

    Returns:
        Expected TDs, or ``nan``.
    """
    if math.isnan(p_anytime) or p_anytime <= 0:
        return float("nan")
    p = min(p_anytime, 0.99)
    return -math.log(1.0 - p)


def compute_prop_implied_points(
    props_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Aggregate a props snapshot into per-player implied fantasy points.

    Per (player, market): de-vig each book's two-way prices, invert to an
    implied stat mean, then take the **median across books** (memo: the
    Unabated method). The per-market implied stats are then scored through
    ``scoring_calculator``. Anytime-TD probability converts to an expected
    TD count credited at the rushing-TD rate (rush and receiving TDs score
    identically in every supported format, so attribution is irrelevant).

    Only the most recent ``snapshot_ts`` per (player, market, bookmaker) is
    used, so a frame concatenated from several capture runs resolves to the
    freshest lines.

    Args:
        props_df:       Bronze props frame (``PROPS_SCHEMA_COLS`` shape).
        scoring_format: Fantasy scoring format for the implied points.

    Returns:
        One row per player: ``name_key``, ``player_name``, implied stat
        columns, ``prop_markets`` (set of markets seen),
        ``prop_market_count`` and ``prop_implied_points``. Empty frame on
        empty/unusable input.
    """
    empty_cols = [
        "name_key",
        "player_name",
        "prop_markets",
        "prop_market_count",
        "prop_implied_points",
    ]
    if props_df is None or props_df.empty:
        return pd.DataFrame(columns=empty_cols)

    df = props_df.copy()
    required = {"market", "player_name", "line", "price_over", "price_under"}
    if not required.issubset(df.columns):
        logger.warning(
            "Props frame missing required columns %s — skipping",
            required - set(df.columns),
        )
        return pd.DataFrame(columns=empty_cols)

    # Freshest quote per (player, market, book).
    if "snapshot_ts" in df.columns:
        df = df.sort_values("snapshot_ts").drop_duplicates(
            subset=["player_name", "market", "bookmaker"], keep="last"
        )

    df["name_key"] = df["player_name"].map(normalize_player_name)

    rows = []
    for (name_key, market), group in df.groupby(["name_key", "market"]):
        if market == ANYTIME_TD_MARKET:
            # Binary market: price_over carries the "yes" price. Without a
            # "no" price to de-vig against, apply a flat vig haircut typical
            # of anytime-TD boards (~7%).
            probs = group["price_over"].map(american_to_prob) * 0.93
            means = probs.map(implied_td_mean)
            stat = "rushing_tds"
        elif market in MARKET_TO_STAT:
            cv = MARKET_CV.get(market, 0.5)
            p_fair = group.apply(
                lambda r: devig_two_way(r["price_over"], r["price_under"]),
                axis=1,
            )
            means = pd.Series(
                [
                    implied_mean_from_line(line, p, cv)
                    for line, p in zip(group["line"], p_fair)
                ],
                index=group.index,
            )
            stat = MARKET_TO_STAT[market]
        else:
            continue

        med = means.dropna().median()
        if pd.isna(med):
            continue
        rows.append(
            {
                "name_key": name_key,
                "player_name": group["player_name"].iloc[0],
                "market": market,
                "stat": stat,
                "implied": round(float(med), 2),
            }
        )

    if not rows:
        return pd.DataFrame(columns=empty_cols)

    long = pd.DataFrame(rows)

    # Invariant guard: each (player, stat) must appear once — two markets
    # mapping to the same stat column would otherwise double-count. Not
    # currently possible with MARKET_TO_STAT, but fail loudly rather than
    # silently sum if the mapping ever grows a collision.
    dup_stats = long.duplicated(subset=["name_key", "stat"])
    if dup_stats.any():
        logger.warning(
            "Duplicate (player, stat) implied entries from markets %s — "
            "keeping first per player",
            sorted(long.loc[dup_stats, "market"].unique()),
        )
        long = long[~dup_stats]

    # Pivot on name_key ONLY. Books spell the same player differently
    # ("AJ Brown" vs "A.J. Brown"); indexing on the raw player_name split
    # one player into per-spelling rows, and the blend join then silently
    # used whichever partial row drop_duplicates kept.
    wide = long.pivot_table(
        index="name_key",
        columns="stat",
        values="implied",
        aggfunc="first",
    ).reset_index()
    name_lookup = long.groupby("name_key")["player_name"].first()
    wide.insert(1, "player_name", wide["name_key"].map(name_lookup))
    markets_per_player = long.groupby("name_key")["market"].agg(set)
    wide["prop_markets"] = wide["name_key"].map(markets_per_player)
    wide["prop_market_count"] = wide["prop_markets"].map(len)

    scored = calculate_fantasy_points_df(
        wide.copy(), scoring_format=scoring_format, output_col="_pts"
    )
    wide["prop_implied_points"] = scored["_pts"].clip(lower=0.0).round(2)
    return wide


def apply_props_blend(
    proj_df: pd.DataFrame,
    implied_df: pd.DataFrame,
    lambdas: Optional[Dict[str, float]] = None,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Blend projections toward prop-implied points, per position.

    ``proj' = (1−λ)·proj + λ·prop_implied_points`` for players whose props
    coverage includes the position's core market(s); everyone else keeps the
    pure model (memo: coverage is concentrated in exactly the high-volume
    players where the consensus losses live). Adds provenance columns
    ``prop_implied_points`` and ``prop_anchor_gap`` (model − market, computed
    pre-blend — the research metric per the memo's self-reference caveat).

    Args:
        proj_df:    Weekly projections with ``player_name``, ``position``
                    and ``points_col``.
        implied_df: Output of :func:`compute_prop_implied_points`.
        lambdas:    Per-position blend weights (default
                    ``PROPS_BLEND_LAMBDAS`` — provisional, pre-gate).
        points_col: Points column to blend in place.

    Returns:
        The projections frame with blended points and provenance columns.
    """
    lambdas = lambdas if lambdas is not None else PROPS_BLEND_LAMBDAS
    proj = proj_df.copy()
    proj["prop_implied_points"] = np.nan
    proj["prop_anchor_gap"] = np.nan
    if implied_df is None or implied_df.empty:
        return proj

    lookup = implied_df.drop_duplicates("name_key").set_index("name_key")
    keys = proj["player_name"].map(normalize_player_name)
    implied = keys.map(lookup["prop_implied_points"])
    markets = keys.map(lookup["prop_markets"])

    proj["prop_implied_points"] = implied
    proj["prop_anchor_gap"] = (proj[points_col] - implied).round(2)

    blended_total = 0
    for pos, lam in lambdas.items():
        if lam <= 0:
            continue
        core = CORE_MARKETS_BY_POS.get(pos, set())
        coverage_ok = markets.map(lambda m: isinstance(m, set) and core.issubset(m))
        mask = (proj["position"] == pos) & implied.notna() & coverage_ok
        if not mask.any():
            continue
        proj.loc[mask, points_col] = (
            (1.0 - lam) * proj.loc[mask, points_col] + lam * implied[mask]
        ).round(2)
        blended_total += int(mask.sum())
        logger.info(
            "Props blend applied to %d %s projections (lambda %.2f)",
            int(mask.sum()),
            pos,
            lam,
        )
    if blended_total == 0:
        logger.info("Props blend: no eligible players (coverage/position gates)")
    return proj
