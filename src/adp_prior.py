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
position only) — CAUGHT LIVE (2026-08-18) doing this the naive way: Bronze
``players/weekly``'s ``player_name`` column is ABBREVIATED (e.g.
``"T.Brady"``; see ``backtest_projections.compute_actuals``'s docstring),
and so is our own PROJECTIONS output's ``player_name`` column — joining
either of those against ADP's full names ("Tom Brady") on name alone is a
structural 0%-match no-op (confirmed: it silently produced a byte-identical
treated/baseline backtest). The fix used here: resolve ADP's full names to
``player_id`` ONCE via a name+position crosswalk built from Bronze
``players/rosters`` (which — unlike ``players/weekly`` — carries FULL names
alongside ``player_id``, and covers pre-debut rookies since it's a
season-roster snapshot, not per-game participation). Every other join in
this module (realized-PPG training labels, and the final blend into
projections) is by ``player_id``, never by name — matching the repo's
hardened-join precedent (``early_season_prior.py``,
``knowledge-vault/concepts/gated-experiment-coverage-check.md``: "never
join on name alone; prefer real ids").

Public API
----------
``load_adp_snapshot(year, scoring_format, source="ffc") -> DataFrame``
``build_name_id_crosswalk(rosters_df) -> DataFrame``
``compute_realized_season_ppg(weekly_df, season, scoring_format) -> DataFrame``
``fit_adp_ppg_mapping(training_seasons, weekly_df, crosswalk, scoring_format) -> dict``
``compute_adp_implied_ppg(adp_df, mapping, crosswalk) -> DataFrame``
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


def build_name_id_crosswalk(rosters_df: pd.DataFrame) -> pd.DataFrame:
    """Build a (normalized name, position) -> player_id lookup from rosters.

    Uses Bronze ``players/rosters`` (NOT ``players/weekly`` — that source's
    ``player_name`` is abbreviated, e.g. ``"T.Brady"``; rosters carries the
    full name FFC's ADP data uses, and covers players before their season
    debut since it's a roster snapshot, not per-game participation).

    Args:
        rosters_df: Bronze ``players/rosters`` rows (one or more seasons
            pooled — a player's (name, position) is effectively stable
            across seasons, so pooling is safe and avoids needing a
            separate crosswalk per season).

    Returns:
        DataFrame with columns ``name_key``, ``position``, ``player_id``,
        deduplicated (last row wins on a rare (name, position) collision).
        Empty (with columns) on empty/malformed input.
    """
    empty = pd.DataFrame(columns=["name_key", "position", "player_id"])
    if rosters_df is None or rosters_df.empty:
        return empty
    if not {"player_name", "position", "player_id"}.issubset(rosters_df.columns):
        return empty

    out = pd.DataFrame(
        {
            "name_key": rosters_df["player_name"].astype(str).map(normalize_name),
            "position": rosters_df["position"].astype(str).str.upper(),
            "player_id": rosters_df["player_id"].astype(str),
        }
    )
    out = out[out["name_key"] != ""]
    return out.drop_duplicates(["name_key", "position"], keep="last").reset_index(drop=True)


def resolve_adp_player_ids(adp_df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Attach ``player_id`` to an ADP snapshot via the (name_key, position) crosswalk.

    Rows without a crosswalk match are dropped (not zero-filled) — an
    unresolved ADP row simply never fires the lever for that player, which
    is what the coverage/firing-rate report is meant to surface.

    Args:
        adp_df: Output of :func:`load_adp_snapshot`.
        crosswalk: Output of :func:`build_name_id_crosswalk`.

    Returns:
        ``adp_df`` inner-joined with ``player_id``; empty if either input
        is empty.
    """
    if adp_df is None or adp_df.empty or crosswalk is None or crosswalk.empty:
        return pd.DataFrame()
    return adp_df.merge(crosswalk[["name_key", "position", "player_id"]], on=["name_key", "position"], how="inner")


def compute_realized_season_ppg(
    weekly_df: pd.DataFrame,
    season: int,
    scoring_format: str = "half_ppr",
    min_games: int = MIN_LABEL_GAMES,
) -> pd.DataFrame:
    """Per-player realized full-season PPG for ``season``, keyed by ``player_id``.

    Mirrors ``early_season_prior.compute_prior_season_ppg`` exactly (same
    player_id-based grouping, same min-games gate) — no name matching
    involved, since Bronze weekly's own ``player_id`` is reliable.

    Args:
        weekly_df: Bronze ``players/weekly`` rows spanning at least
            ``season`` (all weeks, all positions).
        season: Season to compute realized PPG for.
        scoring_format: Scoring format key for ``calculate_fantasy_points_df``.
        min_games: Minimum games played to trust the season PPG as a
            training label.

    Returns:
        DataFrame with columns ``player_id``, ``position``, ``realized_ppg``,
        ``games``. Empty (with those columns) on empty/malformed input.
    """
    empty = pd.DataFrame(columns=["player_id", "position", "realized_ppg", "games"])
    if (
        weekly_df is None
        or weekly_df.empty
        or "player_id" not in weekly_df.columns
        or "season" not in weekly_df.columns
    ):
        return empty

    season_df = weekly_df[weekly_df["season"] == season]
    if season_df.empty:
        return empty

    scored = calculate_fantasy_points_df(
        season_df, scoring_format=scoring_format, output_col="_season_game_pts"
    )
    scored["position"] = scored["position"].astype(str).str.upper()
    scored["player_id"] = scored["player_id"].astype(str)
    grouped = (
        scored.groupby(["player_id", "position"])["_season_game_pts"]
        .agg(realized_ppg="mean", games="count")
        .reset_index()
    )
    return grouped[grouped["games"] >= min_games].reset_index(drop=True)


def fit_adp_ppg_mapping(
    training_seasons: Iterable[int],
    weekly_df: pd.DataFrame,
    crosswalk: pd.DataFrame,
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
        crosswalk: Output of :func:`build_name_id_crosswalk` — must cover
            the players in ``training_seasons``' ADP snapshots (pool
            rosters for those seasons when building it).
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
        resolved = resolve_adp_player_ids(adp, crosswalk)
        if resolved.empty:
            continue
        realized = compute_realized_season_ppg(weekly_df, yr, scoring_format=scoring_format)
        if realized.empty:
            continue
        merged = resolved.merge(realized[["player_id", "realized_ppg"]], on="player_id", how="inner")
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
    adp_df: pd.DataFrame, mapping: Dict[str, Dict[str, float]], crosswalk: pd.DataFrame
) -> pd.DataFrame:
    """Apply a fitted mapping to one season's ADP snapshot, keyed by player_id.

    Args:
        adp_df: Output of :func:`load_adp_snapshot` for the eval season.
        mapping: Output of :func:`fit_adp_ppg_mapping`.
        crosswalk: Output of :func:`build_name_id_crosswalk` — must cover
            the eval season's ADP snapshot (pool rosters including the eval
            season when building it, so pre-debut rookies resolve).

    Returns:
        DataFrame with columns ``player_id``, ``position``, ``adp_implied_ppg``
        (floored at 0 — projected points are never negative). Empty if
        ``adp_df``/``mapping``/``crosswalk`` is empty. Rows whose position
        has no fitted mapping, or whose name doesn't resolve to a
        ``player_id``, are dropped (not zero-filled).
    """
    empty = pd.DataFrame(columns=["player_id", "position", "adp_implied_ppg"])
    if adp_df is None or adp_df.empty or not mapping:
        return empty
    resolved = resolve_adp_player_ids(adp_df, crosswalk)
    if resolved.empty:
        return empty

    rows: List[pd.DataFrame] = []
    for pos, coefs in mapping.items():
        sub = resolved[(resolved["position"] == pos) & resolved["adp"].notna() & (resolved["adp"] > 0)]
        if sub.empty:
            continue
        log_adp = np.log10(sub["adp"].clip(lower=1.0))
        implied = (coefs["slope"] * log_adp + coefs["intercept"]).clip(lower=0.0)
        rows.append(
            pd.DataFrame(
                {
                    "player_id": sub["player_id"].values,
                    "position": pos,
                    "adp_implied_ppg": implied.values,
                }
            )
        )
    if not rows:
        return empty
    return pd.concat(rows, ignore_index=True).drop_duplicates(["player_id", "position"])


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
    weight schedule's weeks, for players with no ADP-implied match
    (``player_id`` join miss), and for positions outside
    ``ADP_PRIOR_POSITIONS``.

    Args:
        proj_df: Projections with ``player_id``, ``position``, ``points_col``.
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
        or "player_id" not in proj.columns
        or "position" not in proj.columns
    ):
        return proj

    lookup = implied_df.drop_duplicates("player_id").set_index("player_id")["adp_implied_ppg"]
    pids = proj["player_id"].astype(str)
    implied = pids.map(lookup)
    proj["adp_implied_ppg"] = implied

    positions = proj["position"].astype(str).str.upper()
    mask = positions.isin(ADP_PRIOR_POSITIONS) & implied.notna()
    if mask.any():
        proj.loc[mask, points_col] = (
            (1.0 - w) * proj.loc[mask, points_col] + w * implied[mask]
        ).round(2)
    return proj
