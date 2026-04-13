#!/usr/bin/env python3
"""QB positive bias investigation — probes H1 through H5.

Generates evidence for the QB_BIAS_INVESTIGATION document.

Experiments:
    E1: Residual distribution analysis by position (training residuals)
    E2: Feature NaN rate for QB pruned features, by season (inc. 2024, 2025)
    E3: Train vs inference feature distribution shift for QB pruned features
    E4: Ceiling shrinkage impact — what % of QB heuristic outputs trigger shrink?
    E5: Per-fold evaluation of pruned v2 model on each season (walk-forward style)
    E6: Per-season holdout evaluation with v2 model, plus reconcile bias numbers
    E7: Run the experiment script's exact config, dump subset composition

All results written to this directory as .csv/.txt/.json.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS  # noqa: E402
from player_feature_engineering import (  # noqa: E402
    assemble_multiyear_player_features,
    get_player_feature_columns,
)
from unified_evaluation import (  # noqa: E402
    build_opp_rankings,
    compute_actual_fantasy_points,
    compute_production_heuristic,
)

ART_DIR = Path(__file__).resolve().parent
ART_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("qb_invest")

SCORING = "half_ppr"

# ----------------------------------------------------------------------------
# Setup: load data once
# ----------------------------------------------------------------------------
log.info("Loading feature data (%s seasons)…", PLAYER_DATA_SEASONS)
ALL_DATA = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
log.info("Loaded %d rows, %d cols", len(ALL_DATA), len(ALL_DATA.columns))

log.info("Building opponent rankings…")
OPP = build_opp_rankings(PLAYER_DATA_SEASONS)

POSITIONS = ["QB", "RB", "WR", "TE"]

# Pre-compute heuristic + actual per position for all seasons
# (compute_production_heuristic requires position-filtered data)
log.info("Computing heuristic + actual points per position (all seasons)…")
POS_FRAMES = {}
for pos in POSITIONS:
    pdata = ALL_DATA[ALL_DATA["position"] == pos].copy()
    heur = compute_production_heuristic(pdata, pos, OPP, SCORING)
    actual = compute_actual_fantasy_points(pdata, SCORING)
    pdata = pdata.assign(
        _heur_pts=heur.values,
        _actual_pts=actual.values,
        _residual=(actual - heur).values,
    )
    POS_FRAMES[pos] = pdata
    log.info("  %s: %d rows", pos, len(pdata))


def _week_mask(df: pd.DataFrame) -> pd.Series:
    return df["week"].between(3, 18)


# ----------------------------------------------------------------------------
# E1: Residual distribution by position (TRAINING range only = seasons != HOLDOUT_SEASON)
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 1: Residual distribution by position (training set)")
log.info("=" * 75)

rows = []
for pos in POSITIONS:
    f = POS_FRAMES[pos]
    mask = (f["season"] != HOLDOUT_SEASON) & _week_mask(f) & f["_residual"].notna()
    r = f.loc[mask, "_residual"]
    rows.append(
        {
            "position": pos,
            "n": len(r),
            "mean_residual": r.mean(),
            "median_residual": r.median(),
            "std_residual": r.std(),
            "q25": r.quantile(0.25),
            "q75": r.quantile(0.75),
            "q90": r.quantile(0.90),
            "q95": r.quantile(0.95),
            "q99": r.quantile(0.99),
            "frac_positive": (r > 0).mean(),
            "max_positive": r.max(),
            "min_negative": r.min(),
            "mean_heuristic": f.loc[mask, "_heur_pts"].mean(),
            "mean_actual": f.loc[mask, "_actual_pts"].mean(),
        }
    )
e1_df = pd.DataFrame(rows)
e1_df.to_csv(ART_DIR / "e1_residual_distribution.csv", index=False)
log.info("\n%s", e1_df.to_string(index=False))

# ----------------------------------------------------------------------------
# E4: Ceiling shrinkage impact — compare un-shrunk vs shrunk heuristic
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 4: Ceiling shrinkage impact on residuals")
log.info("=" * 75)

# We need to recompute the heuristic WITHOUT the ceiling shrinkage step, to see
# how many QB projections trigger shrinkage and what the residual would look
# like without it.
from projection_engine import (  # noqa: E402
    POSITION_STAT_PROFILE,
    PROJECTION_CEILING_SHRINKAGE,
    _matchup_factor,
    _usage_multiplier,
    _weighted_baseline,
)
from scoring_calculator import calculate_fantasy_points_df  # noqa: E402


def compute_heuristic_no_shrink(pos_data: pd.DataFrame, position: str) -> pd.Series:
    stat_cols = POSITION_STAT_PROFILE.get(position, [])
    work = pos_data.copy()
    work = work.drop(columns=["opp_rank"], errors="ignore")
    usage_mult = _usage_multiplier(work, position)
    matchup = _matchup_factor(work, OPP, position)
    rename_map = {}
    proj_cols = {}
    for stat in stat_cols:
        baseline = _weighted_baseline(work, stat)
        proj_val = (baseline * usage_mult * matchup).round(2)
        proj_col = f"proj_{stat}"
        proj_cols[proj_col] = proj_val
        rename_map[proj_col] = stat
    work = work.assign(**proj_cols)
    orig_cols = [v for v in rename_map.values() if v in work.columns]
    scoring_input = work.drop(columns=orig_cols, errors="ignore")
    scoring_input = scoring_input.rename(columns=rename_map).reset_index(drop=True)
    scoring_input = calculate_fantasy_points_df(
        scoring_input, scoring_format=SCORING, output_col="projected_points"
    )
    result = scoring_input["projected_points"]
    result.index = pos_data.index
    return result


e4_rows = []
for pos in POSITIONS:
    pdata = ALL_DATA[ALL_DATA["position"] == pos].copy()
    heur_noshrink = compute_heuristic_no_shrink(pdata, pos)
    heur_with_shrink = POS_FRAMES[pos]["_heur_pts"]
    actual = POS_FRAMES[pos]["_actual_pts"]

    mask = (pdata["season"] != HOLDOUT_SEASON) & _week_mask(pdata)
    mask = mask & heur_noshrink.notna() & heur_with_shrink.notna() & actual.notna()

    hns = heur_noshrink[mask]
    hws = heur_with_shrink[mask]
    act = actual[mask]

    shrink_triggered_12 = (hns >= 12).mean()
    shrink_triggered_18 = (hns >= 18).mean()
    shrink_triggered_23 = (hns >= 23).mean()

    resid_noshrink = act - hns
    resid_with_shrink = act - hws

    e4_rows.append(
        {
            "position": pos,
            "n": int(mask.sum()),
            "pct_heur_ge_12": shrink_triggered_12,
            "pct_heur_ge_18": shrink_triggered_18,
            "pct_heur_ge_23": shrink_triggered_23,
            "mean_resid_noshrink": resid_noshrink.mean(),
            "mean_resid_withshrink": resid_with_shrink.mean(),
            "bias_added_by_shrink": resid_with_shrink.mean() - resid_noshrink.mean(),
            "heur_noshrink_mean": hns.mean(),
            "heur_withshrink_mean": hws.mean(),
            "actual_mean": act.mean(),
        }
    )
e4_df = pd.DataFrame(e4_rows)
e4_df.to_csv(ART_DIR / "e4_ceiling_shrinkage_impact.csv", index=False)
log.info("\n%s", e4_df.to_string(index=False))

# ----------------------------------------------------------------------------
# E2: NaN rate for the 20 QB pruned features — by season
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 2: QB pruned feature NaN rates by season")
log.info("=" * 75)

QB_META_PATH = PROJECT_ROOT / "models" / "residual" / "qb_residual_meta.json"
qb_meta = json.loads(QB_META_PATH.read_text())
qb_features = qb_meta["features"]
log.info("Loaded %d features from %s", len(qb_features), QB_META_PATH)

qb_frame = POS_FRAMES["QB"]
qb_wk = qb_frame[_week_mask(qb_frame)].copy()

seasons = sorted(qb_wk["season"].unique())
nan_table = pd.DataFrame(index=qb_features, columns=[str(s) for s in seasons], dtype=float)
count_table = pd.Series({str(s): (qb_wk["season"] == s).sum() for s in seasons})

for s in seasons:
    sub = qb_wk[qb_wk["season"] == s]
    for f in qb_features:
        if f in sub.columns:
            nan_table.loc[f, str(s)] = sub[f].isna().mean()
        else:
            nan_table.loc[f, str(s)] = 1.0
nan_table["_missing_all_seasons"] = (nan_table == 1.0).any(axis=1)
nan_table.to_csv(ART_DIR / "e2_qb_feature_nan_by_season.csv")
log.info("\nRow counts per season: %s", count_table.to_dict())
log.info("\nNaN rate by feature, by season (20 pruned QB features):")
log.info("\n%s", nan_table.to_string())

# Summary: avg NaN rate per season
nan_summary = nan_table.drop(columns=["_missing_all_seasons"], errors="ignore").mean(axis=0)
log.info("\nMean NaN rate across 20 QB pruned features, by season:\n%s", nan_summary.to_string())

# ----------------------------------------------------------------------------
# E3: Train vs 2025 distribution shift for QB pruned features
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 3: Train (2016-2024) vs 2025 distribution shift for QB features")
log.info("=" * 75)

qb_wk = POS_FRAMES["QB"][_week_mask(POS_FRAMES["QB"])].copy()
train_mask = qb_wk["season"] != HOLDOUT_SEASON
holdout_mask = qb_wk["season"] == HOLDOUT_SEASON

shift_rows = []
for f in qb_features:
    if f not in qb_wk.columns:
        shift_rows.append(
            {"feature": f, "train_mean": np.nan, "train_std": np.nan,
             "holdout_mean": np.nan, "holdout_std": np.nan,
             "z_shift": np.nan, "train_nan": np.nan, "holdout_nan": np.nan}
        )
        continue
    tr = qb_wk.loc[train_mask, f]
    ho = qb_wk.loc[holdout_mask, f]
    tr_m, tr_s = tr.mean(), tr.std()
    ho_m, ho_s = ho.mean(), ho.std()
    z_shift = (ho_m - tr_m) / tr_s if tr_s and not np.isnan(tr_s) and tr_s > 0 else np.nan
    shift_rows.append(
        {
            "feature": f,
            "train_mean": tr_m,
            "train_std": tr_s,
            "holdout_mean": ho_m,
            "holdout_std": ho_s,
            "z_shift": z_shift,
            "train_nan": tr.isna().mean(),
            "holdout_nan": ho.isna().mean(),
        }
    )
e3_df = pd.DataFrame(shift_rows)
e3_df.to_csv(ART_DIR / "e3_qb_distribution_shift.csv", index=False)
log.info("\n%s", e3_df.to_string(index=False))

# ----------------------------------------------------------------------------
# E5: Evaluate the pruned v2 model on each season (walk-forward)
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 5: Pruned v2 QB model — per-season evaluation")
log.info("=" * 75)

qb_model_path = PROJECT_ROOT / "models" / "residual" / "qb_residual.joblib"
qb_imputer_path = PROJECT_ROOT / "models" / "residual" / "qb_residual_imputer.joblib"

qb_lgb = joblib.load(qb_model_path)
qb_imputer = joblib.load(qb_imputer_path)

qb_wk = POS_FRAMES["QB"][_week_mask(POS_FRAMES["QB"])].copy()

# Build feature matrix aligned to feature list, filling missing cols with NaN
X = pd.DataFrame(index=qb_wk.index)
for f in qb_features:
    X[f] = qb_wk[f].values if f in qb_wk.columns else np.nan

X_imp = qb_imputer.transform(X)
X_imp_df = pd.DataFrame(X_imp, columns=qb_features, index=qb_wk.index)
corrections = qb_lgb.predict(X_imp_df)
qb_wk["_correction"] = corrections
qb_wk["_hybrid_pts"] = np.clip(qb_wk["_heur_pts"].values + corrections, 0, None)
qb_wk["_hyb_err"] = qb_wk["_hybrid_pts"] - qb_wk["_actual_pts"]
qb_wk["_heur_err"] = qb_wk["_heur_pts"] - qb_wk["_actual_pts"]

e5_rows = []
for s in sorted(qb_wk["season"].unique()):
    sub = qb_wk[qb_wk["season"] == s]
    e5_rows.append(
        {
            "season": s,
            "n": len(sub),
            "heur_mae": sub["_heur_err"].abs().mean(),
            "heur_bias": sub["_heur_err"].mean(),
            "hybrid_mae": sub["_hyb_err"].abs().mean(),
            "hybrid_bias": sub["_hyb_err"].mean(),
            "mean_correction": sub["_correction"].mean(),
            "median_correction": sub["_correction"].median(),
            "std_correction": sub["_correction"].std(),
            "min_correction": sub["_correction"].min(),
            "max_correction": sub["_correction"].max(),
            "mean_heur_pts": sub["_heur_pts"].mean(),
            "mean_hybrid_pts": sub["_hybrid_pts"].mean(),
            "mean_actual_pts": sub["_actual_pts"].mean(),
        }
    )
e5_df = pd.DataFrame(e5_rows)
e5_df.to_csv(ART_DIR / "e5_per_season_qb_eval.csv", index=False)
log.info("\n%s", e5_df.to_string(index=False))

# ----------------------------------------------------------------------------
# E5b: Bootstrap holdout slices — does subset selection matter?
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 5b: Subset sensitivity — 2025 holdout random slices")
log.info("=" * 75)

ho = qb_wk[qb_wk["season"] == HOLDOUT_SEASON].copy()
log.info("2025 QB holdout n=%d", len(ho))
rng = np.random.default_rng(42)
slices = []
for n_sample in (100, 200, 300, 500):
    if n_sample > len(ho):
        continue
    for i in range(20):
        samp = ho.sample(n=n_sample, random_state=int(rng.integers(0, 10**9)))
        slices.append(
            {
                "n_sample": n_sample,
                "trial": i,
                "hybrid_mae": samp["_hyb_err"].abs().mean(),
                "hybrid_bias": samp["_hyb_err"].mean(),
                "heur_mae": samp["_heur_err"].abs().mean(),
                "mean_correction": samp["_correction"].mean(),
            }
        )
e5b_df = pd.DataFrame(slices)
e5b_df.to_csv(ART_DIR / "e5b_2025_subset_sensitivity.csv", index=False)
log.info("\nSubset stats (aggregated):\n%s",
         e5b_df.groupby("n_sample").agg(
             {"hybrid_mae": ["mean", "min", "max"],
              "hybrid_bias": ["mean", "min", "max"],
              "mean_correction": ["mean", "min", "max"]}
         ).to_string())

# ----------------------------------------------------------------------------
# E6: Per-week QB breakdown for 2025
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 6: 2025 QB per-week breakdown")
log.info("=" * 75)

e6_rows = []
for w in sorted(ho["week"].unique()):
    sub = ho[ho["week"] == w]
    e6_rows.append(
        {
            "week": w,
            "n": len(sub),
            "mean_heur": sub["_heur_pts"].mean(),
            "mean_hybrid": sub["_hybrid_pts"].mean(),
            "mean_actual": sub["_actual_pts"].mean(),
            "mean_correction": sub["_correction"].mean(),
            "hybrid_mae": sub["_hyb_err"].abs().mean(),
            "hybrid_bias": sub["_hyb_err"].mean(),
        }
    )
e6_df = pd.DataFrame(e6_rows)
e6_df.to_csv(ART_DIR / "e6_qb_2025_weekly.csv", index=False)
log.info("\n%s", e6_df.to_string(index=False))

# ----------------------------------------------------------------------------
# E7: Worst corrections — top 20 and bottom 20 QB rows on 2025
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 7: Top/bottom corrections on 2025 QB")
log.info("=" * 75)

ho_view_cols = [
    "season", "week", "player_name", "_heur_pts", "_correction",
    "_hybrid_pts", "_actual_pts", "_hyb_err",
]
avail = [c for c in ho_view_cols if c in ho.columns]
top20 = ho.nlargest(20, "_correction")[avail]
bot20 = ho.nsmallest(20, "_correction")[avail]
top20.to_csv(ART_DIR / "e7_top20_corrections.csv", index=False)
bot20.to_csv(ART_DIR / "e7_bot20_corrections.csv", index=False)
log.info("Top 20 (most positive) corrections:\n%s", top20.to_string(index=False))
log.info("Bottom 20 (most negative) corrections:\n%s", bot20.to_string(index=False))

# ----------------------------------------------------------------------------
# E8: The experiment script subset reproduction
# ----------------------------------------------------------------------------
log.info("=" * 75)
log.info("Experiment 8: Reproducing the experiment script's reported 4.07 MAE path")
log.info("=" * 75)

# The experiment script uses: train = ALL non-holdout seasons, holdout = 2025,
# filter week 3-18, filter valid_mask on heur/actual notna.
# Its reported MAE is over ALL 2025 rows that pass the same filters.

qb_full = POS_FRAMES["QB"]
week_mask = _week_mask(qb_full)
valid_mask = week_mask & qb_full["_heur_pts"].notna() & qb_full["_actual_pts"].notna()
holdout_mask = valid_mask & (qb_full["season"] == HOLDOUT_SEASON)
log.info(
    "Experiment script 2025 holdout: n=%d (from %d total QB 2025 rows)",
    int(holdout_mask.sum()),
    int((qb_full["season"] == HOLDOUT_SEASON).sum()),
)
ho_exp = qb_full[holdout_mask].copy()

X_exp = pd.DataFrame(index=ho_exp.index)
for f in qb_features:
    X_exp[f] = ho_exp[f].values if f in ho_exp.columns else np.nan
X_exp_imp = qb_imputer.transform(X_exp)
corr_exp = qb_lgb.predict(pd.DataFrame(X_exp_imp, columns=qb_features, index=ho_exp.index))
hyb_exp = np.clip(ho_exp["_heur_pts"].values + corr_exp, 0, None)
mae_exp = np.abs(hyb_exp - ho_exp["_actual_pts"].values).mean()
bias_exp = (hyb_exp - ho_exp["_actual_pts"].values).mean()
mean_corr_exp = corr_exp.mean()
log.info(
    "Experiment-script-style evaluation: n=%d, MAE=%.3f, bias=%.3f, mean_corr=%.3f",
    len(ho_exp), mae_exp, bias_exp, mean_corr_exp,
)

# Also compare against heuristic-only for same subset
heur_mae_exp = np.abs(ho_exp["_heur_pts"].values - ho_exp["_actual_pts"].values).mean()
log.info("Heuristic-only on same subset: MAE=%.3f", heur_mae_exp)

# ----------------------------------------------------------------------------
# Write summary JSON
# ----------------------------------------------------------------------------
summary = {
    "n_qb_train_rows_weekfiltered": int(
        ((POS_FRAMES["QB"]["season"] != HOLDOUT_SEASON) & _week_mask(POS_FRAMES["QB"])).sum()
    ),
    "n_qb_holdout_rows_weekfiltered": int(
        ((POS_FRAMES["QB"]["season"] == HOLDOUT_SEASON) & _week_mask(POS_FRAMES["QB"])).sum()
    ),
    "qb_train_mean_residual": float(e1_df[e1_df.position == "QB"]["mean_residual"].iloc[0]),
    "qb_shrink_bias_added": float(
        e4_df[e4_df.position == "QB"]["bias_added_by_shrink"].iloc[0]
    ),
    "qb_hybrid_2025_mae": float(
        e5_df[e5_df.season == HOLDOUT_SEASON]["hybrid_mae"].iloc[0]
    ),
    "qb_hybrid_2025_bias": float(
        e5_df[e5_df.season == HOLDOUT_SEASON]["hybrid_bias"].iloc[0]
    ),
    "qb_hybrid_2025_mean_correction": float(
        e5_df[e5_df.season == HOLDOUT_SEASON]["mean_correction"].iloc[0]
    ),
    "qb_expscript_mae_repro": mae_exp,
    "qb_expscript_bias_repro": bias_exp,
    "qb_expscript_mean_corr_repro": mean_corr_exp,
    "qb_feature_count": len(qb_features),
    "qb_nan_rate_per_season": {
        s: float(nan_summary.get(s, np.nan)) for s in nan_summary.index
    },
}
(ART_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
log.info("\nSUMMARY:\n%s", json.dumps(summary, indent=2))
log.info("All artifacts written to %s", ART_DIR)
