#!/usr/bin/env python3
"""Heuristic experiment lab — fast config sweeps over cached backtest inputs.

The production-faithful eval (production_eval.py) takes ~7 minutes per run
because it rebuilds Silver features for every (season, week). This lab caches
the exact per-week projection inputs once, then evaluates heuristic config
variants in seconds.

Fidelity: the cache stage replicates run_backtest()'s data assembly exactly
(build_silver_features -> week-1 target frame -> project_position -> merge
actuals on player_name). A `--config production` run must match the PFE
baseline per-position MAE within ~0.02 before any sweep results are trusted.

Usage:
    python scripts/experiment_heuristic_lab.py build-cache --seasons 2022,2023,2024
    python scripts/experiment_heuristic_lab.py verify
    python scripts/experiment_heuristic_lab.py sweep-matchup
    python scripts/experiment_heuristic_lab.py sweep-recency
"""

import argparse
import itertools
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import projection_engine  # noqa: E402
from projection_engine import project_position  # noqa: E402
from scoring_calculator import calculate_fantasy_points_df  # noqa: E402
from backtest_projections import (  # noqa: E402
    build_silver_features,
    compute_actuals,
    _load_local_parquet,
    _prepare_weekly,
)
import veteran_prior  # noqa: E402
from veteran_prior import (  # noqa: E402
    build_player_priors,
    apply_veteran_prior_blend,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
CACHE_DIR = os.path.join(PROJECT_ROOT, "output", "heuristic_lab_cache")

POSITIONS = ["QB", "RB", "WR", "TE"]
SCORING = "half_ppr"


# ---------------------------------------------------------------------------
# Cache building
# ---------------------------------------------------------------------------


def _load_weekly(seasons: List[int]) -> pd.DataFrame:
    all_seasons = sorted(set(seasons + [s - 1 for s in seasons]))
    dfs = []
    for s in all_seasons:
        local = _load_local_parquet(BRONZE_DIR, f"players/weekly/season={s}/*.parquet")
        if not local.empty:
            dfs.append(local)
    weekly = pd.concat(dfs, ignore_index=True)
    return _prepare_weekly(weekly)


def _load_schedules(seasons: List[int]) -> pd.DataFrame:
    all_seasons = sorted(set(seasons + [s - 1 for s in seasons]))
    dfs = []
    for s in all_seasons:
        local = _load_local_parquet(BRONZE_DIR, f"games/season={s}/*.parquet")
        if local.empty:
            local = _load_local_parquet(BRONZE_DIR, f"schedules/season={s}/*.parquet")
        if not local.empty:
            if "season" not in local.columns:
                local["season"] = s
            dfs.append(local)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def build_cache(seasons: List[int], weeks: Optional[List[int]] = None) -> None:
    """Build per-(season, week) target frames + actuals, mirroring run_backtest."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    weekly_df = _load_weekly(seasons)
    schedules_df = _load_schedules(seasons)
    schedules_df.to_parquet(os.path.join(CACHE_DIR, "schedules.parquet"), index=False)
    weekly_df.to_parquet(os.path.join(CACHE_DIR, "weekly.parquet"), index=False)

    manifest = []
    for season in seasons:
        for week in weeks or range(3, 19):
            silver_df = build_silver_features(weekly_df, season, up_to_week=week)
            if silver_df.empty:
                continue
            # Mirror generate_weekly_projections step 1: week-1 feature rows
            target_df = silver_df[
                (silver_df["season"] == season) & (silver_df["week"] == week - 1)
            ].copy()
            if target_df.empty:
                latest_week = silver_df[silver_df["season"] == season]["week"].max()
                target_df = silver_df[
                    (silver_df["season"] == season) & (silver_df["week"] == latest_week)
                ].copy()
            target_df["proj_season"] = season
            target_df["proj_week"] = week

            actuals = compute_actuals(weekly_df, season, week, SCORING)
            if actuals.empty:
                continue

            target_df.to_parquet(
                os.path.join(CACHE_DIR, f"target_{season}_{week:02d}.parquet"),
                index=False,
            )
            actuals.to_parquet(
                os.path.join(CACHE_DIR, f"actuals_{season}_{week:02d}.parquet"),
                index=False,
            )
            manifest.append({"season": season, "week": week})
            print(f"cached {season} w{week}: {len(target_df)} target rows")

    with open(os.path.join(CACHE_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)
    print(f"Cache built: {len(manifest)} weeks")


# ---------------------------------------------------------------------------
# Defensive strength table (properly lagged)
# ---------------------------------------------------------------------------


def build_defense_strength(
    weekly_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    scoring_format: str = SCORING,
    window: int = 8,
    min_games: int = 3,
) -> pd.DataFrame:
    """Trailing fantasy points allowed per position by each defense.

    For each (season, week, defense, position), computes the mean fantasy
    points that position group scored against the defense over its previous
    `window` games (strictly before that week — shift(1) lag, spans season
    boundaries). Normalized to a ratio vs the league mean of the same week.

    Returns columns: season, week, team, position, ratio.
    """
    pts = calculate_fantasy_points_df(
        weekly_df.copy(), scoring_format=scoring_format, output_col="_fp"
    )

    sched = schedules_df[["season", "week", "home_team", "away_team"]].copy()
    home = sched.rename(columns={"home_team": "player_team", "away_team": "defense"})
    away = sched.rename(columns={"away_team": "player_team", "home_team": "defense"})
    opp_map = pd.concat([home, away], ignore_index=True)

    pts = pts.merge(
        opp_map,
        left_on=["season", "week", "recent_team"],
        right_on=["season", "week", "player_team"],
        how="inner",
    )
    pts = pts[pts["position"].isin(POSITIONS)]

    allowed = (
        pts.groupby(["season", "week", "defense", "position"], as_index=False)["_fp"]
        .sum()
        .rename(columns={"_fp": "pts_allowed"})
    )
    allowed = allowed.sort_values(["defense", "position", "season", "week"])
    allowed["trailing"] = allowed.groupby(["defense", "position"])[
        "pts_allowed"
    ].transform(lambda s: s.shift(1).rolling(window, min_periods=min_games).mean())

    league = allowed.groupby(["season", "week", "position"])["trailing"].transform(
        "mean"
    )
    allowed["ratio"] = allowed["trailing"] / league
    out = allowed.rename(columns={"defense": "team"})[
        ["season", "week", "team", "position", "ratio"]
    ]
    return out.dropna(subset=["ratio"])


def build_upcoming_opponent_map(schedules_df: pd.DataFrame) -> Dict:
    """(season, week, team) -> opponent dict from schedules."""
    sched = schedules_df[["season", "week", "home_team", "away_team"]].dropna()
    omap: Dict = {}
    for row in sched.itertuples(index=False):
        omap[(row.season, row.week, row.home_team)] = row.away_team
        omap[(row.season, row.week, row.away_team)] = row.home_team
    return omap


# ---------------------------------------------------------------------------
# Config evaluation
# ---------------------------------------------------------------------------


def _make_matchup_patch(
    strength: pd.DataFrame,
    opp_map: Dict,
    beta,
    clip_lo: float = 0.85,
    clip_hi: float = 1.15,
    clip_by_pos: Optional[Dict[str, Tuple[float, float]]] = None,
):
    """Return a _matchup_factor replacement using upcoming opponent + ratio.

    `beta` may be a float (all positions) or a dict {position: beta}.
    """
    # lookup: (season, week, team, position) -> ratio
    lut = {
        (r.season, r.week, r.team, r.position): r.ratio
        for r in strength.itertuples(index=False)
    }

    def patched(df: pd.DataFrame, opp_rankings, position: str) -> pd.Series:
        b = beta.get(position, 0.0) if isinstance(beta, dict) else beta
        if b == 0.0:
            return pd.Series(1.0, index=df.index)
        lo, hi = (clip_by_pos or {}).get(position, (clip_lo, clip_hi))
        vals = []
        for row in df.itertuples(index=False):
            season = getattr(row, "proj_season", None)
            week = getattr(row, "proj_week", None)
            team = getattr(row, "recent_team", None)
            opp = opp_map.get((season, week, team))
            ratio = lut.get((season, week, opp, position)) if opp else None
            if ratio is None or not np.isfinite(ratio):
                vals.append(1.0)
            else:
                vals.append(float(np.clip(1.0 + b * (ratio - 1.0), lo, hi)))
        return pd.Series(vals, index=df.index)

    return patched


def evaluate_config(
    manifest: List[Dict],
    recency_by_pos: Optional[Dict[str, Dict[str, float]]] = None,
    matchup_patch=None,
    td_regression: Optional[Dict[str, float]] = None,
    prior_blend_fn=None,
) -> pd.DataFrame:
    """Evaluate one heuristic config over the cached weeks.

    Args:
        manifest: List of {season, week} dicts from the cache.
        recency_by_pos: Optional per-position recency weight overrides.
        matchup_patch: Optional replacement for projection_engine._matchup_factor.
        td_regression: Optional TD_REGRESSION_WEIGHT overrides.
        prior_blend_fn: Optional callable ``(target_df, pos, season, week)
            -> pd.DataFrame`` that pre-processes the position-filtered target
            frame to blend veteran prior stats into rolling columns before
            ``project_position`` is called.  If None, no blending is applied.

    Returns per-row results DataFrame with position, error, abs_error.
    """
    orig_weights = dict(projection_engine.RECENCY_WEIGHTS)
    orig_matchup = projection_engine._matchup_factor
    orig_td = dict(projection_engine.TD_REGRESSION_WEIGHT)
    empty_rankings = pd.DataFrame()
    results = []
    try:
        if matchup_patch is not None:
            projection_engine._matchup_factor = matchup_patch
        projection_engine.TD_REGRESSION_WEIGHT.clear()
        projection_engine.TD_REGRESSION_WEIGHT.update(td_regression or {})
        for entry in manifest:
            season, week = entry["season"], entry["week"]
            target_df = pd.read_parquet(
                os.path.join(CACHE_DIR, f"target_{season}_{week:02d}.parquet")
            )
            actuals = pd.read_parquet(
                os.path.join(CACHE_DIR, f"actuals_{season}_{week:02d}.parquet")
            )
            for pos in POSITIONS:
                if recency_by_pos and pos in recency_by_pos:
                    projection_engine.RECENCY_WEIGHTS.clear()
                    projection_engine.RECENCY_WEIGHTS.update(recency_by_pos[pos])
                else:
                    projection_engine.RECENCY_WEIGHTS.clear()
                    projection_engine.RECENCY_WEIGHTS.update(orig_weights)

                # Apply veteran prior blend if provided
                proj_input = target_df
                if prior_blend_fn is not None:
                    blended_pos = prior_blend_fn(target_df, pos, season, week)
                    if not blended_pos.empty:
                        # Reconstruct full target_df with blended position rows
                        other_rows = target_df[target_df["position"] != pos]
                        proj_input = pd.concat(
                            [other_rows, blended_pos], ignore_index=True
                        )

                proj = project_position(proj_input, pos, empty_rankings, SCORING)
                if proj.empty:
                    continue
                merged = proj.merge(
                    actuals[["player_name", "actual_points"]],
                    on="player_name",
                    how="inner",
                )
                if merged.empty:
                    continue
                keep = ["player_name", "position", "projected_points", "actual_points"]
                if "player_id" in merged.columns:
                    keep.insert(0, "player_id")
                merged = merged[keep].copy()
                merged["season"] = season
                merged["week"] = week
                merged["error"] = merged["projected_points"] - merged["actual_points"]
                merged["abs_error"] = merged["error"].abs()
                results.append(merged)
    finally:
        projection_engine.RECENCY_WEIGHTS.clear()
        projection_engine.RECENCY_WEIGHTS.update(orig_weights)
        projection_engine._matchup_factor = orig_matchup
        projection_engine.TD_REGRESSION_WEIGHT.clear()
        projection_engine.TD_REGRESSION_WEIGHT.update(orig_td)

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


def summarize(results: pd.DataFrame) -> Dict:
    out = {
        "overall_mae": float(results["abs_error"].mean()),
        "overall_bias": float(results["error"].mean()),
    }
    for pos in POSITIONS:
        sub = results[results["position"] == pos]
        if not sub.empty:
            out[f"{pos}_mae"] = float(sub["abs_error"].mean())
            out[f"{pos}_bias"] = float(sub["error"].mean())
    return out


def _load_manifest() -> List[Dict]:
    with open(os.path.join(CACHE_DIR, "manifest.json")) as fh:
        return json.load(fh)


def _fmt(s: Dict) -> str:
    pos_str = " ".join(f"{p}:{s.get(f'{p}_mae', float('nan')):.3f}" for p in POSITIONS)
    return f"overall {s['overall_mae']:.4f} (bias {s['overall_bias']:+.3f}) | {pos_str}"


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------


def cmd_verify() -> None:
    manifest = _load_manifest()
    results = evaluate_config(manifest)
    s = summarize(results)
    print("LAB production-config result (must match PFE baseline within ~0.02):")
    print(_fmt(s))
    print("PFE baseline_repro_20260609: overall 4.78 | QB:6.35 RB:4.99 WR:4.67 TE:3.70")


def cmd_sweep_matchup() -> None:
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    opp_map = build_upcoming_opponent_map(sched)

    rows = []
    for window in [6, 8, 12]:
        strength = build_defense_strength(weekly, sched, window=window)
        for beta in [0.0, 0.15, 0.3, 0.5, 0.75, 1.0]:
            if beta == 0.0 and window != 8:
                continue
            patch = _make_matchup_patch(strength, opp_map, beta, 0.85, 1.15)
            results = evaluate_config(manifest, matchup_patch=patch)
            s = summarize(results)
            s.update({"window": window, "beta": beta})
            rows.append(s)
            print(f"window={window} beta={beta:<5} {_fmt(s)}")

    pd.DataFrame(rows).to_csv(os.path.join(CACHE_DIR, "sweep_matchup.csv"), index=False)


def cmd_sweep_recency() -> None:
    manifest = _load_manifest()
    grid = []
    for r3 in [0.15, 0.25, 0.30, 0.40, 0.50]:
        for r6 in [0.05, 0.15, 0.25]:
            std = round(1.0 - r3 - r6, 2)
            if std < 0.2:
                continue
            grid.append({"roll3": r3, "roll6": r6, "std": std})

    rows = []
    for combo in grid:
        recency = {p: combo for p in POSITIONS}
        results = evaluate_config(manifest, recency_by_pos=recency)
        s = summarize(results)
        s.update(combo)
        rows.append(s)
        print(f"r3={combo['roll3']} r6={combo['roll6']} std={combo['std']}  {_fmt(s)}")

    pd.DataFrame(rows).to_csv(os.path.join(CACHE_DIR, "sweep_recency.csv"), index=False)


def cmd_sweep_round2() -> None:
    """Round 2: finer recency grid, per-position matchup beta, TD regression,
    then the combined candidate config."""
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    opp_map = build_upcoming_opponent_map(sched)
    strength = build_defense_strength(weekly, sched, window=8)

    rows = []

    def run(label: str, **kwargs) -> Dict:
        results = evaluate_config(manifest, **kwargs)
        s = summarize(results)
        s["label"] = label
        rows.append(s)
        print(f"{label:<42} {_fmt(s)}")
        return s

    # --- A. extended recency grid (global) ---
    for r3, r6 in [
        (0.0, 0.0),
        (0.05, 0.05),
        (0.10, 0.05),
        (0.15, 0.05),
        (0.10, 0.0),
        (0.15, 0.0),
    ]:
        std = round(1.0 - r3 - r6, 2)
        combo = {"roll3": r3, "roll6": r6, "std": std}
        run(
            f"recency r3={r3} r6={r6} std={std}",
            recency_by_pos={p: combo for p in POSITIONS},
        )

    # --- B. per-position matchup beta (production recency) ---
    beta_grid = {
        "QB": [0.0, 0.15, 0.3],
        "RB": [0.75, 1.0, 1.25, 1.5],
        "WR": [0.0, 0.15, 0.3],
        "TE": [0.0, 0.3, 0.5],
    }
    base_beta = {"QB": 0.15, "RB": 1.0, "WR": 0.15, "TE": 0.3}
    for pos in POSITIONS:
        for b in beta_grid[pos]:
            betas = dict(base_beta)
            betas[pos] = b
            patch = _make_matchup_patch(strength, opp_map, betas)
            run(f"matchup {pos} beta={b} (others base)", matchup_patch=patch)

    # --- C. RB wider clip at high beta ---
    patch = _make_matchup_patch(
        strength,
        opp_map,
        base_beta,
        clip_by_pos={"RB": (0.80, 1.20)},
    )
    run("matchup base betas, RB clip 0.80-1.20", matchup_patch=patch)

    # --- D. TD regression sweep (production recency, no matchup) ---
    for w in [0.25, 0.5, 0.75, 1.0]:
        run(f"td_regression w={w}", td_regression={p: w for p in POSITIONS})

    pd.DataFrame(rows).to_csv(os.path.join(CACHE_DIR, "sweep_round2.csv"), index=False)


def cmd_eval_json(config_path: str) -> None:
    """Evaluate a single combined config from a JSON file."""
    with open(config_path) as fh:
        cfg = json.load(fh)
    manifest = _load_manifest()
    kwargs: Dict = {}
    if cfg.get("recency_by_pos"):
        kwargs["recency_by_pos"] = cfg["recency_by_pos"]
    if cfg.get("td_regression"):
        kwargs["td_regression"] = cfg["td_regression"]
    if cfg.get("matchup_beta"):
        weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
        sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
        strength = build_defense_strength(
            weekly, sched, window=cfg.get("matchup_window", 8)
        )
        clip_by_pos = {
            k: tuple(v) for k, v in (cfg.get("matchup_clip_by_pos") or {}).items()
        }
        kwargs["matchup_patch"] = _make_matchup_patch(
            strength,
            build_upcoming_opponent_map(sched),
            cfg["matchup_beta"],
            clip_by_pos=clip_by_pos or None,
        )
    results = evaluate_config(manifest, **kwargs)
    s = summarize(results)
    print(f"{cfg.get('name', config_path)}  {_fmt(s)}")


def _v42_results(manifest: List[Dict]) -> pd.DataFrame:
    """Evaluate the shipped v4.2 config (with matchup patch) over the cache."""
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    strength = build_defense_strength(weekly, sched, window=8)
    omap = build_upcoming_opponent_map(sched)
    patch = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))
    return evaluate_config(manifest, matchup_patch=patch)


def cmd_sweep_residual(model_dir: str) -> None:
    """Lambda-shrinkage sweep for residual corrections on top of v4.2.

    Residual models must have been trained on seasons outside the cached
    eval window (e.g. 2016-2021) for this evaluation to be leak-free.
    """
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
    from hybrid_projection import load_residual_model
    from player_feature_engineering import assemble_player_features

    manifest = _load_manifest()
    seasons = sorted({e["season"] for e in manifest})

    # Feature vectors per season (cached)
    feats = []
    for s in seasons:
        fpath = os.path.join(CACHE_DIR, f"features_{s}.parquet")
        if os.path.exists(fpath):
            feats.append(pd.read_parquet(fpath))
        else:
            fdf = assemble_player_features(s)
            fdf.to_parquet(fpath, index=False)
            feats.append(fdf)
    feat_df = pd.concat(feats, ignore_index=True)
    print(f"Feature vectors: {len(feat_df)} rows, {len(feat_df.columns)} cols")

    base = _v42_results(manifest)
    print(f"v4.2 heuristic-only baseline: {_fmt(summarize(base))}")

    rows = []
    for pos in POSITIONS:
        try:
            model_obj, meta = load_residual_model(pos, model_dir)
        except FileNotFoundError:
            continue
        features = meta.get("features", [])
        pos_res = base[base["position"] == pos].copy()

        merged = pos_res.merge(
            feat_df[
                ["player_id", "season", "week"]
                + [f for f in features if f in feat_df.columns]
            ].drop_duplicates(subset=["player_id", "season", "week"], keep="last"),
            on=["player_id", "season", "week"],
            how="left",
        )
        X = pd.DataFrame(
            {f: merged[f] if f in merged.columns else np.nan for f in features},
            index=merged.index,
        )
        has = X.notna().any(axis=1)
        corr = np.zeros(len(merged))
        if isinstance(model_obj, dict):
            imp = model_obj.get("imputer")
            Xp = X[has]
            Xp = (
                pd.DataFrame(imp.transform(Xp), columns=Xp.columns, index=Xp.index)
                if imp is not None
                else Xp.fillna(0.0)
            )
            corr[has.values] = model_obj["model"].predict(Xp)
        else:
            corr[has.values] = model_obj.predict(X[has])

        print(
            f"\n{pos}: {int(has.sum())}/{len(merged)} rows with features; "
            f"mean corr {corr[has.values].mean():+.3f}"
        )
        base_mae = (
            pos_res["abs_error"].mean()
            if "abs_error" in pos_res
            else ((pos_res["projected_points"] - pos_res["actual_points"]).abs().mean())
        )
        for lam in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            hybrid = np.clip(merged["projected_points"].values + lam * corr, 0.0, None)
            err = hybrid - merged["actual_points"].values
            mae = float(np.abs(err).mean())
            bias = float(err.mean())
            rows.append({"position": pos, "lambda": lam, "mae": mae, "bias": bias})
            print(
                f"  lambda={lam:<4} MAE {mae:.4f} (bias {bias:+.3f})"
                f"  delta vs lam0 {mae - base_mae:+.4f}"
            )

    pd.DataFrame(rows).to_csv(
        os.path.join(CACHE_DIR, "sweep_residual.csv"), index=False
    )


def _load_prior_weekly(seasons: List[int]) -> pd.DataFrame:
    """Load Bronze weekly data for prior computation (includes prior season)."""
    prior_seasons = sorted(set(seasons + [s - 1 for s in seasons]))
    dfs = []
    for s in prior_seasons:
        local = _load_local_parquet(BRONZE_DIR, f"players/weekly/season={s}/*.parquet")
        if not local.empty:
            dfs.append(local)
    if not dfs:
        return pd.DataFrame()
    weekly = pd.concat(dfs, ignore_index=True)
    return _prepare_weekly(weekly)


def _make_prior_blend_fn(
    priors_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    n_full: int = 5,
    steepness: float = 0.7,
    min_prior_games: int = 4,
    team_change_decay: float = 0.7,
    first_week_back_discount: float = 0.85,
):
    """Return a prior_blend_fn closure with the given hyperparameters."""

    def blend_fn(
        target_df: pd.DataFrame, pos: str, season: int, week: int
    ) -> pd.DataFrame:
        return apply_veteran_prior_blend(
            target_df=target_df,
            priors_df=priors_df,
            weekly_df=weekly_df,
            position=pos,
            proj_season=season,
            proj_week=week,
            n_full=n_full,
            steepness=steepness,
            min_prior_games=min_prior_games,
            team_change_decay=team_change_decay,
            first_week_back_discount=first_week_back_discount,
        )

    return blend_fn


def cmd_sweep_veteran_prior() -> None:
    """Sweep veteran prior blending hyperparameters on 2022-2024 cached weeks.

    Sweeps:
      - n_full: [3, 4, 5, 6]  (games to reach full rolling weight)
      - steepness: [0.5, 0.7, 1.0]  (exponential schedule steepness)
      - team_change_decay: [0.5, 0.7, 0.9]  (decay factor on team change)
      - first_week_back_discount: [0.75, 0.85, 1.0]

    Each config is evaluated with the v4.2 matchup patch active (same as
    the production baseline) so results are directly comparable.

    Outputs:
      - Console: per-config summary with overall + per-position MAE
      - CSV: output/heuristic_lab_cache/sweep_veteran_prior.csv
    """
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    omap = build_upcoming_opponent_map(sched)
    strength = build_defense_strength(weekly, sched, window=8)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))

    seasons = sorted({e["season"] for e in manifest})
    prior_weekly = _load_prior_weekly(seasons)
    priors_df = build_player_priors(prior_weekly, scoring_format=SCORING)
    print(f"Built priors for {len(priors_df)} player-seasons")

    rows = []

    def run(label: str, **blend_kwargs) -> Dict:
        blend_fn = _make_prior_blend_fn(priors_df, prior_weekly, **blend_kwargs)
        results = evaluate_config(
            manifest, matchup_patch=matchup, prior_blend_fn=blend_fn
        )
        s = summarize(results)
        s["label"] = label
        s.update(blend_kwargs)
        rows.append(s)
        print(f"{label:<60} {_fmt(s)}")
        return s

    # Baseline (no prior blend) for comparison
    base_results = evaluate_config(manifest, matchup_patch=matchup)
    base = summarize(base_results)
    base["label"] = "baseline_no_prior"
    rows.append(base)
    print(f"{'baseline_no_prior':<60} {_fmt(base)}")

    # Sweep n_full and steepness
    for n_full in [3, 4, 5, 6]:
        for steepness in [0.5, 0.7, 1.0]:
            label = f"n_full={n_full} steep={steepness}"
            run(label, n_full=n_full, steepness=steepness)

    # Sweep team_change_decay (fix best n_full/steepness from above)
    for decay in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        label = f"n_full=5 steep=0.7 decay={decay}"
        run(label, n_full=5, steepness=0.7, team_change_decay=decay)

    # Sweep first_week_back_discount
    for disc in [0.70, 0.75, 0.80, 0.85, 0.90, 1.0]:
        label = f"n_full=5 steep=0.7 fwb={disc}"
        run(label, n_full=5, steepness=0.7, first_week_back_discount=disc)

    df = pd.DataFrame(rows)
    out = os.path.join(CACHE_DIR, "sweep_veteran_prior.csv")
    df.to_csv(out, index=False)
    print(f"\nSaved to {out}")

    # Print top-5 by WR MAE improvement
    if "WR_mae" in df.columns:
        top5 = df.nsmallest(5, "WR_mae")
        print("\nTop-5 configs by WR MAE:")
        for _, row in top5.iterrows():
            print(
                f"  {row['label']:<50} WR:{row['WR_mae']:.4f} RB:{row['RB_mae']:.4f} QB:{row['QB_mae']:.4f}"
            )


def cmd_consensus_gap(
    early_weeks: Optional[List[int]] = None,
) -> None:
    """Compute consensus gap before/after veteran prior blending.

    Joins per-row projections (baseline and with best veteran prior config)
    against Sleeper consensus projections (data/silver/external_projections/).
    Only rows where consensus_proj >= 5 are included (per the plan's filter).

    Outputs:
      - Console: gap table by position + WR w3-6 breakdown
      - Named-case before/after table
      - CSV: output/heuristic_lab_cache/consensus_gap_veteran_prior.csv
    """
    import glob as globmod

    if early_weeks is None:
        early_weeks = [3, 4, 5, 6]

    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    omap = build_upcoming_opponent_map(sched)
    strength = build_defense_strength(weekly, sched, window=8)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))

    seasons = sorted({e["season"] for e in manifest})
    prior_weekly = _load_prior_weekly(seasons)
    priors_df = build_player_priors(prior_weekly, scoring_format=SCORING)
    print(f"Built priors for {len(priors_df)} player-seasons")

    # Load best config from sweep CSV if available
    sweep_csv = os.path.join(CACHE_DIR, "sweep_veteran_prior.csv")
    best_n_full, best_steepness, best_decay, best_disc = 5, 0.7, 0.7, 0.85
    if os.path.exists(sweep_csv):
        sweep_df = pd.read_csv(sweep_csv)
        non_base = sweep_df[sweep_df["label"] != "baseline_no_prior"]
        if not non_base.empty and "WR_mae" in non_base.columns:
            best_row = non_base.loc[non_base["WR_mae"].idxmin()]

            # Series.get returns the CELL value even when it is NaN — the
            # default only fires when the key is absent.  Rows from sweeps
            # that didn't pass a kwarg have NaN cells, so guard explicitly
            # or NaN decay/discount silently corrupts the blend.
            def _param(key: str, default: float) -> float:
                val = best_row.get(key, default)
                return default if pd.isna(val) else float(val)

            best_n_full = int(_param("n_full", 5))
            best_steepness = _param("steepness", 0.7)
            best_decay = _param("team_change_decay", 0.7)
            best_disc = _param("first_week_back_discount", 0.85)
            print(
                f"Using best params from sweep: n_full={best_n_full} steepness={best_steepness} "
                f"decay={best_decay} fwb={best_disc}"
            )

    # --- Compute projections ---
    def collect_projections(results_df: pd.DataFrame, label: str) -> pd.DataFrame:
        results_df = results_df.copy()
        results_df["config"] = label
        return results_df

    base_results = evaluate_config(manifest, matchup_patch=matchup)
    best_blend = _make_prior_blend_fn(
        priors_df,
        prior_weekly,
        n_full=best_n_full,
        steepness=best_steepness,
        team_change_decay=best_decay,
        first_week_back_discount=best_disc,
    )
    blend_results = evaluate_config(
        manifest, matchup_patch=matchup, prior_blend_fn=best_blend
    )

    # --- Load consensus ---
    silver_root = os.path.join(PROJECT_ROOT, "data", "silver", "external_projections")
    consensus_rows = []
    for season in seasons:
        for week in range(3, 19):
            week_dir = os.path.join(silver_root, f"season={season}", f"week={week:02d}")
            files = sorted(globmod.glob(os.path.join(week_dir, "*.parquet")))
            if not files:
                continue
            df = pd.read_parquet(files[-1])
            df = df[(df["source"] == "sleeper") & (df["scoring_format"] == SCORING)]
            df = df[df["position"].isin(POSITIONS)]
            if df.empty:
                continue
            df = df.rename(columns={"projected_points": "consensus_proj"})
            df["season"] = season
            df["week"] = week
            consensus_rows.append(df[["player_id", "season", "week", "consensus_proj"]])

    if not consensus_rows:
        print("No consensus data found.")
        return

    consensus = pd.concat(consensus_rows, ignore_index=True)
    # Dedup: sleeper data confirmed no dupes; drop exact-duplicate rows defensively
    consensus = consensus.drop_duplicates(subset=["player_id", "season", "week"])
    print(f"Consensus rows: {len(consensus)}")

    def compute_gap_df(results: pd.DataFrame, label: str) -> pd.DataFrame:
        """Merge results with consensus and actuals, return gap analysis frame."""
        # results has player_id (sometimes), player_name, season, week, projected_points, actual_points
        if "player_id" not in results.columns:
            # No player_id in results; try name-based join via actuals
            return pd.DataFrame()

        merged = results.merge(
            consensus, on=["player_id", "season", "week"], how="inner"
        )
        merged = merged[merged["consensus_proj"] >= 5.0].copy()
        merged["our_mae"] = (merged["projected_points"] - merged["actual_points"]).abs()
        merged["cons_mae"] = (merged["consensus_proj"] - merged["actual_points"]).abs()
        merged["gap"] = merged["our_mae"] - merged["cons_mae"]
        merged["config"] = label
        return merged

    base_gap = compute_gap_df(base_results, "baseline")
    blend_gap = compute_gap_df(blend_results, "veteran_prior")

    if base_gap.empty or blend_gap.empty:
        # Fallback: join on player_name if player_id not in results
        print("NOTE: player_id not in results — attempting name-based consensus join")
        print("Skipping gap analysis (need player_id in evaluate_config output)")
        print(f"Baseline MAE: {_fmt(summarize(base_results))}")
        print(f"Veteran prior MAE: {_fmt(summarize(blend_results))}")
        return

    combined = pd.concat([base_gap, blend_gap], ignore_index=True)

    def print_gap_table(df: pd.DataFrame, config_label: str) -> None:
        sub = df[df["config"] == config_label]
        print(f"\n{config_label} (consensus_proj >= 5, matched rows):")
        print(f"  {'Pos':<6} {'n':>6} {'Our MAE':>9} {'Cons MAE':>9} {'Gap':>8}")
        for pos in POSITIONS:
            p = sub[sub["position"] == pos]
            if p.empty:
                continue
            print(
                f"  {pos:<6} {len(p):>6} {p['our_mae'].mean():>9.3f} "
                f"{p['cons_mae'].mean():>9.3f} {p['gap'].mean():>+8.3f}"
            )
        # WR early weeks
        wr_early = sub[(sub["position"] == "WR") & (sub["week"].isin(early_weeks))]
        if not wr_early.empty:
            print(
                f"  {'WR w3-6':<6} {len(wr_early):>6} {wr_early['our_mae'].mean():>9.3f} "
                f"{wr_early['cons_mae'].mean():>9.3f} {wr_early['gap'].mean():>+8.3f}"
            )
        # RB early weeks
        rb_early = sub[(sub["position"] == "RB") & (sub["week"].isin(early_weeks))]
        if not rb_early.empty:
            print(
                f"  {'RB w3-6':<6} {len(rb_early):>6} {rb_early['our_mae'].mean():>9.3f} "
                f"{rb_early['cons_mae'].mean():>9.3f} {rb_early['gap'].mean():>+8.3f}"
            )

    print_gap_table(combined, "baseline")
    print_gap_table(combined, "veteran_prior")

    # --- Named cases ---
    named_cases = [
        ("CMC 2024 w11", "00-0033280", 2024, 11),
        ("D.Smith 2022 w3", "00-0036912", 2022, 3),
        ("A.St.Brown 2024 w3", "00-0036963", 2024, 3),
        ("C.Kupp 2023 w6", "00-0033908", 2023, 6),
    ]
    print("\nNamed cases (before / after veteran prior blending):")
    print(f"  {'Case':<22} {'Ours':>7} {'Prior':>7} {'Actual':>7} {'Cons':>7}")
    for name, pid, season, week in named_cases:
        base_row = base_results[
            (
                (base_results.get("player_id", pd.Series()) == pid)
                if "player_id" in base_results.columns
                else pd.Series(False, index=base_results.index)
            )
        ]
        # Use player_id column directly
        if "player_id" in base_results.columns:
            b = base_results[
                (base_results["player_id"] == pid)
                & (base_results["season"] == season)
                & (base_results["week"] == week)
            ]
            v = blend_results[
                (blend_results["player_id"] == pid)
                & (blend_results["season"] == season)
                & (blend_results["week"] == week)
            ]
        else:
            b, v = pd.DataFrame(), pd.DataFrame()

        if b.empty or v.empty:
            print(f"  {name:<22} {'N/A':>7} {'N/A':>7} {'N/A':>7} {'N/A':>7}")
            continue

        cons_row = consensus[
            (consensus["player_id"] == pid)
            & (consensus["season"] == season)
            & (consensus["week"] == week)
        ]
        cons_val = (
            float(cons_row["consensus_proj"].iloc[0])
            if not cons_row.empty
            else float("nan")
        )

        b_proj = float(b["projected_points"].iloc[0])
        v_proj = float(v["projected_points"].iloc[0])
        actual = float(b["actual_points"].iloc[0])
        print(
            f"  {name:<22} {b_proj:>7.2f} {v_proj:>7.2f} {actual:>7.2f} {cons_val:>7.2f}"
        )

    # Save combined gap analysis
    out = os.path.join(CACHE_DIR, "consensus_gap_veteran_prior.csv")
    combined.to_csv(out, index=False)
    print(f"\nSaved gap analysis to {out}")


def _load_route_features(seasons: List[int]) -> pd.DataFrame:
    """Load route participation Silver tables for the given seasons."""
    import glob as globmod

    frames = []
    for season in seasons:
        files = sorted(
            globmod.glob(
                os.path.join(
                    PROJECT_ROOT,
                    "data",
                    "silver",
                    "graph_features",
                    f"season={season}",
                    "graph_route_participation_*.parquet",
                )
            )
        )
        if files:
            frames.append(pd.read_parquet(files[-1]))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def cmd_sweep_rb_route() -> None:
    """Sweep blending route_rate_trail4 into the RB usage multiplier.

    Production _usage_multiplier(RB) ranks carry_share into [0.80, 1.15].
    Candidate: blended percentile w*pct(route_rate_trail4) +
    (1-w)*pct(carry_share). Rows without route data fall back to pure
    carry_share. Evaluated on the cached 2022-2024 frames with the
    production v4.2 matchup patch active (apples-to-apples vs baseline).
    """
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    strength = build_defense_strength(weekly, sched, window=8)
    omap = build_upcoming_opponent_map(sched)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))

    seasons = sorted({e["season"] for e in manifest})
    route = _load_route_features(seasons)
    if route.empty:
        print("No route participation data - aborting")
        return
    # lookup keyed at the PROJECTED week (trail4 is lagged through W-1)
    route_lut = route.set_index(["player_id", "season", "week"])["route_rate_trail4"]

    orig_usage = projection_engine._usage_multiplier

    def make_usage_patch(w: float):
        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            if position != "RB" or w == 0.0 or "player_id" not in df.columns:
                return base
            season_col = (
                df["proj_season"] if "proj_season" in df.columns else df["season"]
            )
            week_col = df["proj_week"] if "proj_week" in df.columns else df["week"]
            keys = list(zip(df["player_id"], season_col, week_col))
            rr = pd.Series([route_lut.get(k, np.nan) for k in keys], index=df.index)
            if rr.notna().sum() < 5:
                return base
            rr_pct = rr.rank(pct=True)
            base_pct = (base - 0.80) / 0.35  # invert to percentile
            blended = (1 - w) * base_pct + w * rr_pct.fillna(base_pct)
            return (0.80 + 0.35 * blended).clip(0.80, 1.15)

        return patched

    for w in [0.0, 0.25, 0.5, 0.75, 1.0]:
        projection_engine._usage_multiplier = make_usage_patch(w)
        try:
            results = evaluate_config(manifest, matchup_patch=matchup)
        finally:
            projection_engine._usage_multiplier = orig_usage
        s = summarize(results)
        print(
            f"rb_route_w={w:<5} RB MAE {s['RB_mae']:.4f} "
            f"(bias {s['RB_bias']:+.3f}) | {_fmt(s)}"
        )


def _build_production_blend_fn(
    weekly: pd.DataFrame,
    manifest: List[Dict],
) -> object:
    """Build the best-params veteran prior blend fn from the sweep CSV.

    Uses n_full=5, steepness=0.7, team_change_decay=1.0 (shipped params from
    plan RESULTS section).  Falls back to defaults when sweep CSV is absent.

    Args:
        weekly: Bronze weekly DataFrame (used as both training and lookup).
        manifest: Manifest from the lab cache.

    Returns:
        Callable ``(target_df, pos, season, week) -> pd.DataFrame`` ready
        for ``evaluate_config(prior_blend_fn=...)``.
    """
    seasons = sorted({e["season"] for e in manifest})
    prior_weekly = _load_prior_weekly(seasons)
    priors_df = build_player_priors(prior_weekly, scoring_format=SCORING)

    sweep_csv = os.path.join(CACHE_DIR, "sweep_veteran_prior.csv")
    n_full, steepness, decay, disc = 5, 0.7, 1.0, 0.85
    if os.path.exists(sweep_csv):
        sweep_df = pd.read_csv(sweep_csv)
        non_base = sweep_df[sweep_df["label"] != "baseline_no_prior"]
        if not non_base.empty and "WR_mae" in non_base.columns:
            best_row = non_base.loc[non_base["WR_mae"].idxmin()]

            def _param(key: str, default: float) -> float:
                val = best_row.get(key, default)
                return default if pd.isna(val) else float(val)

            n_full = int(_param("n_full", 5))
            steepness = _param("steepness", 0.7)
            decay = _param("team_change_decay", 1.0)
            disc = _param("first_week_back_discount", 0.85)

    return _make_prior_blend_fn(
        priors_df,
        prior_weekly,
        n_full=n_full,
        steepness=steepness,
        team_change_decay=decay,
        first_week_back_discount=disc,
    )


def cmd_sweep_wr_route() -> None:
    """Sweep WR route-rate signals as projection modifiers.

    Tests three mechanisms against the production-config baseline
    (v4.2 matchup + veteran prior blend + RB snap-collapse active):

    **Mechanism A — usage level blend (null hypothesis from RB sweep):**
    Blend ``route_rate_trail4`` percentile into the WR usage multiplier
    alongside ``target_share``.  Weight ``w`` in {0.25, 0.5, 0.75, 1.0}.
    Predicted to be null (same as RB); included to confirm.

    **Mechanism B — role-change detector (velocity, asymmetric):**
    Apply a multiplier when ``route_rate_delta`` or ``route_rate_slope``
    exceeds a threshold, analogous to the RB snap-collapse 0.60x.
    Asymmetric: rising role gets a boost; collapsing role gets a shrink.
    Grid:

    - collapse_threshold in {-0.05, -0.08, -0.10, -0.12}
    - boost_threshold    in {+0.05, +0.08, +0.10, +0.12}
    - collapse_mult      in {0.70, 0.75, 0.80, 0.85}
    - boost_mult         in {1.05, 1.10, 1.15}
    - signal source      in {delta, slope}

    The boost and collapse sides are swept separately first, then jointly
    for top candidates.

    All mechanisms are applied ONLY to WR; QB/RB/TE are unchanged.

    Outputs:
      - Console: per-mechanism table with WR/QB/RB/TE MAE + WR Spearman
      - CSV: output/heuristic_lab_cache/sweep_wr_route.csv
      - Gate verdict: PASS/KILL per plan criteria
    """
    from scipy.stats import spearmanr  # type: ignore

    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    strength = build_defense_strength(weekly, sched, window=8)
    omap = build_upcoming_opponent_map(sched)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))
    prior_blend = _build_production_blend_fn(weekly, manifest)

    seasons = sorted({e["season"] for e in manifest})
    route = _load_route_features(seasons)
    if route.empty:
        print("No route participation data found — aborting")
        return

    # Build lookup tables.  trail4/delta/slope are all lagged through W-1
    # inside compute_route_participation, so keying at the projected week is
    # safe (no leakage).
    route_lut_trail4 = route.set_index(["player_id", "season", "week"])[
        "route_rate_trail4"
    ]
    route_lut_delta = route.set_index(["player_id", "season", "week"])[
        "route_rate_delta"
    ]
    route_lut_slope = route.set_index(["player_id", "season", "week"])[
        "route_rate_slope"
    ]

    orig_usage = projection_engine._usage_multiplier

    # ------------------------------------------------------------------
    # Helper: evaluate one config, return summary dict + WR Spearman
    # ------------------------------------------------------------------

    def _run(
        label: str,
        usage_patch=None,
        **eval_kwargs,
    ) -> Dict:
        pe_usage = usage_patch if usage_patch is not None else orig_usage
        projection_engine._usage_multiplier = pe_usage
        try:
            results = evaluate_config(
                manifest,
                matchup_patch=matchup,
                prior_blend_fn=prior_blend,
                **eval_kwargs,
            )
        finally:
            projection_engine._usage_multiplier = orig_usage

        s = summarize(results)
        s["label"] = label

        wr = results[results["position"] == "WR"]
        if len(wr) >= 10:
            corr, _ = spearmanr(wr["projected_points"], wr["actual_points"])
            s["WR_spearman"] = float(corr)
        else:
            s["WR_spearman"] = float("nan")
        return s

    rows: List[Dict] = []

    def _record(s: Dict) -> None:
        rows.append(s)
        sp = s.get("WR_spearman", float("nan"))
        print(
            f"{s['label']:<62} WR:{s.get('WR_mae', float('nan')):.4f} "
            f"rho={sp:.4f} | {_fmt(s)}"
        )

    # ------------------------------------------------------------------
    # BASELINE (production config: matchup + prior blend + snap-collapse)
    # ------------------------------------------------------------------
    base_s = _run("baseline_production")
    _record(base_s)
    baseline_wr_mae = base_s.get("WR_mae", float("nan"))
    baseline_wr_rho = base_s.get("WR_spearman", float("nan"))
    print(
        f"\nBaseline WR MAE: {baseline_wr_mae:.4f}  "
        f"WR Spearman: {baseline_wr_rho:.4f}"
    )
    print(
        "Gates: improve >=0.03 WR MAE vs baseline OR improve >=0.02 WR Spearman "
        "with no WR MAE regression; QB/RB/TE unchanged within +/-0.01."
    )

    # ------------------------------------------------------------------
    # MECHANISM A — usage-level blend (trail4 percentile into WR usage mult)
    # RB sweep found this null; checking WR separately.
    # ------------------------------------------------------------------
    print("\n=== Mechanism A: WR route-level usage blend (trail4 percentile) ===")

    def _make_wr_level_usage(w: float):
        """Blend route_rate_trail4 percentile (weight w) into WR usage mult.

        Args:
            w: Blend weight for the route-rate percentile (0.0 = pure
               target_share; 1.0 = pure route-rate percentile).

        Returns:
            Patched _usage_multiplier function.
        """

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            if position != "WR" or w == 0.0 or "player_id" not in df.columns:
                return base
            season_col = (
                df["proj_season"] if "proj_season" in df.columns else df["season"]
            )
            week_col = df["proj_week"] if "proj_week" in df.columns else df["week"]
            keys = list(zip(df["player_id"], season_col, week_col))
            rr = pd.Series(
                [route_lut_trail4.get(k, np.nan) for k in keys], index=df.index
            )
            if rr.notna().sum() < 5:
                return base
            rr_pct = rr.rank(pct=True)
            base_pct = (base - 0.80) / 0.35
            blended = (1 - w) * base_pct + w * rr_pct.fillna(base_pct)
            return (0.80 + 0.35 * blended).clip(0.80, 1.15)

        return patched

    for w in [0.25, 0.5, 0.75, 1.0]:
        s = _run(f"mech_A_trail4_w={w}", usage_patch=_make_wr_level_usage(w))
        _record(s)

    # ------------------------------------------------------------------
    # MECHANISM B — velocity / role-change detector
    # ------------------------------------------------------------------
    print("\n=== Mechanism B: WR route-velocity role-change detector ===")

    def _make_wr_velocity_usage(
        collapse_thr: float,
        collapse_mult: float,
        boost_thr: float,
        boost_mult: float,
        signal: str = "delta",
    ):
        """Apply an asymmetric multiplier when route velocity crosses a threshold.

        For WR rows where the lagged signal (delta or slope) is below
        ``collapse_thr``, apply ``collapse_mult`` on top of the base usage
        multiplier.  Where the signal exceeds ``boost_thr``, apply
        ``boost_mult``.  All other WRs and all non-WR positions are unchanged.

        Args:
            collapse_thr: Negative threshold; rows below this are collapsing.
            collapse_mult: Multiplier for collapsing WRs (< 1.0).
            boost_thr: Positive threshold; rows above this are rising.
            boost_mult: Multiplier for rising WRs (> 1.0).
            signal: ``"delta"`` uses route_rate_delta; ``"slope"`` uses
                route_rate_slope.

        Returns:
            Patched _usage_multiplier function.
        """
        lut = route_lut_delta if signal == "delta" else route_lut_slope

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            if position != "WR" or "player_id" not in df.columns:
                return base
            season_col = (
                df["proj_season"] if "proj_season" in df.columns else df["season"]
            )
            week_col = df["proj_week"] if "proj_week" in df.columns else df["week"]
            keys = list(zip(df["player_id"], season_col, week_col))
            sig_vals = pd.Series(
                [lut.get(k, np.nan) for k in keys], index=df.index
            )
            result = base.copy()
            collapsing = sig_vals.notna() & (sig_vals < collapse_thr)
            if collapsing.any():
                result.loc[collapsing] = (
                    result.loc[collapsing] * collapse_mult
                ).clip(0.70, 1.15)
            rising = sig_vals.notna() & (sig_vals > boost_thr)
            if rising.any():
                result.loc[rising] = (
                    result.loc[rising] * boost_mult
                ).clip(0.80, 1.25)
            return result

        return patched

    print("--- B1: collapse-only sweep (boost disabled) on delta signal ---")
    for collapse_thr in [-0.05, -0.08, -0.10, -0.12]:
        for collapse_mult in [0.70, 0.75, 0.80, 0.85]:
            label = f"mech_B1_delta_cthr={collapse_thr}_cmult={collapse_mult}"
            s = _run(
                label,
                usage_patch=_make_wr_velocity_usage(
                    collapse_thr=collapse_thr,
                    collapse_mult=collapse_mult,
                    boost_thr=999.0,
                    boost_mult=1.0,
                    signal="delta",
                ),
            )
            _record(s)

    print("--- B2: boost-only sweep (collapse disabled) on delta signal ---")
    for boost_thr in [0.05, 0.08, 0.10, 0.12]:
        for boost_mult in [1.05, 1.10, 1.15]:
            label = f"mech_B2_delta_bthr={boost_thr}_bmult={boost_mult}"
            s = _run(
                label,
                usage_patch=_make_wr_velocity_usage(
                    collapse_thr=-999.0,
                    collapse_mult=1.0,
                    boost_thr=boost_thr,
                    boost_mult=boost_mult,
                    signal="delta",
                ),
            )
            _record(s)

    print("--- B3: collapse-only sweep on slope signal ---")
    for collapse_thr in [-0.03, -0.05, -0.08]:
        for collapse_mult in [0.75, 0.80, 0.85]:
            label = f"mech_B3_slope_cthr={collapse_thr}_cmult={collapse_mult}"
            s = _run(
                label,
                usage_patch=_make_wr_velocity_usage(
                    collapse_thr=collapse_thr,
                    collapse_mult=collapse_mult,
                    boost_thr=999.0,
                    boost_mult=1.0,
                    signal="slope",
                ),
            )
            _record(s)

    print("--- B4: joint sweep (best collapse + best boost) ---")
    df_so_far = pd.DataFrame(rows)
    b1b3 = df_so_far[
        df_so_far["label"].str.startswith("mech_B1")
        | df_so_far["label"].str.startswith("mech_B3")
    ]
    if not b1b3.empty and "WR_mae" in b1b3.columns:
        top_collapse = b1b3.nsmallest(5, "WR_mae")
        for _, crow in top_collapse.iterrows():
            lbl = str(crow["label"])
            sig = "slope" if "slope" in lbl else "delta"
            try:
                cthr = float(lbl.split("cthr=")[1].split("_")[0])
                cmult = float(lbl.split("cmult=")[1])
            except (IndexError, ValueError):
                continue
            for boost_thr in [0.08, 0.10]:
                for boost_mult in [1.10, 1.15]:
                    joint_label = (
                        f"mech_B4_{sig}_c{cthr}_m{cmult}_b{boost_thr}_bm{boost_mult}"
                    )
                    s = _run(
                        joint_label,
                        usage_patch=_make_wr_velocity_usage(
                            collapse_thr=cthr,
                            collapse_mult=cmult,
                            boost_thr=boost_thr,
                            boost_mult=boost_mult,
                            signal=sig,
                        ),
                    )
                    _record(s)

    # ------------------------------------------------------------------
    # Save results and print summary
    # ------------------------------------------------------------------
    df_out = pd.DataFrame(rows)
    out_path = os.path.join(CACHE_DIR, "sweep_wr_route.csv")
    df_out.to_csv(out_path, index=False)
    print(f"\nSaved sweep results to {out_path}")

    print(
        f"\n=== Summary: baseline WR MAE={baseline_wr_mae:.4f} "
        f"WR_rho={baseline_wr_rho:.4f} ==="
    )
    print(
        "Gate: improve >=0.03 WR MAE OR >=0.02 Spearman with no MAE regression\n"
    )

    if "WR_mae" in df_out.columns:
        non_base = df_out[df_out["label"] != "baseline_production"].copy()
        non_base["wr_delta"] = baseline_wr_mae - non_base["WR_mae"]
        non_base["rho_delta"] = non_base.get(
            "WR_spearman", pd.Series(float("nan"), index=non_base.index)
        ) - baseline_wr_rho
        ranked = non_base.sort_values("WR_mae").head(10)
        print("Top-10 configs by WR MAE (lower is better):")
        print(
            f"  {'Label':<62} {'WR_MAE':>8} {'DMAE':>7} {'WR_rho':>8} "
            f"{'Drho':>7} {'QB':>7} {'RB':>7} {'TE':>7}"
        )
        for _, r in ranked.iterrows():
            print(
                f"  {str(r['label']):<62} "
                f"{r.get('WR_mae', float('nan')):>8.4f} "
                f"{r.get('wr_delta', float('nan')):>+7.4f} "
                f"{r.get('WR_spearman', float('nan')):>8.4f} "
                f"{r.get('rho_delta', float('nan')):>+7.4f} "
                f"{r.get('QB_mae', float('nan')):>7.4f} "
                f"{r.get('RB_mae', float('nan')):>7.4f} "
                f"{r.get('TE_mae', float('nan')):>7.4f}"
            )

        mae_gate = non_base[non_base["wr_delta"] >= 0.03]
        rho_col = "WR_spearman" if "WR_spearman" in non_base.columns else None
        rho_gate = (
            non_base[
                (non_base["WR_spearman"] - baseline_wr_rho >= 0.02)
                & (non_base["WR_mae"] <= baseline_wr_mae + 0.001)
            ]
            if rho_col
            else pd.DataFrame()
        )

        print("\n=== GATE VERDICT ===")
        if not mae_gate.empty:
            best = mae_gate.loc[mae_gate["wr_delta"].idxmax()]
            print(
                f"PASS (MAE gate): {best['label']}  "
                f"WR MAE {baseline_wr_mae:.4f} -> {best['WR_mae']:.4f} "
                f"(delta {best['wr_delta']:+.4f})"
            )
        elif not rho_gate.empty:
            best = rho_gate.loc[rho_gate["WR_spearman"].idxmax()]
            rho_d = float(best["WR_spearman"]) - baseline_wr_rho
            print(
                f"PASS (Spearman gate): {best['label']}  "
                f"WR rho {baseline_wr_rho:.4f} -> {best['WR_spearman']:.4f} "
                f"(delta {rho_d:+.4f})"
            )
        else:
            best_mae_d = float(non_base["wr_delta"].max())
            best_rho_d = (
                float((non_base["WR_spearman"] - baseline_wr_rho).max())
                if rho_col
                else float("nan")
            )
            print(
                f"KILL: no config cleared the gate "
                f"(best WR MAE delta={best_mae_d:+.4f}, need >=+0.03; "
                f"best rho delta={best_rho_d:+.4f}, need >=+0.02)."
            )


def cmd_consensus_gap_wr_route() -> None:
    """Compute consensus gap + Spearman before/after WR route signals.

    Uses the best WR route config from sweep_wr_route.csv (if the gate was
    cleared) or the best-performing config (if killed, for reference).

    Joins per-row projections against Sleeper consensus
    (data/silver/external_projections/), filtering to consensus_proj >= 5.

    Outputs:
      - Console: gap table by position + WR w3-6 breakdown + Spearman
      - CSV: output/heuristic_lab_cache/consensus_gap_wr_route.csv
    """
    import glob as globmod
    from scipy.stats import spearmanr  # type: ignore

    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    omap = build_upcoming_opponent_map(sched)
    strength = build_defense_strength(weekly, sched, window=8)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))
    prior_blend = _build_production_blend_fn(weekly, manifest)

    seasons = sorted({e["season"] for e in manifest})
    route = _load_route_features(seasons)

    route_lut_delta = (
        route.set_index(["player_id", "season", "week"])["route_rate_delta"]
        if not route.empty
        else pd.Series(dtype=float)
    )
    route_lut_slope = (
        route.set_index(["player_id", "season", "week"])["route_rate_slope"]
        if not route.empty
        else pd.Series(dtype=float)
    )
    route_lut_trail4 = (
        route.set_index(["player_id", "season", "week"])["route_rate_trail4"]
        if not route.empty
        else pd.Series(dtype=float)
    )

    orig_usage = projection_engine._usage_multiplier
    best_config_label = "baseline_production"
    gate_cleared = False
    best_usage_patch = None

    sweep_csv = os.path.join(CACHE_DIR, "sweep_wr_route.csv")
    baseline_wr_mae = float("nan")
    baseline_wr_rho = float("nan")

    if os.path.exists(sweep_csv):
        sweep_df = pd.read_csv(sweep_csv)
        base_row = sweep_df[sweep_df["label"] == "baseline_production"]
        if not base_row.empty:
            baseline_wr_mae = float(base_row["WR_mae"].iloc[0])
            baseline_wr_rho = (
                float(base_row["WR_spearman"].iloc[0])
                if "WR_spearman" in base_row.columns
                else float("nan")
            )
        non_base = sweep_df[sweep_df["label"] != "baseline_production"].copy()
        if not non_base.empty and "WR_mae" in non_base.columns:
            non_base["wr_delta"] = baseline_wr_mae - non_base["WR_mae"]
            mae_gate = non_base[non_base["wr_delta"] >= 0.03]
            rho_gate = pd.DataFrame()
            if "WR_spearman" in non_base.columns:
                rho_gate = non_base[
                    (non_base["WR_spearman"] - baseline_wr_rho >= 0.02)
                    & (non_base["WR_mae"] <= baseline_wr_mae + 0.001)
                ]
            if not mae_gate.empty:
                best_lbl = mae_gate.loc[mae_gate["wr_delta"].idxmax(), "label"]
                best_config_label = best_lbl
                gate_cleared = True
                print(f"Using MAE gate-cleared config: {best_config_label}")
            elif not rho_gate.empty:
                best_lbl = rho_gate.loc[rho_gate["WR_spearman"].idxmax(), "label"]
                best_config_label = best_lbl
                gate_cleared = True
                print(f"Using Spearman gate-cleared config: {best_config_label}")
            else:
                best_lbl = non_base.loc[non_base["WR_mae"].idxmin(), "label"]
                best_config_label = best_lbl
                print(
                    f"No gate cleared — using best-performing for reference: "
                    f"{best_config_label}"
                )

    def _parse_usage_patch(label: str):
        """Reconstruct a usage patch function from a sweep label string.

        Args:
            label: Label string from sweep_wr_route.csv.

        Returns:
            Patched usage function or None if label cannot be parsed.
        """
        if "mech_A" in label:
            try:
                w = float(label.split("w=")[1])
            except (IndexError, ValueError):
                return None

            def _lvl(df: pd.DataFrame, position: str) -> pd.Series:
                base = orig_usage(df, position)
                if position != "WR" or "player_id" not in df.columns:
                    return base
                sc = df.get("proj_season", df["season"])
                wc = df.get("proj_week", df["week"])
                keys = list(zip(df["player_id"], sc, wc))
                rr = pd.Series(
                    [route_lut_trail4.get(k, np.nan) for k in keys], index=df.index
                )
                if rr.notna().sum() < 5:
                    return base
                rr_pct = rr.rank(pct=True)
                bp = (base - 0.80) / 0.35
                blended = (1 - w) * bp + w * rr_pct.fillna(bp)
                return (0.80 + 0.35 * blended).clip(0.80, 1.15)

            return _lvl

        if "mech_B" in label:
            sig = "slope" if "slope" in label else "delta"
            lut = route_lut_slope if sig == "slope" else route_lut_delta
            try:
                cthr = float(label.split("cthr=")[1].split("_")[0])
                cmult = float(label.split("cmult=")[1].split("_")[0] if "_" in label.split("cmult=")[1] else label.split("cmult=")[1])
            except (IndexError, ValueError):
                cthr, cmult = -999.0, 1.0
            try:
                bthr = float(label.split("bthr=")[1].split("_")[0]) if "bthr=" in label else 999.0
                bmult = float(label.split("bmult=")[1]) if "bmult=" in label else 1.0
            except (IndexError, ValueError):
                bthr, bmult = 999.0, 1.0
            # Handle mech_B4 label format: c{val}_m{val}_b{val}_bm{val}
            if "mech_B4" in label:
                try:
                    parts = label.split("_")
                    for i, p in enumerate(parts):
                        if p.startswith("c") and not p.startswith("cm"):
                            cthr = float(p[1:])
                        elif p.startswith("m") and not p.startswith("mech"):
                            cmult = float(p[1:])
                        elif p.startswith("b") and not p.startswith("bm"):
                            bthr = float(p[1:])
                        elif p.startswith("bm"):
                            bmult = float(p[2:])
                except (IndexError, ValueError):
                    pass

            _cthr, _cmult, _bthr, _bmult, _lut = cthr, cmult, bthr, bmult, lut

            def _vel(
                df: pd.DataFrame,
                position: str,
                __cthr=_cthr,
                __cmult=_cmult,
                __bthr=_bthr,
                __bmult=_bmult,
                __lut=_lut,
            ) -> pd.Series:
                base = orig_usage(df, position)
                if position != "WR" or "player_id" not in df.columns:
                    return base
                sc = df.get("proj_season", df["season"])
                wc = df.get("proj_week", df["week"])
                keys = list(zip(df["player_id"], sc, wc))
                sv = pd.Series([__lut.get(k, np.nan) for k in keys], index=df.index)
                result = base.copy()
                collapsing = sv.notna() & (sv < __cthr)
                if collapsing.any():
                    result.loc[collapsing] = (
                        result.loc[collapsing] * __cmult
                    ).clip(0.70, 1.15)
                rising = sv.notna() & (sv > __bthr)
                if rising.any():
                    result.loc[rising] = (
                        result.loc[rising] * __bmult
                    ).clip(0.80, 1.25)
                return result

            return _vel

        return None

    best_usage_patch = _parse_usage_patch(best_config_label)

    # --- Run projections ---
    def _get_results(usage_patch=None) -> pd.DataFrame:
        if usage_patch is not None:
            projection_engine._usage_multiplier = usage_patch
        try:
            return evaluate_config(
                manifest, matchup_patch=matchup, prior_blend_fn=prior_blend
            )
        finally:
            projection_engine._usage_multiplier = orig_usage

    base_results = _get_results()
    best_results = _get_results(best_usage_patch)

    # --- Load consensus ---
    silver_root = os.path.join(PROJECT_ROOT, "data", "silver", "external_projections")
    consensus_rows = []
    for season in seasons:
        for week in range(3, 19):
            week_dir = os.path.join(
                silver_root, f"season={season}", f"week={week:02d}"
            )
            files = sorted(
                __import__("glob").glob(os.path.join(week_dir, "*.parquet"))
            )
            if not files:
                continue
            df = pd.read_parquet(files[-1])
            df = df[(df["source"] == "sleeper") & (df["scoring_format"] == SCORING)]
            df = df[df["position"].isin(POSITIONS)]
            if df.empty:
                continue
            df = df.rename(columns={"projected_points": "consensus_proj"})
            df["season"] = season
            df["week"] = week
            consensus_rows.append(
                df[["player_id", "season", "week", "consensus_proj"]]
            )

    if not consensus_rows:
        print("No consensus data found.")
        return

    consensus = pd.concat(consensus_rows, ignore_index=True).drop_duplicates(
        subset=["player_id", "season", "week"]
    )
    print(f"Consensus rows: {len(consensus)}")

    early_weeks = [3, 4, 5, 6]

    def _gap_df(results: pd.DataFrame, label: str) -> pd.DataFrame:
        if "player_id" not in results.columns:
            return pd.DataFrame()
        merged = results.merge(
            consensus, on=["player_id", "season", "week"], how="inner"
        )
        merged = merged[merged["consensus_proj"] >= 5.0].copy()
        merged["our_mae"] = (
            merged["projected_points"] - merged["actual_points"]
        ).abs()
        merged["cons_mae"] = (
            merged["consensus_proj"] - merged["actual_points"]
        ).abs()
        merged["gap"] = merged["our_mae"] - merged["cons_mae"]
        merged["config"] = label
        return merged

    base_gap = _gap_df(base_results, "baseline_production")
    best_gap = _gap_df(best_results, best_config_label)
    combined = pd.concat([base_gap, best_gap], ignore_index=True)

    def _print_gap(df: pd.DataFrame, cfg: str) -> None:
        sub = df[df["config"] == cfg]
        print(f"\n{cfg} (consensus_proj >= 5):")
        print(
            f"  {'Pos':<8} {'n':>6} {'Our MAE':>9} {'Cons MAE':>10} "
            f"{'Gap':>8} {'WR rho':>8}"
        )
        for pos in POSITIONS:
            p = sub[sub["position"] == pos]
            if p.empty:
                continue
            rho = float("nan")
            if pos == "WR" and len(p) >= 10:
                rho, _ = spearmanr(p["projected_points"], p["actual_points"])
            print(
                f"  {pos:<8} {len(p):>6} {p['our_mae'].mean():>9.3f} "
                f"{p['cons_mae'].mean():>10.3f} {p['gap'].mean():>+8.3f} "
                f"{rho:>8.4f}"
            )
        wr_early = sub[
            (sub["position"] == "WR") & (sub["week"].isin(early_weeks))
        ]
        if not wr_early.empty:
            rho_e = float("nan")
            if len(wr_early) >= 5:
                rho_e, _ = spearmanr(
                    wr_early["projected_points"], wr_early["actual_points"]
                )
            print(
                f"  {'WR w3-6':<8} {len(wr_early):>6} "
                f"{wr_early['our_mae'].mean():>9.3f} "
                f"{wr_early['cons_mae'].mean():>10.3f} "
                f"{wr_early['gap'].mean():>+8.3f} {rho_e:>8.4f}"
            )

    _print_gap(combined, "baseline_production")
    _print_gap(combined, best_config_label)

    print(f"\nGate cleared: {gate_cleared}")
    if not base_gap.empty and not best_gap.empty:
        wr_base = base_gap[base_gap["position"] == "WR"]
        wr_best = best_gap[best_gap["position"] == "WR"]
        gap_before = float(wr_base["gap"].mean()) if not wr_base.empty else float("nan")
        gap_after = float(wr_best["gap"].mean()) if not wr_best.empty else float("nan")
        rho_base = float("nan")
        rho_best = float("nan")
        if len(wr_base) >= 10:
            rho_base, _ = spearmanr(wr_base["projected_points"], wr_base["actual_points"])
        if len(wr_best) >= 10:
            rho_best, _ = spearmanr(wr_best["projected_points"], wr_best["actual_points"])
        print(f"WR consensus gap: {gap_before:+.3f} -> {gap_after:+.3f}  delta={gap_after - gap_before:+.3f}")
        print(f"WR Spearman:      {rho_base:.4f} -> {rho_best:.4f}  delta={rho_best - rho_base:+.4f}")

    out = os.path.join(CACHE_DIR, "consensus_gap_wr_route.csv")
    combined.to_csv(out, index=False)
    print(f"\nSaved consensus gap analysis to {out}")


def _compute_per_position_spearman(results: pd.DataFrame) -> Dict[str, float]:
    """Compute mean within-position-week Spearman rank correlation.

    The plan's primary gate metric for rank-ordering experiments.  For each
    (position, season, week) with >= 5 players, computes Spearman between
    projected_points and actual_points, then averages across all qualifying
    weeks.

    Args:
        results: Per-row results DataFrame from evaluate_config with columns
            position, season, week, projected_points, actual_points.

    Returns:
        Dict with keys "{POS}_spearman_weekly" for QB/RB/WR/TE containing the
        mean within-week Spearman value.  NaN when no qualifying weeks exist.
    """
    from scipy.stats import spearmanr  # type: ignore

    out: Dict[str, float] = {}
    for pos in POSITIONS:
        pos_df = results[results["position"] == pos]
        if pos_df.empty:
            out[f"{pos}_spearman_weekly"] = float("nan")
            continue
        week_corrs = []
        for (season, week), grp in pos_df.groupby(["season", "week"]):
            if len(grp) < 5:
                continue
            rho, _ = spearmanr(grp["projected_points"], grp["actual_points"])
            if np.isfinite(rho):
                week_corrs.append(float(rho))
        out[f"{pos}_spearman_weekly"] = (
            float(np.mean(week_corrs)) if week_corrs else float("nan")
        )
    return out


def _summarize_with_spearman(results: pd.DataFrame) -> Dict:
    """Summarize results including both MAE and per-position mean weekly Spearman.

    Extends summarize() with _compute_per_position_spearman().

    Args:
        results: Per-row results DataFrame from evaluate_config.

    Returns:
        Summary dict with overall_mae, {POS}_mae, {POS}_spearman_weekly keys.
    """
    s = summarize(results)
    s.update(_compute_per_position_spearman(results))
    return s


def _fmt_with_spearman(s: Dict) -> str:
    """Format a summary dict including Spearman values for RB and WR.

    Args:
        s: Summary dict from _summarize_with_spearman.

    Returns:
        Human-readable string for console output.
    """
    base = _fmt(s)
    rb_rho = s.get("RB_spearman_weekly", float("nan"))
    wr_rho = s.get("WR_spearman_weekly", float("nan"))
    return f"{base} | RB_rho={rb_rho:.4f} WR_rho={wr_rho:.4f}"


# ---------------------------------------------------------------------------
# Experiment 1: TPRR (Targets Per Route Run) sweep
# ---------------------------------------------------------------------------


def _load_tprr_features(seasons: List[int], weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Build TPRR features for the given seasons from Silver route parquets.

    Loads the most-recent graph_route_participation_*.parquet for each season,
    then calls compute_tprr_features to produce tprr_trail4, tprr_trail4_slope,
    and tprr_x_route_slope (all strictly lagged).

    Args:
        seasons: List of evaluation seasons (e.g. [2022, 2023, 2024]).
        weekly_df: Bronze weekly DataFrame (must have player_id, season, week,
            targets).

    Returns:
        DataFrame with TPRR features (possibly empty if no route parquets found).
    """
    import glob as globmod
    from graph_route_participation import compute_tprr_features  # noqa: E402

    route_frames = []
    for season in seasons:
        files = sorted(
            globmod.glob(
                os.path.join(
                    PROJECT_ROOT,
                    "data",
                    "silver",
                    "graph_features",
                    f"season={season}",
                    "graph_route_participation_*.parquet",
                )
            )
        )
        if files:
            route_frames.append(pd.read_parquet(files[-1]))

    if not route_frames:
        logger.warning("No route participation parquets found for seasons %s", seasons)
        return pd.DataFrame()

    route_df = pd.concat(route_frames, ignore_index=True)
    tprr_df = compute_tprr_features(route_df, weekly_df)
    print(
        f"TPRR features built: {len(tprr_df)} rows, "
        f"tprr_trail4 non-null: {tprr_df['tprr_trail4'].notna().sum() if not tprr_df.empty else 0}"
    )
    return tprr_df


def cmd_sweep_tprr() -> None:
    """Experiment 1: Sweep TPRR-based WR/TE usage multiplier adjustments.

    TPRR (targets per route run) is the stickiest WR role-quality signal
    (YoY r≈0.65).  This is distinct from target_share (different denominator:
    routes vs team pass attempts) and from route_rate_trail4 (measures volume
    of routes, not conversion).

    Three candidate mechanisms are swept, all WR/TE only:

    **Mechanism 1 — TPRR percentile blend into usage multiplier:**
        Blend tprr_trail4 percentile (weight w) into the WR/TE usage
        multiplier alongside target_share.  Expected to be null (same as
        route-rate level blend); included to confirm.

    **Mechanism 2 — TPRR × route-slope interaction boost/collapse:**
        When tprr_x_route_slope exceeds a threshold (rising TPRR + growing
        routes = classic breakout) or falls below a threshold (declining TPRR
        + shrinking routes = fade), apply a directional multiplier.
        Grid: interaction threshold in {-0.03, -0.02, 0.02, 0.03, 0.05};
        multipliers in {0.80-0.95 for negative, 1.05-1.15 for positive}.

    **Mechanism 3 — Early-season TPRR anchor (< 5 recent games):**
        For players with fewer than 5 rolling-window games, blend heuristic
        projection toward a TPRR-implied target count.  TPRR-implied targets
        = tprr_trail4 * team_dropbacks_est (position-mean dropbacks).
        Shrinks the prior-season bias for WRs with short in-season history.
        Sweep anchor weight in {0.15, 0.25, 0.35, 0.50}.

    Gates (from plan): ship-candidate if MAE improves >= 0.02 at the position
    OR mean within-position-week Spearman improves >= 0.015 with MAE not worse
    by > 0.005.

    Note: Spearman is the first-class gate for this experiment because the
    plan's RB/WR Spearman gaps (−0.080, −0.056) are the primary target.

    Outputs:
        - Console: per-config table with WR/TE MAE + WR/TE weekly Spearman
        - CSV: output/heuristic_lab_cache/sweep_tprr.csv
        - Gate verdict: PASS/KILL per plan criteria
    """
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    strength = build_defense_strength(weekly, sched, window=8)
    omap = build_upcoming_opponent_map(sched)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))
    prior_blend = _build_production_blend_fn(weekly, manifest)

    seasons = sorted({e["season"] for e in manifest})
    tprr_df = _load_tprr_features(seasons, weekly)

    if tprr_df.empty:
        print("No TPRR features available — aborting sweep.")
        return

    # Build TPRR lookup tables keyed at the PROJECTED week (features are
    # lagged through W-1 inside compute_tprr_features, so the key
    # (player_id, proj_season, proj_week) reads the prior-week TPRR).
    tprr_lut_trail4 = tprr_df.set_index(["player_id", "season", "week"])["tprr_trail4"]
    tprr_lut_slope = tprr_df.set_index(["player_id", "season", "week"])[
        "tprr_trail4_slope"
    ]
    tprr_lut_xslope = tprr_df.set_index(["player_id", "season", "week"])[
        "tprr_x_route_slope"
    ]

    # Load route data for mechanism 3 (team dropbacks estimate)
    route = _load_route_features(seasons)
    route_lut_team_db = pd.Series(dtype=float)
    if not route.empty and "team_dropbacks" in route.columns:
        route_lut_team_db = route.set_index(["player_id", "season", "week"])[
            "team_dropbacks"
        ]

    orig_usage = projection_engine._usage_multiplier

    def _run(label: str, usage_patch=None) -> Dict:
        pe_usage = usage_patch if usage_patch is not None else orig_usage
        projection_engine._usage_multiplier = pe_usage
        try:
            results = evaluate_config(
                manifest,
                matchup_patch=matchup,
                prior_blend_fn=prior_blend,
            )
        finally:
            projection_engine._usage_multiplier = orig_usage
        s = _summarize_with_spearman(results)
        s["label"] = label
        return s

    rows: List[Dict] = []

    def _record(s: Dict) -> None:
        rows.append(s)
        wr_rho = s.get("WR_spearman_weekly", float("nan"))
        te_rho = s.get("TE_spearman_weekly", float("nan"))
        rb_rho = s.get("RB_spearman_weekly", float("nan"))
        print(
            f"{s['label']:<60} "
            f"WR:{s.get('WR_mae', float('nan')):.4f} "
            f"TE:{s.get('TE_mae', float('nan')):.4f} "
            f"RB:{s.get('RB_mae', float('nan')):.4f} "
            f"WR_rho={wr_rho:.4f} TE_rho={te_rho:.4f} RB_rho={rb_rho:.4f}"
        )

    # --- Baseline ---
    base_s = _run("baseline_production")
    _record(base_s)
    baseline_wr_mae = base_s.get("WR_mae", float("nan"))
    baseline_wr_rho = base_s.get("WR_spearman_weekly", float("nan"))
    baseline_rb_mae = base_s.get("RB_mae", float("nan"))
    baseline_rb_rho = base_s.get("RB_spearman_weekly", float("nan"))
    baseline_te_mae = base_s.get("TE_mae", float("nan"))
    print(
        f"\nBaseline — WR MAE: {baseline_wr_mae:.4f}  WR Spearman: {baseline_wr_rho:.4f}"
        f"  |  RB MAE: {baseline_rb_mae:.4f}  RB Spearman: {baseline_rb_rho:.4f}"
        f"  |  TE MAE: {baseline_te_mae:.4f}"
    )
    print(
        "Gates: ship if MAE improves >= 0.02 at position "
        "OR Spearman improves >= 0.015 with MAE not worse by > 0.005"
    )

    # -----------------------------------------------------------------------
    # MECHANISM 1 — TPRR percentile blend into WR/TE usage multiplier
    # -----------------------------------------------------------------------
    print("\n=== Mechanism 1: TPRR trail4 percentile blend into WR/TE usage mult ===")

    def _make_tprr_level_usage(w: float, positions: List[str]) -> object:
        """Blend tprr_trail4 percentile (weight w) into usage multiplier.

        Args:
            w: Blend weight for TPRR percentile (0.0 = pure target_share).
            positions: Positions to apply the blend to (e.g. ['WR', 'TE']).

        Returns:
            Patched _usage_multiplier function.
        """

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            if position not in positions or w == 0.0 or "player_id" not in df.columns:
                return base
            sc = df.get("proj_season", df["season"])
            wc = df.get("proj_week", df["week"])
            keys = list(zip(df["player_id"], sc, wc))
            tprr_vals = pd.Series(
                [tprr_lut_trail4.get(k, np.nan) for k in keys], index=df.index
            )
            if tprr_vals.notna().sum() < 5:
                return base
            tprr_pct = tprr_vals.rank(pct=True)
            base_pct = (base - 0.80) / 0.35
            blended = (1 - w) * base_pct + w * tprr_pct.fillna(base_pct)
            return (0.80 + 0.35 * blended).clip(0.80, 1.15)

        return patched

    for pos_set, pos_label in [
        (["WR"], "WR"),
        (["TE"], "TE"),
        (["WR", "TE"], "WR+TE"),
    ]:
        for w in [0.25, 0.5, 0.75]:
            label = f"tprr_m1_{pos_label}_w={w}"
            s = _run(label, usage_patch=_make_tprr_level_usage(w, pos_set))
            _record(s)

    # -----------------------------------------------------------------------
    # MECHANISM 2 — TPRR × route-slope interaction
    # -----------------------------------------------------------------------
    print("\n=== Mechanism 2: TPRR × route-slope interaction (breakout/fade) ===")

    def _make_tprr_interaction_usage(
        neg_thr: float,
        neg_mult: float,
        pos_thr: float,
        pos_mult: float,
        positions: List[str],
        signal: str = "xslope",
    ) -> object:
        """Apply directional multiplier based on TPRR interaction signal.

        Uses tprr_x_route_slope (tprr_trail4 * route_rate_slope) or
        tprr_trail4_slope depending on ``signal``.

        Args:
            neg_thr: Negative threshold; rows below get neg_mult applied.
            neg_mult: Multiplier for fading players (< 1.0).
            pos_thr: Positive threshold; rows above get pos_mult applied.
            pos_mult: Multiplier for breaking-out players (> 1.0).
            positions: Positions to apply to.
            signal: 'xslope' uses tprr_x_route_slope; 'slope' uses
                tprr_trail4_slope.

        Returns:
            Patched _usage_multiplier function.
        """
        lut = tprr_lut_xslope if signal == "xslope" else tprr_lut_slope

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            if position not in positions or "player_id" not in df.columns:
                return base
            sc = df.get("proj_season", df["season"])
            wc = df.get("proj_week", df["week"])
            keys = list(zip(df["player_id"], sc, wc))
            sig_vals = pd.Series(
                [lut.get(k, np.nan) for k in keys], index=df.index
            )
            result = base.copy()
            fading = sig_vals.notna() & (sig_vals < neg_thr)
            if fading.any():
                result.loc[fading] = (
                    result.loc[fading] * neg_mult
                ).clip(0.70, 1.15)
            breaking = sig_vals.notna() & (sig_vals > pos_thr)
            if breaking.any():
                result.loc[breaking] = (
                    result.loc[breaking] * pos_mult
                ).clip(0.80, 1.25)
            return result

        return patched

    # 2a: xslope signal (tprr_trail4 * route_rate_slope), collapse-only
    print("--- 2a: xslope signal, collapse/fade only ---")
    for neg_thr, neg_mult in [(-0.02, 0.85), (-0.02, 0.90), (-0.03, 0.85), (-0.03, 0.90)]:
        for pos_set, pos_label in [(["WR"], "WR"), (["WR", "TE"], "WR+TE")]:
            label = f"tprr_m2a_{pos_label}_xthr={neg_thr}_xm={neg_mult}"
            s = _run(
                label,
                usage_patch=_make_tprr_interaction_usage(
                    neg_thr=neg_thr,
                    neg_mult=neg_mult,
                    pos_thr=999.0,
                    pos_mult=1.0,
                    positions=pos_set,
                    signal="xslope",
                ),
            )
            _record(s)

    # 2b: xslope signal, boost-only
    print("--- 2b: xslope signal, boost/breakout only ---")
    for pos_thr, pos_mult in [(0.02, 1.10), (0.02, 1.15), (0.03, 1.10), (0.03, 1.15)]:
        for pos_set, pos_label in [(["WR"], "WR"), (["WR", "TE"], "WR+TE")]:
            label = f"tprr_m2b_{pos_label}_xthr={pos_thr}_xm={pos_mult}"
            s = _run(
                label,
                usage_patch=_make_tprr_interaction_usage(
                    neg_thr=-999.0,
                    neg_mult=1.0,
                    pos_thr=pos_thr,
                    pos_mult=pos_mult,
                    positions=pos_set,
                    signal="xslope",
                ),
            )
            _record(s)

    # 2c: tprr_trail4_slope signal (pure TPRR slope, no route-rate cross)
    print("--- 2c: tprr_trail4_slope signal (pure TPRR velocity), collapse only ---")
    for neg_thr, neg_mult in [(-0.02, 0.85), (-0.02, 0.90), (-0.03, 0.85)]:
        label = f"tprr_m2c_WR_slope_thr={neg_thr}_m={neg_mult}"
        s = _run(
            label,
            usage_patch=_make_tprr_interaction_usage(
                neg_thr=neg_thr,
                neg_mult=neg_mult,
                pos_thr=999.0,
                pos_mult=1.0,
                positions=["WR"],
                signal="slope",
            ),
        )
        _record(s)

    # -----------------------------------------------------------------------
    # MECHANISM 3 — Early-season TPRR anchor (< n_games recent weeks)
    # -----------------------------------------------------------------------
    print("\n=== Mechanism 3: TPRR-implied target anchor (early season / sparse history) ===")
    # Team dropbacks estimate: median team_dropbacks per week from route data
    # (position-agnostic proxy; real team dropbacks vary but median ~34)
    LEAGUE_MEAN_DROPBACKS = 34.0  # typical team dropbacks per game

    def _make_tprr_anchor_usage(
        anchor_weight: float,
        n_games_thr: int,
        positions: List[str],
    ) -> object:
        """Blend TPRR-implied projection toward heuristic for sparse-history rows.

        For players with fewer than n_games_thr valid rolling windows,
        override the base usage multiplier toward one derived from
        tprr_trail4 * team_dropbacks_est / team_targets_est.

        Mechanism: tprr_trail4 * LEAGUE_MEAN_DROPBACKS gives an implied
        weekly target count.  Convert to a usage-mult proxy via the same
        normalization as target_share.  Blend anchor_weight of this implied
        usage with (1 - anchor_weight) of the base multiplier.

        Args:
            anchor_weight: Weight for TPRR-implied usage (0 = pure base).
            n_games_thr: Apply anchor only when roll3 column suggests fewer
                than this many recent games (proxied by NaN count in rolling
                stats: if roll3 is NaN but prior TPRR exists, player has
                sparse in-season history).
            positions: Positions to apply to.

        Returns:
            Patched _usage_multiplier function.
        """

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            if position not in positions or "player_id" not in df.columns:
                return base
            sc = df.get("proj_season", df["season"])
            wc = df.get("proj_week", df["week"])
            keys = list(zip(df["player_id"], sc, wc))
            tprr_vals = pd.Series(
                [tprr_lut_trail4.get(k, np.nan) for k in keys], index=df.index
            )
            if tprr_vals.notna().sum() < 3:
                return base

            # Identify sparse-history rows: use a proxy of roll3 stats being
            # NaN (player has < 3 games of data in current season window)
            roll3_col = "targets_roll3" if "targets_roll3" in df.columns else None
            if roll3_col is not None:
                sparse_mask = df[roll3_col].isna() & tprr_vals.notna()
            else:
                # Fallback: apply to all rows with valid TPRR
                sparse_mask = tprr_vals.notna()

            if not sparse_mask.any():
                return base

            # Implied usage percentile from TPRR
            implied_targets = tprr_vals * LEAGUE_MEAN_DROPBACKS
            # Normalize to a usage multiplier in [0.80, 1.15] range
            # via team-level quantile normalization
            implied_pct = implied_targets.rank(pct=True)
            implied_mult = (0.80 + 0.35 * implied_pct).clip(0.80, 1.15)

            result = base.copy()
            result.loc[sparse_mask] = (
                (1 - anchor_weight) * base.loc[sparse_mask]
                + anchor_weight * implied_mult.loc[sparse_mask]
            )
            return result

        return patched

    for pos_set, pos_label in [(["WR"], "WR"), (["WR", "TE"], "WR+TE")]:
        for w in [0.15, 0.25, 0.35]:
            for n_thr in [3, 5]:
                label = f"tprr_m3_{pos_label}_w={w}_n={n_thr}"
                s = _run(
                    label,
                    usage_patch=_make_tprr_anchor_usage(
                        anchor_weight=w,
                        n_games_thr=n_thr,
                        positions=pos_set,
                    ),
                )
                _record(s)

    # -----------------------------------------------------------------------
    # Save results and print summary
    # -----------------------------------------------------------------------
    df_out = pd.DataFrame(rows)
    out_path = os.path.join(CACHE_DIR, "sweep_tprr.csv")
    df_out.to_csv(out_path, index=False)
    print(f"\nSaved sweep results to {out_path}")

    print(
        f"\n=== Summary: baseline WR MAE={baseline_wr_mae:.4f} "
        f"WR_rho={baseline_wr_rho:.4f} | RB MAE={baseline_rb_mae:.4f} "
        f"RB_rho={baseline_rb_rho:.4f} ==="
    )
    print(
        "Gate: ship if MAE improves >= 0.02 at WR/TE/RB "
        "OR Spearman improves >= 0.015 with MAE not worse by > 0.005\n"
    )

    if "WR_mae" in df_out.columns:
        non_base = df_out[df_out["label"] != "baseline_production"].copy()
        non_base["wr_mae_delta"] = baseline_wr_mae - non_base["WR_mae"]
        non_base["rb_mae_delta"] = baseline_rb_mae - non_base["RB_mae"]
        non_base["wr_rho_delta"] = (
            non_base.get("WR_spearman_weekly", pd.Series(float("nan"), index=non_base.index))
            - baseline_wr_rho
        )
        non_base["rb_rho_delta"] = (
            non_base.get("RB_spearman_weekly", pd.Series(float("nan"), index=non_base.index))
            - baseline_rb_rho
        )

        ranked = non_base.sort_values("WR_mae").head(10)
        print("Top-10 by WR MAE:")
        print(
            f"  {'Label':<60} {'WR_MAE':>8} {'dWRMAE':>7} {'WR_rho':>8} "
            f"{'dWRrho':>7} {'RB_rho':>8} {'dRBrho':>7} {'TE_mae':>7}"
        )
        for _, r in ranked.iterrows():
            print(
                f"  {str(r['label']):<60} "
                f"{r.get('WR_mae', float('nan')):>8.4f} "
                f"{r.get('wr_mae_delta', float('nan')):>+7.4f} "
                f"{r.get('WR_spearman_weekly', float('nan')):>8.4f} "
                f"{r.get('wr_rho_delta', float('nan')):>+7.4f} "
                f"{r.get('RB_spearman_weekly', float('nan')):>8.4f} "
                f"{r.get('rb_rho_delta', float('nan')):>+7.4f} "
                f"{r.get('TE_mae', float('nan')):>7.4f}"
            )

        # Gate verdict
        wr_mae_gate = non_base[non_base["wr_mae_delta"] >= 0.02]
        wr_rho_gate = non_base[
            (non_base.get("wr_rho_delta", pd.Series(float("nan"), index=non_base.index)) >= 0.015)
            & (non_base["WR_mae"] <= baseline_wr_mae + 0.005)
        ]
        rb_mae_gate = non_base[non_base["rb_mae_delta"] >= 0.02]
        rb_rho_gate = non_base[
            (non_base.get("rb_rho_delta", pd.Series(float("nan"), index=non_base.index)) >= 0.015)
            & (non_base["RB_mae"] <= baseline_rb_mae + 0.005)
        ]

        print("\n=== GATE VERDICT (TPRR Experiment) ===")
        verdicts = []
        for gate_df, gate_name, key_mae, key_delta in [
            (wr_mae_gate, "WR MAE gate (>=0.02)", "WR_mae", "wr_mae_delta"),
            (wr_rho_gate, "WR Spearman gate (>=0.015, no MAE regression)", "WR_spearman_weekly", "wr_rho_delta"),
            (rb_mae_gate, "RB MAE gate (>=0.02)", "RB_mae", "rb_mae_delta"),
            (rb_rho_gate, "RB Spearman gate (>=0.015, no MAE regression)", "RB_spearman_weekly", "rb_rho_delta"),
        ]:
            if not gate_df.empty:
                best = gate_df.loc[gate_df[key_delta].idxmax()]
                verdicts.append(
                    f"PASS ({gate_name}): {best['label']}  "
                    f"delta={best[key_delta]:+.4f}"
                )
            else:
                verdicts.append(f"KILL ({gate_name}): no config cleared")

        for v in verdicts:
            print(f"  {v}")


# ---------------------------------------------------------------------------
# Experiment 2: Spread-conditioned game-script volume tilt
# ---------------------------------------------------------------------------


def _build_spread_by_week(
    schedules_df: pd.DataFrame,
) -> Dict[Tuple, float]:
    """Build a (season, week, team) -> spread_from_team_perspective dict.

    nflverse ``spread_line`` is POSITIVE when the home team is favoured
    (e.g., KC home favourite by 7 → spread_line = +7.0).  This function
    converts to the BETTING CONVENTION used by _vegas_multiplier and
    _build_spread_by_team: NEGATIVE = favoured.

    Conversion:
      home_team perspective = -spread_line  (home fav by 7 → -7)
      away_team perspective = +spread_line  (away dog by 7 → +7)

    This matches ``_build_spread_by_team`` in src/projection_engine.py,
    which documents the same convention.

    Args:
        schedules_df: Schedule DataFrame with season, week, home_team,
            away_team, spread_line columns.

    Returns:
        Dict keyed as (season, week, team_abbr) -> spread_betting_conv.
        Negative values indicate the team is favoured.
        Missing or NaN spread_line games get 0.0 (pick-em / neutral).
    """
    required = {"season", "week", "home_team", "away_team", "spread_line"}
    if schedules_df.empty or not required.issubset(schedules_df.columns):
        return {}
    spread_map: Dict[Tuple, float] = {}
    for row in schedules_df[
        ["season", "week", "home_team", "away_team", "spread_line"]
    ].itertuples(index=False):
        raw = float(row.spread_line) if pd.notna(row.spread_line) else 0.0
        # nflverse: positive raw = home favored → betting conv: home gets -raw
        spread_map[(row.season, row.week, row.home_team)] = -raw
        spread_map[(row.season, row.week, row.away_team)] = raw
    return spread_map


def cmd_sweep_spread_gamescript() -> None:
    """Experiment 2: Sweep spread-conditioned game-script volume multipliers.

    Motivation: The current heuristic uses Vegas implied team total multiplier
    only (plus a small RB run-heavy bonus at total<20 & spread<-7).  SOTA
    systems (PFF Greenline, Peabody) condition VOLUME MIX on the spread:

      - Big favourites → more RB carries / fewer WR targets late in games
        (running out the clock, preventing garbage time pass volume)
      - Big underdogs → more WR/TE targets (must pass to catch up), fewer
        RB carries

    This attacks WITHIN-TEAM ordering: the current vegas_multiplier moves
    the whole team up/down but cannot reorder an RB vs his WR teammates.

    Implementation: spread-conditioned multipliers are layered ON TOP of the
    base usage multiplier, applied after the standard usage calc.  The spread
    is the pre-game line (spread_line from schedules Bronze — same source used
    by _build_spread_by_team in projection_engine.py).

    Buckets swept:
      - Spread < -10 (heavy favourite): RB boost, WR/TE cut
      - Spread < -7 (moderate favourite): RB boost, WR/TE cut
      - Spread > +7 (moderate underdog): RB cut, WR/TE boost
      - Spread > +10 (heavy underdog): RB cut, WR/TE boost
      - Combined: both tails active

    Multiplier values swept: k_fav_rb in {1.05, 1.08, 1.10, 1.12};
    k_dog_rb in {0.88, 0.90, 0.92, 0.95};
    mirror for WR/TE (1/k approximately).

    The spread source is the pre-game line from data/bronze/schedules
    (``spread_line`` column, which is the home-team spread at game time;
    the lab builds a per-team per-week map so every row can look up its
    own spread perspective).

    Gates: ship-candidate if MAE improves >= 0.02 OR mean within-position-week
    Spearman improves >= 0.015 with MAE not worse by > 0.005.

    Outputs:
        - Console: per-config table with RB/WR MAE + RB/WR weekly Spearman
        - CSV: output/heuristic_lab_cache/sweep_spread_gamescript.csv
        - Gate verdict: PASS/KILL per plan criteria
    """
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    strength = build_defense_strength(weekly, sched, window=8)
    omap = build_upcoming_opponent_map(sched)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))
    prior_blend = _build_production_blend_fn(weekly, manifest)

    # Build spread lookup: (season, week, team) -> spread_from_team_perspective
    spread_map = _build_spread_by_week(sched)
    if not spread_map:
        print("No spread data in schedules — aborting sweep.")
        return

    n_covered = sum(1 for v in spread_map.values() if v != 0.0)
    print(
        f"Spread map built: {len(spread_map)} team-weeks, "
        f"{n_covered} with non-zero spread"
    )

    orig_usage = projection_engine._usage_multiplier

    def _make_spread_usage(
        fav_threshold: float,
        dog_threshold: float,
        rb_fav_mult: float,
        wr_fav_mult: float,
        rb_dog_mult: float,
        wr_dog_mult: float,
        apply_rb: bool = True,
        apply_wr: bool = True,
    ) -> object:
        """Create a usage multiplier that conditions on the pre-game spread.

        For RB: big-favourite games -> rb_fav_mult; big-underdog games ->
        rb_dog_mult.  For WR/TE: mirror (wr_fav_mult in favourite game,
        wr_dog_mult in underdog game).

        Args:
            fav_threshold: Spread below which team is a favourite (negative
                value, e.g. -7.0 means favoured by 7+).
            dog_threshold: Spread above which team is an underdog (positive
                value, e.g. +7.0 means underdog by 7+).
            rb_fav_mult: RB multiplier when team is a heavy favourite (> 1).
            wr_fav_mult: WR/TE multiplier when team is a heavy favourite (< 1).
            rb_dog_mult: RB multiplier when team is a big underdog (< 1).
            wr_dog_mult: WR/TE multiplier when team is a big underdog (> 1).
            apply_rb: Whether to apply spread tilt to RB position.
            apply_wr: Whether to apply spread tilt to WR/TE positions.

        Returns:
            Patched _usage_multiplier function.
        """

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage(df, position)
            is_rb = position == "RB"
            is_wr_te = position in ("WR", "TE")
            if not ((is_rb and apply_rb) or (is_wr_te and apply_wr)):
                return base
            if "recent_team" not in df.columns:
                return base

            sc = df.get("proj_season", df.get("season", pd.Series(dtype=int)))
            wc = df.get("proj_week", df.get("week", pd.Series(dtype=int)))
            spreads = pd.Series(
                [
                    spread_map.get((s, w, t), 0.0)
                    for s, w, t in zip(sc, wc, df["recent_team"])
                ],
                index=df.index,
            )

            result = base.copy()

            # Favourite bucket: spread < fav_threshold (e.g. < -7)
            fav_mask = spreads < fav_threshold
            if fav_mask.any():
                if is_rb and apply_rb:
                    result.loc[fav_mask] = (
                        result.loc[fav_mask] * rb_fav_mult
                    ).clip(0.80, 1.25)
                elif is_wr_te and apply_wr:
                    result.loc[fav_mask] = (
                        result.loc[fav_mask] * wr_fav_mult
                    ).clip(0.70, 1.15)

            # Underdog bucket: spread > dog_threshold (e.g. > +7)
            dog_mask = spreads > dog_threshold
            if dog_mask.any():
                if is_rb and apply_rb:
                    result.loc[dog_mask] = (
                        result.loc[dog_mask] * rb_dog_mult
                    ).clip(0.70, 1.15)
                elif is_wr_te and apply_wr:
                    result.loc[dog_mask] = (
                        result.loc[dog_mask] * wr_dog_mult
                    ).clip(0.80, 1.25)

            return result

        return patched

    def _run(label: str, usage_patch=None) -> Dict:
        pe_usage = usage_patch if usage_patch is not None else orig_usage
        projection_engine._usage_multiplier = pe_usage
        try:
            results = evaluate_config(
                manifest,
                matchup_patch=matchup,
                prior_blend_fn=prior_blend,
            )
        finally:
            projection_engine._usage_multiplier = orig_usage
        s = _summarize_with_spearman(results)
        s["label"] = label
        return s

    rows: List[Dict] = []

    def _record(s: Dict) -> None:
        rows.append(s)
        rb_rho = s.get("RB_spearman_weekly", float("nan"))
        wr_rho = s.get("WR_spearman_weekly", float("nan"))
        print(
            f"{s['label']:<72} "
            f"RB:{s.get('RB_mae', float('nan')):.4f} "
            f"WR:{s.get('WR_mae', float('nan')):.4f} "
            f"RB_rho={rb_rho:.4f} WR_rho={wr_rho:.4f}"
        )

    # Baseline
    base_s = _run("baseline_production")
    _record(base_s)
    baseline_rb_mae = base_s.get("RB_mae", float("nan"))
    baseline_rb_rho = base_s.get("RB_spearman_weekly", float("nan"))
    baseline_wr_mae = base_s.get("WR_mae", float("nan"))
    baseline_wr_rho = base_s.get("WR_spearman_weekly", float("nan"))
    print(
        f"\nBaseline — RB MAE: {baseline_rb_mae:.4f}  RB Spearman: {baseline_rb_rho:.4f}"
        f"  |  WR MAE: {baseline_wr_mae:.4f}  WR Spearman: {baseline_wr_rho:.4f}"
    )
    print(
        "Gates: ship if MAE improves >= 0.02 OR Spearman improves >= 0.015 "
        "with MAE not worse by > 0.005"
    )

    # -----------------------------------------------------------------------
    # Sub-experiment A: RB-only spread tilt
    # -----------------------------------------------------------------------
    print("\n=== Sub-experiment A: RB-only spread tilt ===")
    for fav_thr, dog_thr in [(-7.0, 7.0), (-10.0, 10.0)]:
        thr_label = f"fav{abs(fav_thr):.0f}"
        for rb_fav in [1.05, 1.08, 1.10, 1.12]:
            for rb_dog in [0.88, 0.90, 0.92, 0.95]:
                # Mirror for WR/TE: wr_fav = inverse of rb_dog tendency;
                # neutral here (apply_wr=False) to isolate RB effect
                label = (
                    f"spread_A_{thr_label}_rbfav={rb_fav}_rbdog={rb_dog}"
                )
                s = _run(
                    label,
                    usage_patch=_make_spread_usage(
                        fav_threshold=fav_thr,
                        dog_threshold=dog_thr,
                        rb_fav_mult=rb_fav,
                        wr_fav_mult=1.0,
                        rb_dog_mult=rb_dog,
                        wr_dog_mult=1.0,
                        apply_rb=True,
                        apply_wr=False,
                    ),
                )
                _record(s)

    # -----------------------------------------------------------------------
    # Sub-experiment B: WR/TE-only spread tilt
    # -----------------------------------------------------------------------
    print("\n=== Sub-experiment B: WR/TE-only spread tilt ===")
    for fav_thr, dog_thr in [(-7.0, 7.0), (-10.0, 10.0)]:
        thr_label = f"fav{abs(fav_thr):.0f}"
        for wr_fav in [0.90, 0.92, 0.95]:
            for wr_dog in [1.05, 1.08, 1.10]:
                label = (
                    f"spread_B_{thr_label}_wrfav={wr_fav}_wrdog={wr_dog}"
                )
                s = _run(
                    label,
                    usage_patch=_make_spread_usage(
                        fav_threshold=fav_thr,
                        dog_threshold=dog_thr,
                        rb_fav_mult=1.0,
                        wr_fav_mult=wr_fav,
                        rb_dog_mult=1.0,
                        wr_dog_mult=wr_dog,
                        apply_rb=False,
                        apply_wr=True,
                    ),
                )
                _record(s)

    # -----------------------------------------------------------------------
    # Sub-experiment C: Joint RB + WR/TE (both tails active)
    # Best RB config from A + best WR config from B
    # -----------------------------------------------------------------------
    print("\n=== Sub-experiment C: Joint RB + WR/TE tilt (both tails active) ===")
    df_so_far = pd.DataFrame(rows)
    # Find best RB config from sub-A (lowest RB MAE)
    sub_a = df_so_far[df_so_far["label"].str.startswith("spread_A_")]
    # Find best WR config from sub-B (lowest WR MAE)
    sub_b = df_so_far[df_so_far["label"].str.startswith("spread_B_")]

    joint_configs = []
    if not sub_a.empty and not sub_b.empty and "RB_mae" in sub_a.columns and "WR_mae" in sub_b.columns:
        # Top-3 RB × Top-3 WR joint combos
        top_rb = sub_a.nsmallest(3, "RB_mae")
        top_wr = sub_b.nsmallest(3, "WR_mae")
        for _, rb_row in top_rb.iterrows():
            for _, wr_row in top_wr.iterrows():
                joint_configs.append((str(rb_row["label"]), str(wr_row["label"])))

    def _parse_spread_params(label: str) -> Optional[Dict]:
        """Parse spread parameters from a sweep label string.

        Args:
            label: Label string from spread_A_* or spread_B_* entries.

        Returns:
            Dict with threshold and multiplier params, or None if parsing fails.
        """
        try:
            # Determine threshold from label (fav7 or fav10)
            if "fav7" in label:
                fav_thr, dog_thr = -7.0, 7.0
            elif "fav10" in label:
                fav_thr, dog_thr = -10.0, 10.0
            else:
                return None
            params: Dict = {"fav_threshold": fav_thr, "dog_threshold": dog_thr}
            if "rbfav=" in label:
                params["rb_fav_mult"] = float(label.split("rbfav=")[1].split("_")[0])
                params["rb_dog_mult"] = float(label.split("rbdog=")[1].split("_")[0])
            else:
                params["rb_fav_mult"] = 1.0
                params["rb_dog_mult"] = 1.0
            if "wrfav=" in label:
                params["wr_fav_mult"] = float(label.split("wrfav=")[1].split("_")[0])
                params["wr_dog_mult"] = float(label.split("wrdog=")[1])
            else:
                params["wr_fav_mult"] = 1.0
                params["wr_dog_mult"] = 1.0
            return params
        except (IndexError, ValueError):
            return None

    for rb_label, wr_label in joint_configs[:9]:  # limit to 9 joint combos
        rb_p = _parse_spread_params(rb_label)
        wr_p = _parse_spread_params(wr_label)
        if rb_p is None or wr_p is None:
            continue
        # Use the tighter threshold (larger abs value) for the joint config
        fav_thr = min(rb_p["fav_threshold"], wr_p["fav_threshold"])
        dog_thr = max(rb_p["dog_threshold"], wr_p["dog_threshold"])
        label = (
            f"spread_C_fav{abs(fav_thr):.0f}"
            f"_rbfav={rb_p['rb_fav_mult']}_rbdog={rb_p['rb_dog_mult']}"
            f"_wrfav={wr_p['wr_fav_mult']}_wrdog={wr_p['wr_dog_mult']}"
        )
        s = _run(
            label,
            usage_patch=_make_spread_usage(
                fav_threshold=fav_thr,
                dog_threshold=dog_thr,
                rb_fav_mult=rb_p["rb_fav_mult"],
                wr_fav_mult=wr_p["wr_fav_mult"],
                rb_dog_mult=rb_p["rb_dog_mult"],
                wr_dog_mult=wr_p["wr_dog_mult"],
                apply_rb=True,
                apply_wr=True,
            ),
        )
        _record(s)

    # -----------------------------------------------------------------------
    # Save results and gate verdicts
    # -----------------------------------------------------------------------
    df_out = pd.DataFrame(rows)
    out_path = os.path.join(CACHE_DIR, "sweep_spread_gamescript.csv")
    df_out.to_csv(out_path, index=False)
    print(f"\nSaved sweep results to {out_path}")

    print(
        f"\n=== Summary: baseline RB MAE={baseline_rb_mae:.4f} "
        f"RB_rho={baseline_rb_rho:.4f} | WR MAE={baseline_wr_mae:.4f} "
        f"WR_rho={baseline_wr_rho:.4f} ==="
    )

    if len(df_out) > 1:
        non_base = df_out[df_out["label"] != "baseline_production"].copy()
        non_base["rb_mae_delta"] = baseline_rb_mae - non_base["RB_mae"]
        non_base["wr_mae_delta"] = baseline_wr_mae - non_base["WR_mae"]
        non_base["rb_rho_delta"] = (
            non_base.get("RB_spearman_weekly", pd.Series(float("nan"), index=non_base.index))
            - baseline_rb_rho
        )
        non_base["wr_rho_delta"] = (
            non_base.get("WR_spearman_weekly", pd.Series(float("nan"), index=non_base.index))
            - baseline_wr_rho
        )

        print("\nTop-10 by RB MAE improvement:")
        ranked_rb = non_base.nlargest(10, "rb_mae_delta")
        print(
            f"  {'Label':<72} {'RB_MAE':>8} {'dRBMAE':>7} {'RB_rho':>8} "
            f"{'dRBrho':>7} {'WR_MAE':>8} {'dWRMAE':>7}"
        )
        for _, r in ranked_rb.iterrows():
            print(
                f"  {str(r['label']):<72} "
                f"{r.get('RB_mae', float('nan')):>8.4f} "
                f"{r.get('rb_mae_delta', float('nan')):>+7.4f} "
                f"{r.get('RB_spearman_weekly', float('nan')):>8.4f} "
                f"{r.get('rb_rho_delta', float('nan')):>+7.4f} "
                f"{r.get('WR_mae', float('nan')):>8.4f} "
                f"{r.get('wr_mae_delta', float('nan')):>+7.4f}"
            )

        print("\nTop-10 by WR MAE improvement:")
        ranked_wr = non_base.nlargest(10, "wr_mae_delta")
        for _, r in ranked_wr.iterrows():
            print(
                f"  {str(r['label']):<72} "
                f"{r.get('WR_mae', float('nan')):>8.4f} "
                f"{r.get('wr_mae_delta', float('nan')):>+7.4f} "
                f"{r.get('WR_spearman_weekly', float('nan')):>8.4f} "
                f"{r.get('wr_rho_delta', float('nan')):>+7.4f} "
                f"{r.get('RB_mae', float('nan')):>8.4f} "
                f"{r.get('rb_mae_delta', float('nan')):>+7.4f}"
            )

        # Gate verdicts
        print("\n=== GATE VERDICT (Spread Game-Script Experiment) ===")
        for pos, mae_key, rho_key, mae_delta_key, rho_delta_key, base_mae, base_rho in [
            ("RB", "RB_mae", "RB_spearman_weekly", "rb_mae_delta", "rb_rho_delta",
             baseline_rb_mae, baseline_rb_rho),
            ("WR", "WR_mae", "WR_spearman_weekly", "wr_mae_delta", "wr_rho_delta",
             baseline_wr_mae, baseline_wr_rho),
        ]:
            mae_gate = non_base[non_base[mae_delta_key] >= 0.02]
            rho_gate = non_base[
                (non_base.get(rho_delta_key, pd.Series(float("nan"), index=non_base.index)) >= 0.015)
                & (non_base[mae_key] <= base_mae + 0.005)
            ]
            if not mae_gate.empty:
                best = mae_gate.loc[mae_gate[mae_delta_key].idxmax()]
                print(
                    f"  PASS ({pos} MAE gate >=0.02): {best['label']}  "
                    f"delta {best[mae_delta_key]:+.4f}  "
                    f"MAE {base_mae:.4f} -> {best[mae_key]:.4f}"
                )
            elif not rho_gate.empty:
                best = rho_gate.loc[rho_gate[rho_delta_key].idxmax()]
                print(
                    f"  PASS ({pos} Spearman gate >=0.015): {best['label']}  "
                    f"rho delta {best[rho_delta_key]:+.4f}  "
                    f"MAE delta {best[mae_delta_key]:+.4f}"
                )
            else:
                best_mae_d = float(non_base[mae_delta_key].max()) if len(non_base) > 0 else float("nan")
                rho_col_vals = non_base.get(rho_delta_key, pd.Series(dtype=float))
                best_rho_d = float(rho_col_vals.max()) if len(rho_col_vals) > 0 else float("nan")
                print(
                    f"  KILL ({pos}): no config cleared gate "
                    f"(best MAE delta={best_mae_d:+.4f}, need >=+0.02; "
                    f"best rho delta={best_rho_d:+.4f}, need >=+0.015)"
                )


def _load_graph_all_features_lab(seasons: List[int]) -> pd.DataFrame:
    """Load the most-recent graph_all_features parquet for each season.

    All 83+ columns including red-zone, QB-WR chemistry, game-script, and
    route features are included.  All are shift(1)-lagged in source modules.

    Ported from worktree-agent-a2e05852c20b3a13d so the sweep-ranking-score
    command can run on main's codebase without a cherry-pick.

    Args:
        seasons: Evaluation seasons (e.g. [2022, 2023, 2024]).

    Returns:
        Concatenated DataFrame, or empty DataFrame when no files found.
    """
    import glob as globmod

    frames = []
    for season in seasons:
        files = sorted(
            globmod.glob(
                os.path.join(
                    PROJECT_ROOT,
                    "data",
                    "silver",
                    "graph_features",
                    f"season={season}",
                    "graph_all_features_*.parquet",
                )
            )
        )
        if files:
            frames.append(pd.read_parquet(files[-1]))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _compute_band_spearman_lab(
    results: pd.DataFrame,
    consensus: pd.DataFrame,
    pos: str,
    band_lo: int,
    band_hi: int,
) -> float:
    """Compute mean within-week Spearman in a consensus-rank band.

    Band membership is determined by consensus rank within each
    (season, week) group.  Rank 1 = highest consensus projection.
    Only weeks with >= 5 players in the band are included.

    Ported from worktree-agent-a2e05852c20b3a13d.

    Args:
        results: Eval results with player_id, season, week,
            projected_points (or ranking_score), actual_points, position.
        consensus: Consensus DataFrame with player_id, season, week,
            consensus_proj columns.
        pos: Position string ('RB' or 'WR').
        band_lo: Lowest rank in the band (1-indexed, inclusive).
        band_hi: Highest rank in band (inclusive); use 999 for 25+.

    Returns:
        Mean within-week Spearman over qualifying weeks.  NaN when none.
    """
    from scipy.stats import spearmanr  # type: ignore

    pos_res = results[results["position"] == pos]
    if pos_res.empty or "player_id" not in pos_res.columns:
        return float("nan")

    score_col = "ranking_score" if "ranking_score" in pos_res.columns else "projected_points"

    merged = pos_res.merge(
        consensus[["player_id", "season", "week", "consensus_proj"]],
        on=["player_id", "season", "week"],
        how="inner",
    )
    if merged.empty:
        return float("nan")

    merged["cons_rank"] = merged.groupby(["season", "week"])["consensus_proj"].rank(
        ascending=False, method="average"
    )
    band = merged[(merged["cons_rank"] >= band_lo) & (merged["cons_rank"] <= band_hi)]

    week_corrs = []
    for (_s, _w), grp in band.groupby(["season", "week"]):
        if len(grp) < 5:
            continue
        rho, _ = spearmanr(grp[score_col], grp["actual_points"])
        if np.isfinite(rho):
            week_corrs.append(float(rho))
    return float(np.mean(week_corrs)) if week_corrs else float("nan")


def _summarize_with_band_spearman_lab(
    results: pd.DataFrame,
    consensus: pd.DataFrame,
) -> Dict:
    """Extend _summarize_with_spearman with RB/WR band-level Spearman.

    Adds keys RB_band12_spearman, RB_band1324_spearman,
    WR_band12_spearman, WR_band1324_spearman.

    Args:
        results: Eval results from evaluate_config (may include ranking_score).
        consensus: Consensus data (player_id, season, week, consensus_proj).

    Returns:
        Summary dict with standard MAE/Spearman keys plus band entries.
    """
    s = _summarize_with_spearman(results)
    for pos in ["RB", "WR"]:
        s[f"{pos}_band12_spearman"] = _compute_band_spearman_lab(
            results, consensus, pos, 1, 12
        )
        s[f"{pos}_band1324_spearman"] = _compute_band_spearman_lab(
            results, consensus, pos, 13, 24
        )
    return s


def _load_consensus_for_seasons_lab(seasons: List[int]) -> pd.DataFrame:
    """Load Sleeper consensus projections for the given seasons (half-PPR).

    Args:
        seasons: Evaluation seasons.

    Returns:
        Deduplicated DataFrame with player_id, season, week, consensus_proj.
    """
    import glob as globmod

    silver_root = os.path.join(PROJECT_ROOT, "data", "silver", "external_projections")
    rows = []
    for season in seasons:
        for week in range(3, 19):
            week_dir = os.path.join(silver_root, f"season={season}", f"week={week:02d}")
            files = sorted(globmod.glob(os.path.join(week_dir, "*.parquet")))
            if not files:
                continue
            df = pd.read_parquet(files[-1])
            df = df[(df["source"] == "sleeper") & (df["scoring_format"] == SCORING)]
            df = df[df["position"].isin(POSITIONS)]
            if df.empty:
                continue
            df = df.rename(columns={"projected_points": "consensus_proj"})
            df["season"] = season
            df["week"] = week
            rows.append(df[["player_id", "season", "week", "consensus_proj"]])
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).drop_duplicates(
        subset=["player_id", "season", "week"]
    )


def _compute_inversion_rate(
    results: pd.DataFrame,
    pts_gap_threshold: float = 1.5,
) -> float:
    """Compute the fraction of within-(position, week) player pairs whose
    ranking_score order inverts relative to projected_points order, for pairs
    where the projected_points gap exceeds ``pts_gap_threshold``.

    A rank inversion happens when player A has a higher projected_points than
    player B by more than ``pts_gap_threshold``, but a lower ranking_score.
    This guardrail keeps the ranking_score from aggressively reordering pairs
    that the heuristic clearly separated on volume alone.

    Args:
        results: Eval results with projected_points, ranking_score, position,
            season, week columns.
        pts_gap_threshold: Minimum projected_points gap for a pair to count.

    Returns:
        Fraction of qualifying pairs that are inverted.  0.0 when no
        qualifying pairs exist.
    """
    if "ranking_score" not in results.columns:
        return 0.0

    total_pairs = 0
    inverted_pairs = 0

    for (pos, _s, _w), grp in results.groupby(["position", "season", "week"]):
        if pos not in ("RB", "WR"):
            continue
        n = len(grp)
        if n < 2:
            continue
        pts = grp["projected_points"].values
        rs = grp["ranking_score"].values
        for i in range(n):
            for j in range(i + 1, n):
                diff = pts[i] - pts[j]
                if abs(diff) > pts_gap_threshold:
                    total_pairs += 1
                    # Inversion: higher pts but lower ranking_score
                    if diff > 0 and rs[i] < rs[j]:
                        inverted_pairs += 1
                    elif diff < 0 and rs[j] < rs[i]:
                        inverted_pairs += 1

    if total_pairs == 0:
        return 0.0
    return inverted_pairs / total_pairs


def cmd_sweep_ranking_score() -> None:
    """Experiment: ranking_score nudge parameter selection.

    Concept (from WR_RB_CONSENSUS_PLAN.md "NEXT FRONTIER"):
    ``ranking_score = projected_points + small capped nudges`` — used ONLY
    for position ordering.  MAE is irrelevant by construction; the optimisation
    target is band-level Spearman in the broken bands:
        WR top-12 (baseline +0.072)
        WR 13-24  (baseline −0.001)
        RB top-12 (baseline +0.140)
        RB 13-24  (baseline +0.015)

    Primary metric: band Spearman (not MAE).
    Gate (ship): WR12 >= baseline + 0.025; no band degrades > 0.005.
    Inversion guardrail: inversion_rate_1_5 <= 2 %.

    Grid:
      Single WR signals: W2 (qb_wr_chemistry_epa_roll3) at alphas 0.10–0.40;
                         W1 (rz_target_share_roll3) at alphas 0.05–0.20.
      Single RB signals: R4 (predicted_script_boost) at alphas 0.05–0.25;
                         R1 (rz_carry_share_roll3) at alphas 0.05–0.20;
                         R5 (rz_td_regression) at alphas 0.05–0.20.
      Joint WR: W2+W1 at several alpha combos.
      Joint RB: R4+R1, R4+R5 at several alpha combos.

    The sweep applies nudges additively (z-score * alpha per signal, summed
    then capped at ±RANKING_NUDGE_CAP) using src/ranking_score.py.

    Output:
        output/heuristic_lab_cache/sweep_ranking_score.csv
        Console gate verdict per signal.
    """
    import sys as _sys

    _src = os.path.join(PROJECT_ROOT, "src")
    if _src not in _sys.path:
        _sys.path.insert(0, _src)

    from ranking_score import (  # type: ignore
        RANKING_NUDGE_CAP,
        _compute_position_nudge,
    )

    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    strength = build_defense_strength(weekly, sched, window=8)
    omap = build_upcoming_opponent_map(sched)
    matchup = _make_matchup_patch(strength, omap, dict(projection_engine.MATCHUP_BETA))
    prior_blend = _build_production_blend_fn(weekly, manifest)

    seasons = sorted({e["season"] for e in manifest})
    gf = _load_graph_all_features_lab(seasons)
    if gf.empty:
        print("No graph_all_features data found — aborting sweep-ranking-score")
        return

    consensus = _load_consensus_for_seasons_lab(seasons)
    if consensus.empty:
        print("No consensus data found — aborting sweep-ranking-score")
        return

    print(f"Graph feature rows: {len(gf)} over seasons {sorted(gf['season'].unique())}")
    print(f"Consensus rows: {len(consensus)}")

    # Base results (projected_points) evaluated once, reused for all configs.
    print("\nBuilding baseline (production config)...")
    base_results = evaluate_config(
        manifest,
        matchup_patch=matchup,
        prior_blend_fn=prior_blend,
    )
    if base_results.empty:
        print("evaluate_config returned empty — aborting")
        return

    base_s = _summarize_with_band_spearman_lab(base_results, consensus)
    base_s["label"] = "baseline_production"
    base_s["inversion_rate_1_5"] = 0.0  # no nudge → no inversions by definition

    base_rb12 = base_s["RB_band12_spearman"]
    base_rb1324 = base_s["RB_band1324_spearman"]
    base_wr12 = base_s["WR_band12_spearman"]
    base_wr1324 = base_s["WR_band1324_spearman"]

    print(
        f"\nBaseline band Spearman: "
        f"RB12={base_rb12:.4f}  RB1324={base_rb1324:.4f}  "
        f"WR12={base_wr12:.4f}  WR1324={base_wr1324:.4f}"
    )
    print(
        "Gate: WR12 >= baseline+0.025; no band degrades >0.005; "
        "inversion_rate_1_5 <= 2%\n"
    )

    rows: List[Dict] = [base_s]

    def _apply_nudge_config(
        results: pd.DataFrame,
        signal_params: Dict[str, Dict[str, float]],
    ) -> pd.DataFrame:
        """Apply additive z-score nudges to a copy of results, returning it
        with a ranking_score column.

        Args:
            results: Base eval results with player_id, position, season,
                week, projected_points.
            signal_params: Per-position {signal_col: alpha} mapping.

        Returns:
            Copy of results with ranking_score column added.
        """
        out = results.copy()
        total_nudge = pd.Series(0.0, index=out.index, dtype=float)
        for pos, sig_map in signal_params.items():
            if not sig_map:
                continue
            total_nudge += _compute_position_nudge(out, gf, pos, sig_map)
        total_nudge = total_nudge.clip(-RANKING_NUDGE_CAP, RANKING_NUDGE_CAP)
        out["ranking_score"] = (out["projected_points"] + total_nudge).clip(lower=0.0)
        return out

    def _eval_config(label: str, signal_params: Dict[str, Dict[str, float]]) -> Dict:
        """Apply nudge, compute band Spearman + inversion rate, record row.

        Args:
            label: Human-readable config label.
            signal_params: Per-position {signal_col: alpha} mapping.

        Returns:
            Summary dict with band Spearman, MAE, inversion_rate_1_5, label.
        """
        patched = _apply_nudge_config(base_results, signal_params)
        # Summarize using ranking_score for Spearman; MAE still from projected_points
        patched_for_spearman = patched.rename(
            columns={"projected_points": "_pts_orig", "ranking_score": "projected_points"}
        )
        s = _summarize_with_band_spearman_lab(patched_for_spearman, consensus)
        # Restore projected_points label for MAE (already computed from _pts_orig)
        s["label"] = label
        s["inversion_rate_1_5"] = _compute_inversion_rate(patched, 1.5)
        rows.append(s)

        rb12 = s.get("RB_band12_spearman", float("nan"))
        rb1324 = s.get("RB_band1324_spearman", float("nan"))
        wr12 = s.get("WR_band12_spearman", float("nan"))
        wr1324 = s.get("WR_band1324_spearman", float("nan"))
        inv = s.get("inversion_rate_1_5", float("nan"))
        wr12_delta = wr12 - base_wr12
        rb12_delta = rb12 - base_rb12
        print(
            f"  {label:<70} "
            f"WR12={wr12:+.4f}(Δ{wr12_delta:+.4f}) "
            f"WR1324={wr1324:+.4f} "
            f"RB12={rb12:+.4f}(Δ{rb12_delta:+.4f}) "
            f"RB1324={rb1324:+.4f} "
            f"inv={inv:.2%}"
        )
        return s

    # ------------------------------------------------------------------
    # Single-signal sweeps
    # ------------------------------------------------------------------
    print("=== WR single-signal sweeps ===")

    WR_W2_ALPHAS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    for a in WR_W2_ALPHAS:
        _eval_config(
            f"WR_W2_qb_wr_chemistry_epa_a={a}",
            {"WR": {"qb_wr_chemistry_epa_roll3": a}},
        )

    WR_W1_ALPHAS = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20]
    for a in WR_W1_ALPHAS:
        _eval_config(
            f"WR_W1_rz_target_share_a={a}",
            {"WR": {"rz_target_share_roll3": a}},
        )

    print("\n=== RB single-signal sweeps ===")

    RB_R4_ALPHAS = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]
    for a in RB_R4_ALPHAS:
        _eval_config(
            f"RB_R4_predicted_script_boost_a={a}",
            {"RB": {"predicted_script_boost": a}},
        )

    RB_R1_ALPHAS = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20]
    for a in RB_R1_ALPHAS:
        _eval_config(
            f"RB_R1_rz_carry_share_a={a}",
            {"RB": {"rz_carry_share_roll3": a}},
        )

    RB_R5_ALPHAS = [0.05, 0.08, 0.10, 0.12, 0.15]
    for a in RB_R5_ALPHAS:
        _eval_config(
            f"RB_R5_rz_td_regression_a={a}",
            {"RB": {"rz_td_regression": a}},
        )

    # ------------------------------------------------------------------
    # Joint WR sweeps: W2 + W1
    # ------------------------------------------------------------------
    print("\n=== Joint WR sweeps: W2+W1 ===")
    for a2, a1 in [
        (0.20, 0.08),
        (0.25, 0.08),
        (0.30, 0.08),
        (0.30, 0.10),
        (0.30, 0.12),
        (0.35, 0.10),
        (0.25, 0.10),
        (0.20, 0.10),
    ]:
        _eval_config(
            f"WR_joint_W2_a{a2}+W1_a{a1}",
            {"WR": {"qb_wr_chemistry_epa_roll3": a2, "rz_target_share_roll3": a1}},
        )

    # ------------------------------------------------------------------
    # Joint RB sweeps: R4 + R1
    # ------------------------------------------------------------------
    print("\n=== Joint RB sweeps: R4+R1, R4+R5 ===")
    for a4, a1 in [
        (0.12, 0.08),
        (0.15, 0.08),
        (0.15, 0.10),
        (0.18, 0.08),
        (0.20, 0.08),
    ]:
        _eval_config(
            f"RB_joint_R4_a{a4}+R1_a{a1}",
            {"RB": {"predicted_script_boost": a4, "rz_carry_share_roll3": a1}},
        )

    for a4, a5 in [(0.15, 0.08), (0.15, 0.10), (0.18, 0.08)]:
        _eval_config(
            f"RB_joint_R4_a{a4}+R5_a{a5}",
            {"RB": {"predicted_script_boost": a4, "rz_td_regression": a5}},
        )

    # ------------------------------------------------------------------
    # Save results
    # ------------------------------------------------------------------
    df_out = pd.DataFrame(rows)
    out_path = os.path.join(CACHE_DIR, "sweep_ranking_score.csv")
    df_out.to_csv(out_path, index=False)
    print(f"\nSaved sweep results -> {out_path}")

    # ------------------------------------------------------------------
    # Gate verdict
    # ------------------------------------------------------------------
    non_base = df_out[df_out["label"] != "baseline_production"].copy()
    print(
        "\n=== GATE VERDICT (sweep-ranking-score) ===\n"
        f"  Baseline: WR12={base_wr12:.4f}  WR1324={base_wr1324:.4f}  "
        f"RB12={base_rb12:.4f}  RB1324={base_rb1324:.4f}\n"
        f"  Gate (WR): WR12 >= {base_wr12 + 0.025:.4f} (+0.025); "
        f"no band degrades >0.005; inv_rate_1_5 <= 2%"
    )

    # Best WR-only configs
    wr_gate = non_base[
        (non_base["WR_band12_spearman"] >= base_wr12 + 0.025)
        & (non_base["WR_band1324_spearman"] >= base_wr1324 - 0.005)
        & (non_base["RB_band12_spearman"] >= base_rb12 - 0.005)
        & (non_base["RB_band1324_spearman"] >= base_rb1324 - 0.005)
        & (non_base.get("inversion_rate_1_5", pd.Series(1.0, index=non_base.index)) <= 0.02)
    ]
    if not wr_gate.empty:
        best = wr_gate.loc[wr_gate["WR_band12_spearman"].idxmax()]
        print(
            f"  PASS (WR12 gate): {best['label']}  "
            f"WR12={best['WR_band12_spearman']:.4f} "
            f"(Δ{best['WR_band12_spearman'] - base_wr12:+.4f})  "
            f"inv={best.get('inversion_rate_1_5', float('nan')):.2%}"
        )
    else:
        best_wr12 = float(non_base["WR_band12_spearman"].max()) if len(non_base) else float("nan")
        print(
            f"  KILL (WR12 gate): no config cleared gate "
            f"(best WR12={best_wr12:.4f}, need >={base_wr12 + 0.025:.4f})"
        )

    # Best RB configs (decoupled from WR gate)
    rb_gate = non_base[
        (non_base.get("inversion_rate_1_5", pd.Series(1.0, index=non_base.index)) <= 0.02)
    ].copy() if "inversion_rate_1_5" in non_base.columns else non_base.copy()
    rb_non_degrading = rb_gate[
        (rb_gate["RB_band12_spearman"] >= base_rb12 - 0.005)
        & (rb_gate["RB_band1324_spearman"] >= base_rb1324 - 0.005)
    ]
    if not rb_non_degrading.empty:
        rb_best = rb_non_degrading.loc[rb_non_degrading["RB_band12_spearman"].idxmax()]
        rb12_delta = rb_best["RB_band12_spearman"] - base_rb12
        print(
            f"  RB best non-degrading: {rb_best['label']}  "
            f"RB12={rb_best['RB_band12_spearman']:.4f} "
            f"(Δ{rb12_delta:+.4f})  "
            f"RB1324={rb_best['RB_band1324_spearman']:.4f}"
        )
        if rb12_delta >= 0.03:
            print(f"  RB12 gate PASS (>= +0.030)!")
        else:
            print(
                f"  RB12 gate MISS (< +0.030) — best delta {rb12_delta:+.4f}; "
                f"decoupled nudges are free, shipping best non-degrading"
            )
    else:
        print("  RB: no non-degrading configs found")

    print(f"\nTop-5 configs by WR12 Spearman:")
    top5 = non_base.nlargest(5, "WR_band12_spearman")
    for _, r in top5.iterrows():
        print(
            f"  {str(r['label']):<70} "
            f"WR12={r['WR_band12_spearman']:.4f} "
            f"RB12={r['RB_band12_spearman']:.4f} "
            f"inv={r.get('inversion_rate_1_5', float('nan')):.2%}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "build-cache",
            "verify",
            "sweep-matchup",
            "sweep-recency",
            "sweep-round2",
            "eval-json",
            "sweep-residual",
            "sweep-rb-route",
            "sweep-veteran-prior",
            "consensus-gap",
            "sweep-wr-route",
            "consensus-gap-wr-route",
            "sweep-tprr",
            "sweep-spread-gamescript",
            "sweep-ranking-score",
        ],
    )
    parser.add_argument("--seasons", type=str, default="2022,2023,2024")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--model-dir", type=str, default="models/residual_v42_sandbox")
    args = parser.parse_args()

    if args.command == "build-cache":
        build_cache([int(s) for s in args.seasons.split(",")])
    elif args.command == "verify":
        cmd_verify()
    elif args.command == "sweep-matchup":
        cmd_sweep_matchup()
    elif args.command == "sweep-recency":
        cmd_sweep_recency()
    elif args.command == "sweep-round2":
        cmd_sweep_round2()
    elif args.command == "eval-json":
        cmd_eval_json(args.config)
    elif args.command == "sweep-residual":
        cmd_sweep_residual(args.model_dir)
    elif args.command == "sweep-rb-route":
        cmd_sweep_rb_route()
    elif args.command == "sweep-veteran-prior":
        cmd_sweep_veteran_prior()
    elif args.command == "consensus-gap":
        cmd_consensus_gap()
    elif args.command == "sweep-wr-route":
        cmd_sweep_wr_route()
    elif args.command == "consensus-gap-wr-route":
        cmd_consensus_gap_wr_route()
    elif args.command == "sweep-tprr":
        cmd_sweep_tprr()
    elif args.command == "sweep-spread-gamescript":
        cmd_sweep_spread_gamescript()
    elif args.command == "sweep-ranking-score":
        cmd_sweep_ranking_score()
    return 0


if __name__ == "__main__":
    sys.exit(main())
