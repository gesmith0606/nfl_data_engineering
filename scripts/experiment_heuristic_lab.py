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


def _build_yardage_allowances(
    weekly_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    window: int = 8,
    min_games: int = 3,
) -> pd.DataFrame:
    """Lab-local version of player_analytics.build_yardage_allowances.

    Returns a long-format DataFrame with columns:
        season, week, team (defending), position, stat, opp_adj

    ``stat`` is one of:
        WR_recv_yds_trail, WR_receptions_trail,
        TE_recv_yds_trail, TE_receptions_trail,
        RB_recv_yds_trail, RB_rush_yds_trail, RB_carries_trail

    ``opp_adj`` = trailing_{window}-week mean of that stat allowed by the
    defense, minus the league-week mean for (position, stat) — so positive
    means the defense allows *more* of that stat than average (favorable
    matchup for the offensive player).

    All trailing values use shift(1) before rolling so the current week's
    data is strictly excluded (leak-free for projecting that week).
    """
    if weekly_df.empty or schedules_df.empty:
        return pd.DataFrame()

    sched = schedules_df[["season", "week", "home_team", "away_team"]].copy()
    home = sched.rename(columns={"home_team": "player_team", "away_team": "defense"})
    away = sched.rename(columns={"away_team": "player_team", "home_team": "defense"})
    opp_map = pd.concat([home, away], ignore_index=True)

    skill = weekly_df[weekly_df["position"].isin(["WR", "TE", "RB"])].copy()
    if skill.empty:
        return pd.DataFrame()

    merged = skill.merge(
        opp_map,
        left_on=["season", "week", "recent_team"],
        right_on=["season", "week", "player_team"],
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame()

    # (position_filter, stat_label, raw_column)
    stat_defs = [
        ("WR", "WR_recv_yds_trail", "receiving_yards"),
        ("WR", "WR_receptions_trail", "receptions"),
        ("TE", "TE_recv_yds_trail", "receiving_yards"),
        ("TE", "TE_receptions_trail", "receptions"),
        ("RB", "RB_recv_yds_trail", "receiving_yards"),
        ("RB", "RB_rush_yds_trail", "rushing_yards"),
        ("RB", "RB_carries_trail", "carries"),
    ]

    parts = []
    for pos_filter, stat_label, raw_col in stat_defs:
        if raw_col not in merged.columns:
            continue
        pos_merged = merged[merged["position"] == pos_filter]
        if pos_merged.empty:
            continue

        allowed = (
            pos_merged.groupby(["season", "week", "defense"], as_index=False)[raw_col]
            .sum()
            .rename(columns={raw_col: "raw_allowed"})
        )
        allowed = allowed.sort_values(["defense", "season", "week"])
        allowed["trailing"] = allowed.groupby("defense")["raw_allowed"].transform(
            lambda s: s.shift(1).rolling(window, min_periods=min_games).mean()
        )
        league_mean = allowed.groupby(["season", "week"])["trailing"].transform("mean")
        allowed["opp_adj"] = allowed["trailing"] - league_mean
        allowed["position"] = pos_filter
        allowed["stat"] = stat_label
        parts.append(
            allowed[["season", "week", "defense", "position", "stat", "opp_adj"]]
            .dropna(subset=["opp_adj"])
            .rename(columns={"defense": "team"})
        )

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _make_yardage_matchup_patch(
    yardage_allow: pd.DataFrame,
    strength: pd.DataFrame,
    opp_map: Dict,
    pos_betas: Dict[str, Dict[str, float]],
    base_betas: Optional[Dict[str, float]] = None,
    clip_lo: float = 0.85,
    clip_hi: float = 1.15,
) -> callable:
    """Return a ``_matchup_factor`` replacement combining yardage allowances.

    The combined factor for position P is:

        factor = clip(1 + beta_base * (pts_ratio - 1)
                      + sum_stat(beta_stat * norm(opp_adj_stat)),
                 clip_lo, clip_hi)

    where ``pts_ratio`` is from the existing defense_strength table (overall
    fantasy-points-allowed ratio), ``opp_adj_stat`` is from yardage_allow,
    and ``norm`` scales each stat to unit variance (computed over the
    provided allowance table so it is consistent within the sweep).

    Args:
        yardage_allow: Output of ``_build_yardage_allowances``.
        strength:      Output of ``build_defense_strength`` (pts ratio table).
        opp_map:       (season, week, team) -> opponent dict.
        pos_betas:     Per-position stat-beta dict, e.g.
                       ``{"WR": {"WR_recv_yds_trail": 0.02, ...}, ...}``.
        base_betas:    Per-position beta for the overall pts-ratio term.
                       Defaults to production ``projection_engine.MATCHUP_BETA``.
        clip_lo:       Lower clip bound (default 0.85).
        clip_hi:       Upper clip bound (default 1.15).
    """
    if base_betas is None:
        base_betas = dict(projection_engine.MATCHUP_BETA)

    # Build the per-stat normalisation denominators (std over non-null rows)
    stat_std: Dict[str, float] = {}
    if not yardage_allow.empty:
        for stat_name, grp in yardage_allow.groupby("stat"):
            s = grp["opp_adj"].dropna()
            stat_std[stat_name] = float(s.std()) if len(s) > 1 else 1.0

    # Build lookup tables
    pts_lut: Dict[tuple, float] = {}
    if not strength.empty:
        for r in strength.itertuples(index=False):
            pts_lut[(r.season, r.week, r.team, r.position)] = r.ratio

    ydg_lut: Dict[tuple, float] = {}
    if not yardage_allow.empty:
        for r in yardage_allow.itertuples(index=False):
            ydg_lut[(r.season, r.week, r.team, r.stat)] = r.opp_adj

    def patched(df: pd.DataFrame, opp_rankings, position: str) -> pd.Series:  # noqa: ARG001
        base_beta = base_betas.get(position, 0.0)
        stat_betas = pos_betas.get(position, {})

        season_col = "proj_season" if "proj_season" in df.columns else "season"
        week_col = "proj_week" if "proj_week" in df.columns else "week"

        vals = []
        for row in df.itertuples(index=False):
            season = getattr(row, season_col, None)
            week = getattr(row, week_col, None)
            team = getattr(row, "recent_team", None)
            opp = opp_map.get((season, week, team)) if season and week and team else None

            # Base pts-ratio term
            pts_ratio = pts_lut.get((season, week, opp, position)) if opp else None
            base_contrib = (
                base_beta * (pts_ratio - 1.0) if pts_ratio is not None and np.isfinite(pts_ratio) else 0.0
            )

            # Yardage-allowance terms
            ydg_contrib = 0.0
            for stat_name, beta_stat in stat_betas.items():
                if beta_stat == 0.0 or not opp:
                    continue
                adj = ydg_lut.get((season, week, opp, stat_name))
                if adj is None or not np.isfinite(adj):
                    continue
                std = stat_std.get(stat_name, 1.0)
                if std < 1e-6:
                    continue
                ydg_contrib += beta_stat * (adj / std)

            factor = 1.0 + base_contrib + ydg_contrib
            vals.append(float(np.clip(factor, clip_lo, clip_hi)))

        return pd.Series(vals, index=df.index)

    return patched


def cmd_sweep_yardage_allowances() -> None:
    """Sweep position-specific yardage-allowance betas on 2022-2024 cached weeks.

    Strategy:
    1. Load the cached weekly + schedule data.
    2. Build yardage allowances (7 stat-types across WR/TE/RB).
    3. Sweep individual stat betas per position, one at a time, on top of the
       production v4.2 matchup patch (apples-to-apples baseline).
    4. Evaluate combined WR+TE and WR+RB multi-stat combos at winner betas.

    Gate: improvement >= 0.03 CV MAE per position to report as SHIP candidate.
    Kill: < 0.02 overall MAE delta → record null result.

    Outputs:
      - Console: per-config summary with position MAE + delta vs baseline
      - CSV: output/heuristic_lab_cache/sweep_yardage_allowances.csv
    """
    manifest = _load_manifest()
    weekly = pd.read_parquet(os.path.join(CACHE_DIR, "weekly.parquet"))
    sched = pd.read_parquet(os.path.join(CACHE_DIR, "schedules.parquet"))
    omap = build_upcoming_opponent_map(sched)
    strength = build_defense_strength(weekly, sched, window=8)
    base_betas = dict(projection_engine.MATCHUP_BETA)

    print("Building yardage allowances table...")
    yardage_allow = _build_yardage_allowances(weekly, sched, window=8, min_games=3)
    if yardage_allow.empty:
        print("ERROR: yardage allowances table is empty — aborting")
        return

    stat_counts = yardage_allow.groupby("stat").size()
    print(f"Yardage allowances: {len(yardage_allow)} rows")
    print(stat_counts.to_string())

    rows = []

    def run(label: str, pos_betas: Dict) -> Dict:
        """Evaluate one config and print result."""
        patch = _make_yardage_matchup_patch(
            yardage_allow, strength, omap, pos_betas, base_betas
        )
        results = evaluate_config(manifest, matchup_patch=patch)
        s = summarize(results)
        s["label"] = label
        s.update({f"beta_{k}": str(v) for k, v in pos_betas.items()})
        rows.append(s)
        print(f"{label:<55} {_fmt(s)}")
        return s

    # -----------------------------------------------------------------------
    # Baseline: v4.2 production (no yardage terms, pure pts-ratio matchup)
    # -----------------------------------------------------------------------
    base_patch = _make_yardage_matchup_patch(
        yardage_allow, strength, omap, {}, base_betas
    )
    base_results = evaluate_config(manifest, matchup_patch=base_patch)
    base = summarize(base_results)
    base["label"] = "baseline_v42"
    rows.append(base)
    print(f"{'baseline_v42 (pts-ratio only)':<55} {_fmt(base)}")
    print()

    # -----------------------------------------------------------------------
    # Phase 1: Single-stat sweeps per position
    # WR stats: WR_recv_yds_trail, WR_receptions_trail
    # TE stats: TE_recv_yds_trail, TE_receptions_trail
    # RB stats: RB_recv_yds_trail, RB_rush_yds_trail, RB_carries_trail
    # -----------------------------------------------------------------------
    print("--- WR single-stat sweeps ---")
    wr_stats = ["WR_recv_yds_trail", "WR_receptions_trail"]
    for stat in wr_stats:
        for beta in [0.01, 0.02, 0.04, 0.07, 0.10]:
            run(
                f"WR {stat} b={beta}",
                {"WR": {stat: beta}},
            )

    print()
    print("--- TE single-stat sweeps ---")
    te_stats = ["TE_recv_yds_trail", "TE_receptions_trail"]
    for stat in te_stats:
        for beta in [0.01, 0.02, 0.04, 0.07, 0.10]:
            run(
                f"TE {stat} b={beta}",
                {"TE": {stat: beta}},
            )

    print()
    print("--- RB single-stat sweeps ---")
    rb_stats = ["RB_rush_yds_trail", "RB_carries_trail", "RB_recv_yds_trail"]
    for stat in rb_stats:
        for beta in [0.02, 0.05, 0.10, 0.15, 0.20]:
            run(
                f"RB {stat} b={beta}",
                {"RB": {stat: beta}},
            )

    # -----------------------------------------------------------------------
    # Phase 2: Winner combos (best single per position, then multi-stat)
    # -----------------------------------------------------------------------
    print()
    print("--- Best-of-phase-1 combos ---")

    # Find per-position best single stat from phase-1 sweep
    df_rows = pd.DataFrame(rows)
    best_by_pos: Dict[str, Tuple[str, float, float]] = {}
    for pos in ["WR", "TE", "RB"]:
        pos_key = f"{pos}_mae"
        if pos_key not in df_rows.columns:
            continue
        phase1 = df_rows[
            df_rows["label"].str.startswith(pos + " ") & df_rows[pos_key].notna()
        ]
        if phase1.empty:
            continue
        best_row = phase1.loc[phase1[pos_key].idxmin()]
        # Parse best stat + beta from label: "{POS} {stat} b={beta}"
        try:
            parts = best_row["label"].split()
            stat_best = parts[1]
            beta_best = float(parts[2].split("=")[1])
            base_pos_mae = float(base[pos_key])
            best_pos_mae = float(best_row[pos_key])
            delta = best_pos_mae - base_pos_mae
            best_by_pos[pos] = (stat_best, beta_best, delta)
            print(
                f"  {pos} best: {stat_best} b={beta_best}  "
                f"MAE {best_pos_mae:.4f} (delta {delta:+.4f})"
            )
        except (IndexError, ValueError, KeyError):
            pass

    # Multi-stat combo: combine all winning stats simultaneously
    if len(best_by_pos) >= 2:
        combo_betas: Dict[str, Dict[str, float]] = {}
        for pos, (stat, beta, _) in best_by_pos.items():
            combo_betas[pos] = {stat: beta}
        run("combo_all_best_stats", combo_betas)

    # WR + TE combined (most likely to interact)
    if "WR" in best_by_pos and "TE" in best_by_pos:
        wr_stat, wr_b, _ = best_by_pos["WR"]
        te_stat, te_b, _ = best_by_pos["TE"]
        run(
            "combo_WR+TE_best",
            {"WR": {wr_stat: wr_b}, "TE": {te_stat: te_b}},
        )

    # RB multi-stat (rush yards + carries together)
    run(
        "RB_rush_yds+carries_0.05",
        {"RB": {"RB_rush_yds_trail": 0.05, "RB_carries_trail": 0.05}},
    )
    run(
        "RB_rush_yds+carries_0.10",
        {"RB": {"RB_rush_yds_trail": 0.10, "RB_carries_trail": 0.10}},
    )

    # -----------------------------------------------------------------------
    # Phase 3: Fine-tune best combos (tighter grid around winner)
    # -----------------------------------------------------------------------
    print()
    print("--- Phase 3: fine-tune grid around best combo ---")
    if "WR" in best_by_pos:
        wr_stat, wr_b, _ = best_by_pos["WR"]
        for b in [max(0.005, wr_b - 0.015), wr_b - 0.01, wr_b, wr_b + 0.01, wr_b + 0.02]:
            if b < 0:
                continue
            run(f"fine_WR {wr_stat} b={b:.3f}", {"WR": {wr_stat: b}})

    if "RB" in best_by_pos:
        rb_stat, rb_b, _ = best_by_pos["RB"]
        for b in [rb_b - 0.02, rb_b - 0.01, rb_b, rb_b + 0.02, rb_b + 0.04]:
            if b < 0:
                continue
            run(f"fine_RB {rb_stat} b={b:.3f}", {"RB": {rb_stat: b}})

    # Save results
    out_df = pd.DataFrame(rows)
    out_path = os.path.join(CACHE_DIR, "sweep_yardage_allowances.csv")
    out_df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")

    # -----------------------------------------------------------------------
    # Summary: gate assessment
    # -----------------------------------------------------------------------
    print()
    print("=" * 72)
    print("GATE ASSESSMENT (threshold: >= 0.03 MAE improvement per position)")
    print("=" * 72)
    base_overall = base["overall_mae"]
    for pos in POSITIONS:
        pos_key = f"{pos}_mae"
        base_pos = base.get(pos_key, float("nan"))
        best_overall = out_df[pos_key].min() if pos_key in out_df.columns else float("nan")
        delta = best_overall - base_pos
        gate = "PASS (>= 0.03)" if delta <= -0.03 else ("MARGINAL" if delta <= -0.02 else "KILL (< 0.02)")
        print(f"  {pos}: base {base_pos:.4f}  best {best_overall:.4f}  delta {delta:+.4f}  => {gate}")

    best_overall = out_df["overall_mae"].min() if "overall_mae" in out_df.columns else float("nan")
    overall_delta = best_overall - base_overall
    print(f"\n  Overall: base {base_overall:.4f}  best {best_overall:.4f}  delta {overall_delta:+.4f}")
    if overall_delta <= -0.03:
        print("  VERDICT: SHIP — substantial overall improvement")
    elif overall_delta <= -0.02:
        print("  VERDICT: MARGINAL — investigate per-position decomposition")
    else:
        print("  VERDICT: KILL — less than 0.02 overall improvement; revert")


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
            "sweep-yardage-allowances",
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
    elif args.command == "sweep-yardage-allowances":
        cmd_sweep_yardage_allowances()
    return 0


if __name__ == "__main__":
    sys.exit(main())
