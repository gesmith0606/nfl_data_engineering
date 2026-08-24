"""Draft value engine — VALUE / BUST / BREAKOUT / DEEP-SLEEPER labels with reasons.

Implements the codable rules of ``docs/DRAFT_DOCTRINE.md`` (rule numbers cited
inline) on top of an enriched board (:func:`src.draft_optimizer.compute_value_scores`
output: ``model_rank``, ``adp_rank``, ``vorp``, ``position``, stat columns).

Feature sources (all local-first, every one optional — a missing source only
disables the rules that need it, never raises):

* Sleeper player registry (``data/bronze/players/sleeper_players.json``) →
  ``age`` (at Sept 1 of the season), ``years_exp``.
* Silver weekly usage for season N-1 → prior-year games, targets, TDs, target
  share, positional finish.
* UC1 vacated-opportunity features (``src.graph_vacated_opportunity``) →
  ``vacancy_absorbed_share`` / ``net_target_vacancy``.
* The projection stat line → TD share of projected points.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:  # importable as ``src.draft_value`` and bare ``draft_value``
    from src.draft_optimizer import name_key
except ImportError:  # pragma: no cover
    from draft_optimizer import name_key

logger = logging.getLogger(__name__)

# Doctrine thresholds (docs/DRAFT_DOCTRINE.md)
VALUE_GAP = 12          # §10/§29: model rank >= 1 round ahead of ADP
INFLATION_GAP = 12      # §27: ADP >= 1 round ahead of model rank
RB_AGE_CLIFF = 27       # §20
TD_SHARE_MAX = 0.35     # §22 proxy: TD-dependent scorer
DEEP_SLEEPER_ADP = 100  # §29: deep sleeper = ADP > 100 with a startable ceiling
CEILING_RANK = {"QB": 12, "TE": 12, "RB": 24, "WR": 24}
VACANCY_MIN = 0.10      # §31: meaningful vacated-opportunity share
ADP_MAX_PRICED = 200    # ADP beyond this = undrafted-pool artifact, not a price
STARTABLE_MULT = 2      # breakout/sleeper candidates must rank within 2x the startable range
POS_TD_REGRESSION_TARGETS = 50  # §34
POS_TD_REGRESSION_TDS = 5

_REGISTRY = os.path.join("data", "bronze", "players", "sleeper_players.json")
_USAGE_GLOB = os.path.join("data", "silver", "players", "usage", "season={season}", "*.parquet")


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """Numeric column as a Series aligned to ``df`` (all-NaN when absent) —
    ``df.get(col)`` returns None/scalars for missing columns and breaks ``.fillna``."""
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype=float)


# ---------------------------------------------------------------------------
# Feature loaders
# ---------------------------------------------------------------------------


def _age_on(birth: str, season: int) -> Optional[float]:
    try:
        y, m, d = (int(x) for x in str(birth)[:10].split("-"))
        b = date(y, m, d)
    except Exception:  # noqa: BLE001
        return None
    ref = date(season, 9, 1)
    return round((ref - b).days / 365.25, 1)


def load_registry_features(season: int, path: str = _REGISTRY) -> pd.DataFrame:
    """Age at Sept 1 of ``season`` + years_exp per player (Sleeper registry).

    Returns columns ``gsis_id, _name_key, position, age, years_exp`` — empty
    frame when the registry cache is absent.
    """
    if not os.path.exists(path):
        logger.warning("Sleeper registry not found at %s — age/exp rules disabled", path)
        return pd.DataFrame(columns=["gsis_id", "_name_key", "position", "age", "years_exp"])
    with open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    rows = []
    for rec in reg.values():
        if not isinstance(rec, dict) or not rec.get("full_name"):
            continue
        pos = str(rec.get("position") or "").upper()
        if pos not in {"QB", "RB", "WR", "TE", "K"}:
            continue
        rows.append(
            {
                "gsis_id": rec.get("gsis_id"),
                "_name_key": name_key(rec.get("full_name")),
                "position": pos,
                "age": _age_on(rec.get("birth_date"), season),
                "years_exp": rec.get("years_exp"),
            }
        )
    df = pd.DataFrame(rows)
    # Active players first so a name collision resolves to the current one.
    return df.drop_duplicates(["_name_key", "position"], keep="first")


def load_prior_usage(season: int) -> pd.DataFrame:
    """Season ``season - 1`` actuals per player from Silver weekly usage.

    Returns ``player_id, prior_games, prior_targets, prior_receptions,
    prior_tds, prior_target_share, prior_points, prior_pos_rank`` (rank by
    half-PPR points within position). Empty frame when the season is missing.
    """
    files = sorted(glob.glob(_USAGE_GLOB.format(season=season - 1)))
    if not files:
        return pd.DataFrame(columns=["player_id"])
    df = pd.read_parquet(files[-1])
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    need = {"player_id", "position", "fantasy_points", "receptions"}
    if not need <= set(df.columns):
        return pd.DataFrame(columns=["player_id"])
    df = df.copy()
    df["half_ppr"] = df["fantasy_points"].fillna(0) + 0.5 * df["receptions"].fillna(0)
    df["tds"] = _num(df, "rushing_tds").fillna(0) + _num(df, "receiving_tds").fillna(0)
    agg = (
        df.groupby(["player_id", "position"])
        .agg(
            prior_games=("week", "nunique"),
            prior_targets=("targets", "sum"),
            prior_receptions=("receptions", "sum"),
            prior_tds=("tds", "sum"),
            prior_target_share=("target_share", "mean"),
            prior_points=("half_ppr", "sum"),
        )
        .reset_index()
    )
    agg["prior_pos_rank"] = (
        agg.groupby("position")["prior_points"].rank(ascending=False, method="first").astype(int)
    )
    return agg.drop(columns=["position"])


def load_vacancy(season: int) -> pd.DataFrame:
    """UC1 vacated-opportunity features keyed by ``player_id`` (empty on any failure)."""
    try:
        from src.graph_vacated_opportunity import build_vacated_opportunity_data
    except ImportError:  # pragma: no cover
        from graph_vacated_opportunity import build_vacated_opportunity_data
    try:
        df = build_vacated_opportunity_data(season)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vacated-opportunity features unavailable: %s", exc)
        return pd.DataFrame(columns=["player_id"])
    keep = [c for c in ("player_id", "vacancy_absorbed_share", "net_target_vacancy", "net_carry_vacancy") if c in df.columns]
    return df[keep].drop_duplicates("player_id") if keep else pd.DataFrame(columns=["player_id"])


def td_share(df: pd.DataFrame) -> pd.Series:
    """Share of projected points that comes from touchdowns (standard weights)."""
    pts = _num(df, "projected_season_points")
    td_pts = (
        6 * _num(df, "rushing_tds").fillna(0)
        + 6 * _num(df, "receiving_tds").fillna(0)
        + 4 * _num(df, "passing_tds").fillna(0)
    )
    return (td_pts / pts.replace(0, np.nan)).round(3)


# ---------------------------------------------------------------------------
# Labeling
# ---------------------------------------------------------------------------


def attach_features(board: pd.DataFrame, season: int) -> pd.DataFrame:
    """Join age/exp, prior-year usage, vacancy and TD share onto a board frame."""
    df = board.copy()
    df["_name_key"] = df["player_name"].map(name_key)
    reg = load_registry_features(season)
    if not reg.empty:
        df = df.merge(reg.drop(columns=["gsis_id"]), on=["_name_key", "position"], how="left")
    else:
        df["age"] = np.nan
        df["years_exp"] = np.nan
    if "player_id" in df.columns:
        prior = load_prior_usage(season)
        if not prior.empty:
            df = df.merge(prior, on="player_id", how="left")
        vac = load_vacancy(season)
        if not vac.empty:
            df = df.merge(vac, on="player_id", how="left")
    for c in ("prior_games", "prior_targets", "prior_tds", "prior_target_share", "prior_points",
              "prior_pos_rank", "vacancy_absorbed_share", "net_target_vacancy", "net_carry_vacancy"):
        if c not in df.columns:
            df[c] = np.nan
    df["td_share"] = td_share(df)
    return df.drop(columns=["_name_key"])


def label_board(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``flag_value / flag_bust / flag_breakout / flag_deep_sleeper``,
    ``bust_score / breakout_score`` and a ``reasons`` string citing doctrine rules.

    Expects the columns produced by :func:`attach_features` on top of
    ``compute_value_scores`` output. Missing inputs simply don't fire.
    """
    out = df.copy()
    pos = out["position"].astype(str).str.upper()
    # Value is POSITIONAL (§1): compare ADP with the VBD board (rank by VORP),
    # not the raw-points rank — otherwise every QB looks like a "value" because
    # QBs score the most raw points. K/DST never enter the value board.
    vorp = _num(out, "vorp").where(~pos.isin(["K", "DST"]))
    out["vbd_rank"] = vorp.rank(ascending=False, method="first")
    # ADP feeds mark undrafted players with 300+ — that is "nobody drafts him",
    # not a price. Treat as unpriced.
    adp = _num(out, "adp_rank")
    adp = adp.where(adp <= ADP_MAX_PRICED)
    gap = adp - out["vbd_rank"]
    out["adp_gap"] = gap.round(0)
    age = _num(out, "age")
    exp = _num(out, "years_exp")
    pos_rank = out["position_rank"] if "position_rank" in out.columns else (
        out.groupby("position")["model_rank"].rank(method="first")
    )
    reasons: List[List[str]] = [[] for _ in range(len(out))]

    def add(mask: pd.Series, text: str) -> pd.Series:
        m = mask.fillna(False).astype(bool)
        for i in np.flatnonzero(m.to_numpy()):
            reasons[i].append(text)
        return m

    # --- VALUE (§10)
    value = add(gap >= VALUE_GAP, "§10 value: model rank ≥1 round ahead of ADP")

    # --- BUST signals (§20-§28)
    bust_score = pd.Series(0, index=out.index)
    bust_score += add(gap <= -INFLATION_GAP, "§27 ADP inflation: market ≥1 round ahead of model").astype(int)
    bust_score += add((pos == "RB") & (age >= RB_AGE_CLIFF), f"§20 RB age cliff (age ≥{RB_AGE_CLIFF})").astype(int)
    # Back-test 2021-25 (scripts/backtest_draft_flags.py): prior top-5 raises bust
    # rate only for RBs (46% vs 34%); for WR/QB/TE it does not -> RB-only signal.
    bust_score += add((pos == "RB") & (_num(out, "prior_pos_rank") <= 5), "§21 RB top-5 finish last year (repeat ~24%)").astype(int)
    # The crude "TD share of projected points" proxy showed NO bust lift in the
    # back-test (0.83) — tagged for information only, not scored. A real xTD
    # (expected-TD) gap is the doctrine's actual §22 signal; not built yet.
    add(_num(out, "td_share") > TD_SHARE_MAX, f"(info) TD-dependent: >{int(TD_SHARE_MAX*100)}% of points from TDs")
    if "is_low_sample_projection" in out.columns:
        bust_score += add(out["is_low_sample_projection"].fillna(False).astype(bool), "§28 low-sample projection").astype(int)
    out["bust_score"] = bust_score
    # Bust = ADP inflation plus at least one more signal, or ≥3 signals total.
    bust = ((gap <= -INFLATION_GAP) & (bust_score >= 2)) | (bust_score >= 3)

    # --- BREAKOUT / SLEEPER signals (§29-§35)
    breakout_score = pd.Series(0, index=out.index)
    young = (exp >= 1) & (exp <= 3)
    vac = _num(out, "vacancy_absorbed_share").fillna(0)
    ntv = _num(out, "net_target_vacancy").fillna(0)
    ncv = _num(out, "net_carry_vacancy").fillna(0)
    opportunity = (vac >= VACANCY_MIN) | (ntv >= VACANCY_MIN) | (ncv >= VACANCY_MIN)
    breakout_score += add(young & opportunity, "§30/§31 years 2-4 + vacated opportunity").astype(int)
    breakout_score += add((exp == 0) & opportunity, "§30 rookie stepping into vacated role").astype(int)
    breakout_score += add(young & (gap >= 6), "§29 young player the model likes more than the market").astype(int)
    breakout_score += add(
        pos.isin(["WR", "TE"])
        & (_num(out, "prior_targets") >= POS_TD_REGRESSION_TARGETS)
        & (_num(out, "prior_tds") < POS_TD_REGRESSION_TDS),
        "§34 positive TD regression (≥50 targets, <5 TDs last year)",
    ).astype(int)
    out["breakout_score"] = breakout_score
    ceiling = pos.map(CEILING_RANK).fillna(24)
    startable = (pos_rank <= ceiling * STARTABLE_MULT) & ~pos.isin(["K", "DST"])
    breakout = (breakout_score >= 1) & startable

    deep = add(
        (adp > DEEP_SLEEPER_ADP) & (pos_rank <= ceiling) & ~pos.isin(["K", "DST"]),
        "§29 deep sleeper: ADP >100 with a startable model rank",
    )

    out["flag_value"] = value
    out["flag_bust"] = bust
    out["flag_breakout"] = breakout
    out["flag_deep_sleeper"] = deep
    out["reasons"] = ["; ".join(r) for r in reasons]
    return out


def summarize(labeled: pd.DataFrame, top: int = 8) -> Dict[str, pd.DataFrame]:
    """Top-N tables per label for reporting (sorted by VORP / gap as appropriate)."""
    cols = [c for c in ("player_name", "position", "recent_team", "vbd_rank", "adp_rank", "adp_gap",
                        "projected_season_points", "vorp", "age", "years_exp", "td_share", "reasons") if c in labeled.columns]
    lab = labeled.copy()
    lab["reasons"] = lab["reasons"].str.slice(0, 95)
    v = lab[lab["flag_value"]].sort_values("vorp", ascending=False).head(top)
    b = lab[lab["flag_bust"]].sort_values("adp_rank").head(top)
    br = lab[lab["flag_breakout"] & ~lab["flag_bust"]].sort_values(["breakout_score", "vorp"], ascending=False).head(top)
    d = lab[lab["flag_deep_sleeper"]].sort_values("vorp", ascending=False).head(top)
    return {"values": v[cols], "busts": b[cols], "breakouts": br[cols], "deep_sleepers": d[cols]}


__all__ = [
    "attach_features",
    "label_board",
    "summarize",
    "load_registry_features",
    "load_prior_usage",
    "load_vacancy",
    "td_share",
]
