# QB LGB Residual Positive Bias — Root Cause Investigation

**Date:** 2026-04-10
**Author:** gsd-phase-researcher
**Status:** ROOT CAUSE CONFIRMED — NOT what any prior hypothesis expected
**Confidence:** HIGH

---

## Executive Summary

The QB positive bias mystery has a single root cause, and it is **not** regularization, feature pruning, label leakage, or distribution shift. It is a **train/inference heuristic mismatch** caused by a silent NaN in the QB usage multiplier.

**Root cause (confidence: HIGH):**
`unified_evaluation.compute_production_heuristic` produces **0.03 pts (98.6% zero)** for QB training rows, because `projection_engine._usage_multiplier` looks for a `snap_pct` column that is present-but-all-NaN in `assemble_multiyear_player_features()`. The function does `fillna(median)`, but the median of an all-NaN column is itself NaN, so the fillna is a no-op, the multiplier is NaN for every row, and `baseline * NaN = NaN → scoring = 0`.

Consequence: the training target becomes `residual = actual − 0 = actual`, so the LGB residual model is not learning a *correction*, it is learning to **regress directly to the actual fantasy points from features**. It outputs ~+14 points for every average QB, ~+23 for high-usage QBs, and ~0 for clearly-non-starters.

**This is confirmed by five independent pieces of evidence, any one of which is sufficient:**

1. QB `mean_heuristic = 0.032, frac_zero = 98.6%` on 4,976 training rows (E1/E4). All other positions produce heuristics in the 5–8 pt range.
2. QB `mean_residual = +14.10` (matches `mean_actual = 14.13`); all other positions have near-zero mean residuals.
3. Ceiling-shrinkage firing rate for QB is **0.0% at 12 pts, 0.0% at 18 pts, 0.0% at 23 pts** (E4). Shrinkage cannot be causing the bias because it never triggers — there is nothing to shrink.
4. Per-season eval (E5) shows that on 2016–2023 (in-sample), the model produces `heur_pts ≈ 0` and `hybrid_pts ≈ 14` with MAE ≈ 2.0. This is the model memorizing actuals, not correcting a heuristic.
5. The `unified_evaluation` heuristic is **completely different** from the production `generate_weekly_projections` heuristic for QB, because production uses a `silver_df` that has **no `snap_pct` column at all**, which triggers the `if usage_col not in df.columns: return 1.0` branch — returning a neutral multiplier and yielding a working heuristic.

**Recommended fix (confidence: HIGH):** patch `_usage_multiplier` to guard against an all-NaN column (two lines), retrain `qb_residual` against the fixed heuristic, re-evaluate on 2025 holdout. Expected behavior post-fix: training residuals will be near-zero mean; the model will learn small per-player corrections instead of adding +12 points on average.

---

## The Paradox That Obscured The Bug

| Evaluation path | QB MAE | Why |
|-----------------|--------|-----|
| Walk-forward CV | −72% MAE improvement (looked great) | Trained + evaluated on same broken-heuristic = 0 baseline; residual model memorizes the actuals |
| 2025 holdout via `experiment_regularized_residuals.py` | **4.07** (declared SHIP) | Same broken heuristic used for eval, so hybrid ≈ model prediction alone ≈ actual |
| Full-season 2025 backtest via `generate_ml_projections` | **12.87** (catastrophic), bias **+11.33**, mean correction **+11.82** | Uses DIFFERENT heuristic (real ~14 pt projections from `project_position`) then ADDS the model's ~12 pts on top |

The "looks good in experiment" and "catastrophic in production" numbers are both *correct* — they just describe two completely different evaluation pipelines that happen to share a model filename. The experiment script validates a model that predicts `actual_fantasy_points − 0`; the production backtest asks it to predict `actual − production_heuristic` but gets `actual − 0` instead.

---

## Data Analysis Results

Artifacts in `/Users/georgesmith/repos/nfl_data_engineering/.planning/phases/v4.1-phase3/artifacts/`.

### E1 — Training residual distribution by position (weeks 3–18, seasons 2016–2024)

| position | n      | mean_residual | median | std  | frac_positive | mean_heuristic | mean_actual |
|----------|--------|---------------|--------|------|---------------|----------------|-------------|
| **QB**   | 4976   | **+14.10**    | 14.12  | 9.03 | **94.0%**     | **0.032**      | 14.13       |
| RB       | 10461  | +0.62         | −0.21  | 6.19 | 48.0%         | 7.55           | 8.16        |
| WR       | 16440  | +0.17         | −0.51  | 5.73 | 43.6%         | 6.84           | 7.01        |
| TE       | 8349   | +0.20         | −0.34  | 4.58 | 44.4%         | 4.80           | 5.00        |

Read this table carefully. For RB/WR/TE the residuals are centered near zero (the model has to do real work). For QB the residuals are **centered at +14.10 with 94% positive**, because the heuristic is fundamentally broken for QBs: it returns 0.03 pts on average.

Source: `artifacts/e1_residual_distribution.csv`

### E4 — Ceiling shrinkage impact (H2 falsified)

| position | n     | % heur ≥ 12 pts | % heur ≥ 18 | % heur ≥ 23 | bias_added_by_shrink |
|----------|-------|-----------------|-------------|-------------|----------------------|
| **QB**   | 4976  | **0.000%**      | **0.000%**  | **0.000%**  | **0.000**            |
| RB       | 10461 | 24.7%           | 7.8%        | 2.5%        | +0.468               |
| WR       | 16440 | 18.5%           | 4.0%        | 0.8%        | +0.291               |
| TE       | 8349  | 6.4%            | 0.7%        | 0.1%        | +0.084               |

**Hypothesis H2 (ceiling shrinkage asymmetry) is falsified.** Ceiling shrinkage literally cannot fire for QB training rows because the heuristic never produces ≥ 12 pts for *any* QB (no row, not one). There is nothing to shrink.

As a secondary finding, shrinkage does add a small positive bias to RB/WR/TE training residuals, which is worth tracking — but it is ~0.1 to 0.5 pts, not the +11 pt catastrophe observed for QB.

Source: `artifacts/e4_ceiling_shrinkage_impact.csv`

### E2 — NaN rate for the 20 QB pruned features, by season (H4 partially relevant)

**Mean NaN rate across all 20 pruned QB features, by season:**

| season | mean NaN rate |
|--------|---------------|
| 2016   | 14.1%         |
| 2017   | 13.4%         |
| 2018   | 14.5%         |
| 2019   | 12.8%         |
| 2020   | 13.5%         |
| 2021   | 13.3%         |
| 2022   | 13.3%         |
| 2023   | 14.0%         |
| **2024** | **29.5%**   |
| **2025** | **29.6%**   |

**Features 100% missing in 2024–2025:** `qbr_qb_plays`, `qbr_epa_total`, `qbr_pts_added`, `qbr_qbr_total`. These four QBR-sourced features are gone because nflverse stopped publishing QBR data (confirmed by commit `e27f84b` from 2026-04-10).

Two other features are also notable regardless of season:
- `opp_rz_td_rate_allowed_roll3`: 65% NaN (structural — only computes when team had a recent RZ trip)
- `team_rz_trips_roll3`: 65% NaN (same reason)

So roughly **6 of 20 features are ≥ 65% NaN** by 2024 and **4 of those 6** are 100% NaN (imputed to median). A third of the feature set is carrying little signal. This is a genuine contributing issue — but it is **not the root cause**. Even with a fully populated feature set, the model would still be trained against a zero heuristic and produce +14 pt corrections. **H4 is a secondary factor, not the driver.**

Source: `artifacts/e2_qb_feature_nan_by_season.csv`

### E3 — Train vs 2025 distribution shift (H3 falsified)

Z-shift = (holdout_mean − train_mean) / train_std for each of the 20 pruned features. Values far from zero indicate covariate shift.

Notable shifts (all modest, |z| ≤ 0.17):

| feature                   | z_shift | interpretation |
|---------------------------|---------|----------------|
| rush_yards                | −0.167  | slight downshift |
| ngs_avg_completed_air_yards | −0.141 | stable |
| early_down_run_rate       | +0.143  | stable |
| off_rz_pass_rate          | −0.123  | stable |
| qb_passing_epa            | −0.016  | effectively identical |

**No QB feature shows > 0.2σ distribution shift.** The 4 QBR features show NaN (all missing in 2025), but everything else is stable. **H3 (distribution shift) is falsified** — the features are in-distribution; the model's bad behavior is not an extrapolation problem.

Source: `artifacts/e3_qb_distribution_shift.csv`

### E5 — Per-season evaluation of pruned v2 QB model

This is the most damning table. Every season, the "heuristic" (via `unified_evaluation`) is 0, the "model correction" is ~+12 to +15, and that produces a hybrid very close to the actual:

| season | n   | mean_heur | mean_correction | mean_hybrid | mean_actual | hybrid_mae | hybrid_bias |
|--------|-----|-----------|-----------------|-------------|-------------|------------|-------------|
| 2016   | 521 | 0.052     | +14.50          | 14.56       | 14.23       | 2.03       | +0.33       |
| 2017   | 516 | 0.003     | +13.81          | 13.83       | 13.93       | 1.98       | −0.11       |
| 2018   | 540 | 0.046     | +14.34          | 14.39       | 14.43       | 2.18       | −0.05       |
| 2019   | 513 | 0.034     | +14.81          | 14.85       | 14.85       | 2.16       | −0.01       |
| 2020   | 548 | 0.054     | +14.83          | 14.89       | 15.00       | 2.15       | −0.10       |
| 2021   | 587 | 0.018     | +13.88          | 13.91       | 13.75       | 2.16       | +0.16       |
| 2022   | 574 | 0.059     | +13.64          | 13.70       | 13.70       | 2.18       | +0.00       |
| 2023   | 590 | 0.004     | +13.07          | 13.08       | 13.25       | 2.06       | −0.17       |
| 2024   | 587 | 0.024     | +11.71          | 11.74       | 14.21       | **4.34**   | **−2.47**   |
| 2025   | 589 | 0.033     | +11.34          | 11.37       | 13.31       | **4.07**   | **−1.94**   |

**Interpretation of each column:**

- `mean_heur ≈ 0` for every year → heuristic is broken identically across all seasons.
- `mean_correction ≈ +14` for in-sample years (2016–2023) → the model learned the average QB is worth ~14 pts and outputs that.
- `mean_correction drops to ~+11.3` for 2024–2025 → for the two seasons where 4 of 20 features (QBR) went to 100% NaN and were imputed to training median, the model attenuates. Still way too high.
- `hybrid_bias` is the reason 2024/2025 "looks okay" in this evaluation: the model is undershooting by ~2 pts (because it's no longer seeing the QBR signal), which happens to land closer to the actual mean than the in-sample years do. But this is pure coincidence — the correction is still +11 on top of a zero baseline.
- **The 4.07 MAE on 2025 is not a real 4.07 MAE.** It is a measurement of `| actual − (0 + model_output) |` — i.e., *the LGB model's standalone MAE when asked to predict QB fantasy points directly*. A model that just outputs "11.34 for everyone" would produce comparable numbers.

Source: `artifacts/e5_per_season_qb_eval.csv`

### E5b — Subset sensitivity (H5 falsified)

Random 100/200/300/500-row subsamples of the 589-row 2025 QB holdout:

| n_sample | hybrid_mae mean | hybrid_bias mean | mean_correction mean |
|----------|-----------------|------------------|----------------------|
| 100      | 3.93            | −1.83            | +11.26               |
| 200      | 4.07            | −1.95            | +11.39               |
| 300      | 4.06            | −1.92            | +11.34               |
| 500      | 4.09            | −1.95            | +11.33               |

**Subset selection is not driving the 4.07 number.** Across 20 random trials at each sample size the MAE stays between 3.5 and 4.5 and bias stays between −1.1 and −2.5. The evaluation window was not cherry-picked. **H5 is falsified.**

Source: `artifacts/e5b_2025_subset_sensitivity.csv`

### E6 — 2025 QB per-week breakdown

Every week in 2025 shows the same pattern: `mean_heur ≈ 0`, `mean_correction ≈ +11`, `mean_hybrid ≈ mean_actual`.

| week | n  | mean_heur | mean_correction | mean_hybrid | mean_actual | hybrid_bias |
|------|----|-----------|-----------------|-------------|-------------|-------------|
| 3    | 42 | 0.00      | +10.58          | 10.58       | 11.37       | −0.79       |
| 9    | 31 | 0.30      | +13.57          | 13.86       | 17.24       | −3.38       |
| 18   | 43 | 0.00      | +8.72           | 8.72        | 10.59       | −1.87       |

Source: `artifacts/e6_qb_2025_weekly.csv`

### E7 — Worst 2025 QB corrections

Top 20 by correction magnitude — note `_heur_pts = 0.00` on every single row:

| season | week | player | heur | correction | hybrid | actual |
|--------|------|--------|------|------------|--------|--------|
| 2025   | 15   | T.Lawrence  | 0.00 | +26.75 | 26.75 | 44.30 |
| 2025   | 5    | J.Daniels   | 0.00 | +26.71 | 26.71 | 17.14 |
| 2025   | 17   | D.Maye      | 0.00 | +26.21 | 26.21 | 32.44 |
| 2025   | 13   | J.Love      | 0.00 | +25.20 | 25.20 | 25.76 |
| 2025   | 11   | J.Allen     | 0.00 | +23.11 | 23.11 | 42.68 |

The model is doing the entire job alone, with the heuristic contributing nothing. Also notable: the model knows to output ~0 for backup QBs (bottom-20 corrections all fall in [−1.4, +0.4] and `max(0, hybrid)` floors them to zero). So the model is legitimately predicting usage from features — it's just not correcting anything, it's replacing.

Source: `artifacts/e7_top20_corrections.csv`, `artifacts/e7_bot20_corrections.csv`

### E8 — Reproducing the experiment script's reported 4.07 MAE

With the exact filtering used by `experiment_regularized_residuals.py` (`train_mask = season != 2025 & week ∈ [3,18] & heur.notna() & actual.notna()`, same for holdout):

```
n=589, MAE=4.071, bias=-1.938, mean_corr=+11.337
Heuristic-only on same subset: MAE=13.348
```

The reported 4.07 MAE is reproducible. The "winner vs heuristic delta" of −4.57 that the experiment used (`4.07 − 8.64`) compared against the **wrong** baseline: 8.64 is the production heuristic MAE (from `project_position`), but the experiment's internal baseline is 13.35 because it used the broken `unified_evaluation` heuristic. The experiment script's "−4.57 improvement" was masking the fact that the hybrid was 4.07 vs a correctly-measured broken baseline of 13.35, i.e., a **−9.28 improvement against its own baseline** — which should have been the red flag: a 20-feature LGB residual should not beat its own baseline by 9 points, because residuals shouldn't have that much signal by definition.

Source: `artifacts/summary.json`, the full log embedded in `qb_investigation.py` output.

---

## The Bug — Exact Location

**File:** `src/projection_engine.py`, lines 150–167

```python
def _usage_multiplier(df: pd.DataFrame, position: str) -> pd.Series:
    usage_col = USAGE_STABILITY_STAT.get(position, "snap_pct")  # QB -> "snap_pct"
    if usage_col not in df.columns:
        return pd.Series(1.0, index=df.index)              # <-- production path takes this

    usage = df[usage_col].fillna(df[usage_col].median())   # <-- training path dies here
    # If df["snap_pct"] is all-NaN:
    #   df[usage_col].median() == NaN
    #   fillna(NaN) is a no-op → usage stays all-NaN
    #   percentile = rank(pct=True) on all-NaN → all-NaN
    #   multiplier = 0.80 + 0.35*NaN = NaN → .clip(0.80, 1.15) stays NaN
    percentile = usage.rank(pct=True)
    multiplier = 0.80 + 0.35 * percentile
    return multiplier.clip(0.80, 1.15)
```

**Where the divergence comes from:**

| Code path | Does `silver_df["snap_pct"]` exist? | Does it contain real values? | `_usage_multiplier` returns |
|-----------|-------------------------------------|------------------------------|-----------------------------|
| `generate_weekly_projections` (production backtest) via `build_silver_features → compute_usage_metrics(weekly_df, snap_df=None) → compute_rolling_averages` | **No** (column never created — `compute_usage_metrics` only adds `snap_pct` when `snap_df` is passed) | — | **1.0 (neutral)** — works fine |
| `compute_production_heuristic` (training via `train_residual_models` / `experiment_regularized_residuals`) via `assemble_multiyear_player_features` | **Yes** (column present in feature vector) | **No** (100% NaN — `snap_pct` is listed in `_SAME_WEEK_RAW_STATS` as a leakage source and the feature engineer deliberately blanks it) | **NaN for every row → heuristic = 0** |

This is a textbook train/inference mismatch caused by two well-intentioned but uncoordinated changes:

1. `player_feature_engineering.py` intentionally zeroes `snap_pct` to prevent same-week leakage. It expects consumers to use `snap_pct_roll3` instead.
2. `projection_engine.py` still refers to `snap_pct` (not `snap_pct_roll3`) in `USAGE_STABILITY_STAT["QB"]`.

Neither file is wrong in isolation. The bug is the gap between them.

**Why only QB is affected:** the same pattern exists for RB/WR/TE *but they use different usage columns* — RB uses `carry_share` (0% NaN), WR uses `target_share` (0% NaN), TE uses `target_share` (0% NaN). Only QB is pinned to `snap_pct`, and only QB dies.

---

## Hypothesis Rankings (from the prompt)

| # | Hypothesis | Verdict | Evidence |
|---|------------|---------|----------|
| **H0** | **Train/inference heuristic mismatch (not listed)** | **CONFIRMED** | E1, E4, E5 — heuristic = 0.03 for QB training, ≈ 14 pts in production |
| H1 | Training residuals positively biased (ceiling shrinkage undershoots high-scoring QBs) | **Partially right direction, wrong mechanism.** Residuals ARE positive by +14.10, but not because of ceiling shrinkage (E4 shows shrinkage never fires for QB). The +14.10 comes from heuristic = 0, not from shrinkage of 23-pt projections. | E1 + E4 |
| H2 | Ceiling shrinkage applied inconsistently between train and inference | **Falsified.** Shrinkage would only matter if the heuristic produced projections ≥ 12 pts, which it never does for QB in training (E4: 0.0% trigger rate). | E4 |
| H3 | Label leakage in the 20 QB features (missing `shift(1)`) | **Falsified.** Distribution shift z-scores all |z| ≤ 0.17; the best feature `qb_passing_epa` has train mean 1.54 vs holdout 1.37 — same distribution. No leakage signature. | E3 |
| H4 | 2024+ QB features are all NaN → model defaults to training mean | **Secondary contributor, not root cause.** 4 of 20 features (QBR family) are 100% NaN from 2024 onward, and the average NaN rate doubles from ~13% to ~30%. This pushes the 2024/2025 correction DOWN from +14 to +11 (E5). So the QBR gap is actually *suppressing* the bias, not causing it. Even with all features present, the bug would still exist — see 2016–2023 in E5 showing bias magnitude ~+14. | E2, E5 |
| H5 | Evaluation subset was cherry-picked | **Falsified.** N=589 covers the full 2025 QB population (weeks 3–18, valid heuristic + actual). Bootstrap subsamples show the MAE and bias are stable across random slices. | E5b, E8 |

The prompt didn't list the actual cause, which is why all five provided hypotheses are wrong. H1 is "directionally right" in that the residuals are positively biased, but the mechanism is totally different from what the hypothesis described.

---

## Why This Was Not Caught Earlier

1. **The training script logged `train_residual_mae = 2.11`** (for v1) and `~2.1` for v2 — these looked like "well-fit" numbers because they were comparing the model against *the wrong thing*. A residual MAE of 2.1 on a target that ranges ±30 actually is very low — but that's because the target is the actual fantasy points, not a residual, and predicting QB fantasy points to 2 pts MAE is the correct performance of a direct-to-stat model.
2. **The `_usage_multiplier` function returns silently** — no warning, no error, just NaN multiplication. `calculate_fantasy_points_df` then takes the NaN and produces 0.
3. **`generate_heuristic_predictions`** (used by the earlier `train_residual_model` walk-forward CV path) is a different function than `compute_production_heuristic`, and may or may not have the same bug — they should both be audited.
4. **The v1 model was trained with 60 features** including features like `travel_miles`, `temperature`, `wind_speed`, etc. With so many features, the model could fit the "regress to actual" target even without QBR; so v1's train residual MAE was 2.11. When pruned to 20 features, 4 of which became all-NaN in 2024–2025, the model's ability to regress to actual degraded slightly, and the mean correction fell from ~+14 to ~+11. That ~3-pt reduction in the 2024–2025 mean correction *looked* like an improvement because bias got closer to zero, but the underlying bug was the same.
5. **Production backtest uses `silver_df` (no `snap_pct` column)**, not the full feature vector; so production heuristic works correctly and the mismatch only manifests in training/evaluation.

The phase 2 ship gate explicitly noted: *"training holdout (2.44 MAE) evaluated on a slice where heuristics and QB performance were stable; the full-season production path sees more diverse conditions."* That read as "distribution shift across slices." It was actually: "the experiment script evaluates against a broken baseline that happens to be compatible with the model's broken training target."

---

## Recommended Fix

### Step 1 — Patch `_usage_multiplier` to handle the all-NaN case (5 minutes)

`src/projection_engine.py`, lines 150–167:

```python
def _usage_multiplier(df: pd.DataFrame, position: str) -> pd.Series:
    usage_col = USAGE_STABILITY_STAT.get(position, "snap_pct")
    if usage_col not in df.columns:
        return pd.Series(1.0, index=df.index)

    col = df[usage_col]
    # Guard against all-NaN columns — fillna(NaN) is a no-op and would
    # propagate NaN through the entire projection pipeline.
    if col.isna().all():
        logger.warning(
            "_usage_multiplier: %s is all-NaN for position=%s; "
            "returning neutral 1.0", usage_col, position
        )
        return pd.Series(1.0, index=df.index)

    usage = col.fillna(col.median())
    percentile = usage.rank(pct=True)
    multiplier = 0.80 + 0.35 * percentile
    return multiplier.clip(0.80, 1.15)
```

This is minimally invasive and matches the behavior of the "column missing" branch on line 160–161. It restores symmetry between "column missing" and "column all-NaN."

### Step 2 — Decide the correct QB usage column

`USAGE_STABILITY_STAT["QB"]` is currently `"snap_pct"`, which is a same-week leaked column anyway. The canonical lagged replacement is `snap_pct_roll3`, which IS populated in `assemble_multiyear_player_features` (verified via `compute_rolling_averages`). Options, in preference order:

1. **Change `USAGE_STABILITY_STAT["QB"]` to `"snap_pct_roll3"`** and similarly change RB/WR/TE entries that refer to `carry_share` / `target_share` (the current values are actually same-week shares — also leakage!) to their `_roll3` counterparts. This is the correct long-term fix and eliminates a whole class of leakage.
2. If changing the column breaks the production path (because `silver_df` doesn't carry `snap_pct_roll3` either), add a fallback: try `snap_pct_roll3`, then `snap_pct`, then return 1.0.

Verify which rolling columns are available in `build_silver_features`'s output (our E check showed `passing_yards_roll3` is populated, so `snap_pct_roll3` should be computable if snap data is merged in).

### Step 3 — Retrain the QB residual model against the fixed heuristic

```bash
source venv/bin/activate
python scripts/experiment_regularized_residuals.py \
    --positions qb \
    --clip-threshold 3.0 \
    --save-best \
    --output-log output/qb_retrain_post_fix.json
```

Expected post-fix characteristics:
- Training residual mean should move from +14.10 toward 0 (±1.0).
- Training residual std should drop from 9.03 toward ~4–5 (similar to RB/WR/TE scale).
- Holdout MAE vs heuristic should be a small delta (the residual signal is small by definition).
- **If the training residual mean is still +14.10 after the fix, the fix did not take effect** — don't ship.

### Step 4 — Sanity-check the other positions

Re-run E1 after the fix to confirm:
- QB mean_residual ≈ 0 (not +14)
- RB/WR/TE mean_residuals unchanged (they were already fine because their `USAGE_STABILITY_STAT` columns are populated in both paths)

Also verify: is the assembled multi-year feature DataFrame's `carry_share` and `target_share` genuinely same-week (leakage) or lagged? Our E3 showed `carry_share` mean 0.32 for RBs and `target_share` mean 0.146 for WRs — those are realistic values, suggesting the feature engineer does populate them. If they are the same-week values (leakage), they should be replaced too.

### Step 5 — Audit `generate_heuristic_predictions` in `player_model_training.py`

The walk-forward CV path (`train_residual_model` in `hybrid_projection.py`) uses `generate_heuristic_predictions` from `player_model_training`, NOT `compute_production_heuristic`. The two paths may have independent implementations — if both have the snap_pct bug, fix both. If only one does, understand why the walk-forward CV "−72% MAE improvement" number looked good: it may have been measuring the same memorization effect.

### Step 6 — Re-run the full-season 2025 backtest with the retrained model

Only ship the model if the backtest shows `|bias| < 1.0` and `MAE ≤ 8.0` (slightly better than the 8.64 heuristic baseline). Anything worse than that means the corrected residual signal is too small to be worth the complexity and QB should stay on heuristic.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Fix reveals that the QB residual signal is genuinely tiny, and the model fails to beat heuristic even after retraining | **MEDIUM-HIGH** | QB stays on heuristic; no regression but no improvement | Accept it. The ship gate was wrong; being honest is the right outcome. 8.64 MAE is the floor. |
| Same bug exists for RB/WR/TE but was masked by working `carry_share`/`target_share` values — but those same-week columns are also leakage | **MEDIUM** | Hidden leakage in the current RB/WR/TE hybrid models that's silently boosting their training scores | Audit `carry_share` / `target_share` as part of Step 4. May require retraining RB/WR/TE too. |
| Retrained QB residual with the corrected heuristic still overshoots because the underlying features don't carry stationary residual signal | **MEDIUM** | QB stays on heuristic | This is actually the *correct* conclusion. The 8.64 heuristic MAE is the real floor until we add more predictive features (graph matchups, QB injury tracking, etc.). |
| The fix changes the meaning of RB/WR/TE usage multipliers subtly (they're currently fine but the guardrail might kick in edge cases) | **LOW** | RB/WR/TE projections shift by small amounts | Re-run full backtest after fix; compare overall MAE across all positions. |
| There's ANOTHER bug hiding under this one (e.g., `calculate_fantasy_points_df` silently zeroing NaN inputs) | **LOW-MEDIUM** | A second retraining may still not produce a healthy residual model | The fantasy calculator behavior is intentional — NaN stats → 0 points is correct (missing data = no contribution). Not a bug; just worth knowing. |
| The bug also affects the kicker projection pipeline | **UNKNOWN** | Kicker projections may be zero for every row | Quick audit: check if `USAGE_STABILITY_STAT` is referenced for kickers at all. Kickers aren't in `POSITION_STAT_PROFILE`, so `project_position` wouldn't be called — likely safe. |
| The bug was there "forever" — historical QB MAE numbers might be wrong | **LOW** | Past reports in .planning/ are slightly inaccurate for QB comparisons | Not worth retroactive correction; document the discovery in phase3 and move forward. |

---

## Reproduction

All experiments are reproducible by running:

```bash
source venv/bin/activate
python .planning/phases/v4.1-phase3/artifacts/qb_investigation.py
python .planning/phases/v4.1-phase3/artifacts/qb_heuristic_debug.py
python .planning/phases/v4.1-phase3/artifacts/qb_snap_pct_check.py
```

Artifacts written:
- `artifacts/e1_residual_distribution.csv` — residual stats by position
- `artifacts/e2_qb_feature_nan_by_season.csv` — feature NaN heatmap
- `artifacts/e3_qb_distribution_shift.csv` — train vs holdout z-shifts
- `artifacts/e4_ceiling_shrinkage_impact.csv` — shrinkage trigger rates
- `artifacts/e5_per_season_qb_eval.csv` — per-season hybrid evaluation
- `artifacts/e5b_2025_subset_sensitivity.csv` — bootstrap subsets
- `artifacts/e6_qb_2025_weekly.csv` — per-week 2025 breakdown
- `artifacts/e7_top20_corrections.csv` / `e7_bot20_corrections.csv` — extreme corrections
- `artifacts/summary.json` — headline numbers

---

## One-Line Summary

**The QB residual model was trained against a heuristic that was producing 0.03 points per QB, because `_usage_multiplier` does `fillna(median)` on an all-NaN `snap_pct` column; the "−4.57 MAE improvement" was the model memorizing actuals against a broken baseline, and the +11.82 production bias is exactly the ~14-pt mean QB score that it learned to add to any projection.**
