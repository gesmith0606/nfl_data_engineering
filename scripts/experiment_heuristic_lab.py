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
) -> pd.DataFrame:
    """Evaluate one heuristic config over the cached weeks.

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
                proj = project_position(target_df, pos, empty_rankings, SCORING)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
