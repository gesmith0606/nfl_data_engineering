"""Draft-time ADP shrinkage for early-season projections (weeks 1-6).

Hypothesis (see ``.planning/ADP_EARLY_SEASON_GATE.md``): crowd-consensus
draft-time ADP (Fantasy Football Calculator, snapshot late-Aug/early-Sept —
strictly pre-week-1) prices in role changes (rookies, team changes, promoted
starters) faster than our trailing-usage features, which are thin or absent
in weeks 1-6. This module fits a simple log(ADP) -> realized-season-PPG
mapping per position, trained WALK-FORWARD on prior seasons only (season S's
mapping uses ADP+realized-PPG from seasons < S, never season S itself), then
blends a small decaying weight of the ADP-implied PPG into weeks 1-6
projections, mirroring ``early_season_prior.py``'s
``proj' = (1-w)*proj + w*prior`` pattern.

Join key: ADP snapshots carry no ``player_id`` (FFC exposes name/team/
position only), so the join is on ``sleeper_player_map.normalize_name`` +
position — the same hardened name-join helper used by ``adp_sources.py`` and
the live-draft pick-matching code, not a raw name string (see
knowledge-vault ``gated-experiment-coverage-check.md``: "never join on name
alone").

Public API
----------
``load_adp_snapshot(year, scoring_format, source="ffc") -> DataFrame``
``compute_realized_season_ppg(weekly_df, season, scoring_format) -> DataFrame``
``fit_adp_ppg_mapping(training_seasons, weekly_df, scoring_format) -> dict``
``compute_adp_implied_ppg(adp_df, mapping) -> DataFrame``
``apply_adp_prior(proj_df, implied_df, week, scale=1.0) -> DataFrame``
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from scoring_calculator import calculate_fantasy_points_df

# sleeper_player_map.py does `from src import sleeper_http` (an absolute,
# project-root-relative import) — callers of THIS module vary in whether
# they've put the project root on sys.path (e.g. draft_live.py) or only
# src/ (e.g. backtest_projections.py, generate_projections.py, this
# module's own tests). Ensure the project root is importable as the `src`
# package regardless of caller, so `sleeper_player_map` always resolves.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sleeper_player_map import normalize_name  # noqa: E402

#: Decaying blend weight by week — heaviest in week 1 (zero current-season
#: signal), tapering to 0.1 by week 6, and 0 (untouched) outside 1-6.
ADP_PRIOR_WEIGHTS: Dict[int, float] = {1: 0.5, 2: 0.45, 3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}

#: Minimum games played (in the season used as a training *label*) to trust
#: that season's realized PPG as a fitting target — same bar as
#: ``early_season_prior.MIN_PRIOR_GAMES``.
MIN_LABEL_GAMES = 6

#: Minimum pooled (adp, realized_ppg) rows required to fit a position's
#: mapping — below this the regression is noise, so the position is skipped
#: (no-op for that position) rather than fit on too few points.
MIN_TRAINING_ROWS = 5

#: Positions this lever applies to.
ADP_PRIOR_POSITIONS = {"QB", "RB", "WR", "TE"}

_DEFAULT_ADP_HISTORY_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "adp", "history"
)


def load_adp_snapshot(
    year: int,
    scoring_format: str = "half_ppr",
    source: str = "ffc",
    adp_dir: str = _DEFAULT_ADP_HISTORY_DIR,
) -> pd.DataFrame:
    """Load one season's committed ADP history snapshot.

    Args:
        year: Draft season year.
        scoring_format: One of ``"ppr"``, ``"half_ppr"``, ``"standard"``.
        source: ADP source — ``"ffc"`` (primary; FFC's tight late-Aug/
            early-Sept closed-season window) or ``"mfl"`` (robustness check
            only — full-draft-season aggregate, noisier).
        adp_dir: Root of ``data/adp/history/``.

    Returns:
        DataFrame with ``name_key`` (normalize_name join key) added; empty
        (with columns) if the file doesn't exist.
    """
    columns = [
        "season",
        "snapshot_date",
        "source",
        "format",
        "player_name",
        "team",
        "position",
        "adp",
        "name_key",
    ]
    if source == "mfl":
        filename = f"adp_mfl_season_aggregate_{year}.csv"
    else:
        filename = f"adp_{source}_{scoring_format}_{year}.csv"
    path = os.path.join(adp_dir, filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)

    df = pd.read_csv(path)
    if df.empty or "player_name" not in df.columns:
        return pd.DataFrame(columns=columns)
    df["name_key"] = df["player_name"].astype(str).map(normalize_name)
    df["position"] = df["position"].astype(str).str.upper()
    return df


def compute_realized_season_ppg(
    weekly_df: pd.DataFrame,
    season: int,
    scoring_format: str = "half_ppr",
    min_games: int = MIN_LABEL_GAMES,
) -> pd.DataFrame:
    """Per-player realized full-season PPG for ``season``, name-keyed.

    Args:
        weekly_df: Bronze ``players/weekly`` rows spanning at least
            ``season`` (all weeks, all positions).
        season: Season to compute realized PPG for.
        scoring_format: Scoring format key for ``calculate_fantasy_points_df``.
        min_games: Minimum games played to trust the season PPG as a
            training label (matches ``early_season_prior.MIN_PRIOR_GAMES``).

    Returns:
        DataFrame with columns ``name_key``, ``position``, ``realized_ppg``,
        ``games``. Empty (with those columns) on empty/malformed input.
    """
    empty = pd.DataFrame(columns=["name_key", "position", "realized_ppg", "games"])
    if (
        weekly_df is None
        or weekly_df.empty
        or "player_name" not in weekly_df.columns
        or "season" not in weekly_df.columns
    ):
        return empty

    season_df = weekly_df[weekly_df["season"] == season]
    if season_df.empty:
        return empty

    scored = calculate_fantasy_points_df(
        season_df, scoring_format=scoring_format, output_col="_season_game_pts"
    )
    scored["name_key"] = scored["player_name"].astype(str).map(normalize_name)
    scored["position"] = scored["position"].astype(str).str.upper()
    grouped = (
        scored.groupby(["name_key", "position"])["_season_game_pts"]
        .agg(realized_ppg="mean", games="count")
        .reset_index()
    )
    return grouped[grouped["games"] >= min_games].reset_index(drop=True)


def fit_adp_ppg_mapping(
    training_seasons: Iterable[int],
    weekly_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    adp_dir: str = _DEFAULT_ADP_HISTORY_DIR,
    min_training_rows: int = MIN_TRAINING_ROWS,
) -> Dict[str, Dict[str, float]]:
    """Fit a per-position log10(ADP) -> realized-season-PPG linear mapping.

    Pools (adp, realized_ppg) pairs across every season in
    ``training_seasons`` (walk-forward: callers must pass only seasons
    strictly before the eval season — never the eval season itself).

    Args:
        training_seasons: Prior seasons to pool for fitting.
        weekly_df: Bronze weekly rows covering (at least) ``training_seasons``.
        scoring_format: Scoring format key.
        adp_dir: Root of ``data/adp/history/``.
        min_training_rows: Minimum pooled rows per position to fit (below
            this the position is omitted — too few points is noise, not a
            mapping).

    Returns:
        ``{position: {"slope": float, "intercept": float, "n": int}}``.
        Empty dict if no training data is available at all.
    """
    frames: List[pd.DataFrame] = []
    for yr in training_seasons:
        adp = load_adp_snapshot(yr, scoring_format=scoring_format, adp_dir=adp_dir)
        if adp.empty:
            continue
        realized = compute_realized_season_ppg(weekly_df, yr, scoring_format=scoring_format)
        if realized.empty:
            continue
        merged = adp.merge(
            realized[["name_key", "realized_ppg"]], on="name_key", how="inner"
        )
        if not merged.empty:
            frames.append(merged[["position", "adp", "realized_ppg"]])

    if not frames:
        return {}

    pooled = pd.concat(frames, ignore_index=True)
    pooled = pooled[pooled["adp"].notna() & (pooled["adp"] > 0)]

    mapping: Dict[str, Dict[str, float]] = {}
    for pos, grp in pooled.groupby("position"):
        if pos not in ADP_PRIOR_POSITIONS or len(grp) < min_training_rows:
            continue
        log_adp = np.log10(grp["adp"].clip(lower=1.0))
        slope, intercept = np.polyfit(log_adp, grp["realized_ppg"], 1)
        mapping[pos] = {"slope": float(slope), "intercept": float(intercept), "n": int(len(grp))}
    return mapping


def compute_adp_implied_ppg(
    adp_df: pd.DataFrame, mapping: Dict[str, Dict[str, float]]
) -> pd.DataFrame:
    """Apply a fitted mapping to one season's ADP snapshot.

    Args:
        adp_df: Output of :func:`load_adp_snapshot` for the eval season.
        mapping: Output of :func:`fit_adp_ppg_mapping`.

    Returns:
        DataFrame with columns ``name_key``, ``position``, ``adp_implied_ppg``
        (floored at 0 — projected points are never negative). Empty if
        ``adp_df`` or ``mapping`` is empty. Rows whose position has no
        fitted mapping are dropped (not zero-filled).
    """
    empty = pd.DataFrame(columns=["name_key", "position", "adp_implied_ppg"])
    if adp_df is None or adp_df.empty or not mapping:
        return empty

    rows: List[pd.DataFrame] = []
    for pos, coefs in mapping.items():
        sub = adp_df[(adp_df["position"] == pos) & adp_df["adp"].notna() & (adp_df["adp"] > 0)]
        if sub.empty:
            continue
        log_adp = np.log10(sub["adp"].clip(lower=1.0))
        implied = (coefs["slope"] * log_adp + coefs["intercept"]).clip(lower=0.0)
        rows.append(
            pd.DataFrame(
                {
                    "name_key": sub["name_key"].values,
                    "position": pos,
                    "adp_implied_ppg": implied.values,
                }
            )
        )
    if not rows:
        return empty
    return pd.concat(rows, ignore_index=True).drop_duplicates(["name_key", "position"])


def apply_adp_prior(
    proj_df: pd.DataFrame,
    implied_df: pd.DataFrame,
    week: int,
    scale: float = 1.0,
    weight_schedule: Optional[Dict[int, float]] = None,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Blend ``points_col`` toward ADP-implied PPG, weeks 1-6.

    ``proj' = (1-w)*proj + w*adp_implied_ppg`` where
    ``w = scale * weight_schedule.get(week, 0)`` — zero (no-op) outside the
    weight schedule's weeks, for players with no ADP-implied match (name+
    position join miss), and for positions outside
    ``ADP_PRIOR_POSITIONS``.

    Args:
        proj_df: Projections with ``player_name``, ``position``, ``points_col``.
        implied_df: Output of :func:`compute_adp_implied_ppg`.
        week: Current projection week (int).
        scale: Single knob multiplying the fixed weight schedule (default
            1.0 = schedule as-is; 0 disables the blend entirely).
        weight_schedule: Per-week blend weight (default ``ADP_PRIOR_WEIGHTS``).
        points_col: Points column to blend in place.

    Returns:
        ``proj_df`` with ``points_col`` updated and a new
        ``adp_implied_ppg`` provenance column (NaN where unavailable).
    """
    schedule = weight_schedule if weight_schedule is not None else ADP_PRIOR_WEIGHTS
    proj = proj_df.copy()
    proj["adp_implied_ppg"] = float("nan")

    w = schedule.get(week, 0.0) * scale
    if w <= 0:
        return proj
    if (
        implied_df is None
        or implied_df.empty
        or "player_name" not in proj.columns
        or "position" not in proj.columns
    ):
        return proj

    lookup = implied_df.drop_duplicates(["name_key", "position"]).set_index(
        ["name_key", "position"]
    )["adp_implied_ppg"]
    lookup_dict = lookup.to_dict()

    name_keys = proj["player_name"].astype(str).map(normalize_name)
    positions = proj["position"].astype(str).str.upper()
    implied = pd.Series(
        [lookup_dict.get((nk, pos)) for nk, pos in zip(name_keys, positions)],
        index=proj.index,
        dtype="float64",
    )
    proj["adp_implied_ppg"] = implied

    mask = positions.isin(ADP_PRIOR_POSITIONS) & implied.notna()
    if mask.any():
        proj.loc[mask, points_col] = (
            (1.0 - w) * proj.loc[mask, points_col] + w * implied[mask]
        ).round(2)
    return proj
