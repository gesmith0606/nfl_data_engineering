# Graph Inference Revert Test — deab6a6

**Date**: 2026-04-11
**Tester**: diagnostic subagent (code-implementation-specialist)
**Branch used**: `test-revert-deab6a6` (created from main, reverted deab6a6, deleted after test)

---

## What deab6a6 Changed

1. `src/player_feature_engineering.py` — `_join_wr_matchup_features()` was updated to also
   load `graph_wr_advanced` parquet (6 features: `wr_matchup_target_concentration`,
   `wr_matchup_light/heavy_box_epa`, `wr_matchup_air_yards_per_target`,
   `wr_matchup_completed_air_yards_per_target`, etc.) and `_join_te_features()` was similarly
   updated. Before this commit, WR inference had 54/60 model features; after, 60/60.

2. `src/hybrid_projection.py` — `apply_residual_correction()` gained auto-enrichment logic that
   loads Silver graph features when model metadata says `graph_features_added > 0` and the
   required columns are absent from the passed DataFrame.

---

## Training/Inference Compatibility Check

The models on disk at test time were **Ridge** models (WS1 had already swapped LGB → Ridge).
This was confirmed by `wr_residual_meta.json: model_type = "ridge"`.

The Ridge models expect 60 features including:
- `wr_matchup_target_concentration`, `wr_matchup_light_box_epa`, `wr_matchup_heavy_box_epa`
  (from `graph_wr_advanced`)

With the reverted `_join_wr_matchup_features()`, those 3 advanced features (plus 3 others)
are absent — 54/60 available, 6 imputed by the Ridge Pipeline's built-in `SimpleImputer`.

**Assessment**: Revert is safe to run (Ridge imputes missing features via median; no crash).

---

## Backtest Results

Ran: `python scripts/backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr --ml --full-features`

Log: `output/revert_deab6a6_backtest_20260410.log`
CSV: `output/backtest/backtest_half_ppr_ml_fullfeatures_20260411_000551.csv`

**Reverted inference (no graph_wr_advanced / no graph_te_advanced):**

| Position | MAE  | RMSE | Corr  | Bias  | Count |
|----------|------|------|-------|-------|-------|
| QB       | 7.03 | 8.91 | 0.353 | +0.05 | 1,367 |
| RB       | 5.25 | 7.20 | 0.456 | -0.02 | 3,094 |
| WR       | 4.89 | 6.64 | 0.353 | -0.74 | 4,616 |
| TE       | 3.83 | 5.40 | 0.312 | -0.86 | 2,106 |
| **Overall** | **5.05** | **6.91** | | **-0.47** | **11,183** |

---

## Comparison Table

| Config | Overall MAE | WR MAE | TE MAE |
|--------|-------------|--------|--------|
| v3.2 Ridge 42f (baseline) | 4.80 | 4.63 | 3.58 |
| Current LGB 60f+graph (deab6a6 intent) | 5.40 | 5.48 | 4.40 |
| **Reverted graph inference (this test)** | **5.05** | **4.89** | **3.83** |

---

## Verdict

**deab6a6 is a partial contributor to the regression, but not the root cause.**

The revert recovers WR from 5.48 → 4.89 (−0.59 MAE) and TE from 4.40 → 3.83 (−0.57 MAE),
confirming that loading `graph_wr_advanced` at inference time *hurt* rather than helped the
LGB models that were in place when deab6a6 was merged.

However, the reverted result (5.05 overall, 4.89 WR, 3.83 TE) does not fully recover to
the v3.2 baseline (4.80 overall, 4.63 WR, 3.58 TE). The remaining gap (~0.25 MAE WR, ~0.25 TE)
is caused by other changes — most likely the switch from 42-feature Ridge to 60-feature LGB
models (which WS1 is addressing with the Ridge A/B test).

**Summary**: deab6a6's `graph_wr_advanced` loading introduced noisy features that degraded the
LGB residual models. The reverted inference state (the state WS1's Ridge models are now trained
to expect) is closer to optimal and confirms that the 6 WR advanced features are not net-positive
with the current model training setup.

---

## Important Context Note

At test time, WS1 had already replaced the LGB models with Ridge models. The reverted
code ran against Ridge models (54/60 features, 6 imputed), which is the exact behavior
WS1's Ridge A/B test is designed to evaluate. The backtest output here is essentially
a free preview of the WS1 Ridge model performance — and it shows improvement over LGB+graph.

---

## Recommended Next Step

1. **Do not re-apply deab6a6's `graph_wr_advanced` loading** until Ridge models are retrained
   with those features included and show net improvement on holdout.
2. WS1's Ridge result (5.05 overall) is an improvement over LGB+graph (5.40) but still trails
   the 42-feature Ridge baseline (4.80). The gap is likely due to the 60-feature model having
   more noise than the tuned 42-feature set.
3. Consider whether `graph_wr_advanced` features should be re-introduced to training (not just
   inference) when retraining the Ridge residuals.
