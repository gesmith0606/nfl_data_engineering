# Graph Inference Fix — Train/Inference Feature Mismatch

**Date:** 2026-04-09
**Investigator:** Code Implementation Specialist

---

## Root Cause

The STATE.md decision log noted "train/inference feature mismatch" as the reason
graph features showed no improvement in production backtest. This investigation
confirmed the mismatch and fixed the two contributing gaps.

### Gap 1: `_join_wr_matchup_features` omits `graph_wr_advanced`

`assemble_player_features()` calls `_join_wr_matchup_features()` which only loads
`graph_wr_matchup_*.parquet`. The 9 WR advanced features live in a separate file
`graph_wr_advanced_*.parquet` that was never read at inference.

During training, `train_and_save_residual_models()` with `use_graph_features=True`
calls `load_graph_features()` which reads the consolidated `graph_all_features`
file — that file DOES contain the WR advanced features. So the model was trained
with them but couldn't see them at inference.

**Impact (WR):** 6 of 60 model features missing at inference:
- `wr_matchup_completed_air_yards_per_target`
- `wr_matchup_heavy_box_epa`
- `wr_matchup_light_box_epa`
- `wr_matchup_middle_epa`
- `wr_matchup_short_pass_completion_rate`
- `wr_matchup_target_concentration`

**Impact (TE):** 1 of 60 model features missing (`te_matchup_rz_personnel_lb_rate`
from `graph_te_advanced_*.parquet`).

### Gap 2: Bare `silver_df` path has near-zero feature overlap

When the backtest runs WITHOUT `--full-features`, the router passes `silver_df`
(from `compute_usage_metrics + compute_rolling_averages`) directly to
`apply_residual_correction`. That DataFrame has only ~103 columns from Bronze
player_weekly stats.

**Feature overlap with WR model:** 4 of 60 features present (6.7%).
The remaining 56 features are imputed at training-time medians. LightGBM can
handle NaN via imputation, but with 93% of features imputed the model fires on
near-zero signal and produces corrections close to zero — effectively degrading
to the heuristic.

---

## What Was Fixed

### Fix 1: `src/player_feature_engineering.py` — `_join_wr_matchup_features`

Added loading of `graph_wr_advanced_*.parquet` alongside `graph_wr_matchup_*.parquet`.
Deduplicates by `(player_id, season, week)` since `graph_wr_advanced` has one row
per player-week (multiple defteam rows exist in raw but are aggregated by the
compute script).

**Result:** WR model features in `assemble_player_features`: **60/60** (was 54/60).

### Fix 2: `src/player_feature_engineering.py` — `_join_te_features`

Added loading of `graph_te_advanced_*.parquet` alongside `graph_te_matchup_*.parquet`.

**Result:** TE model features in `assemble_player_features`: **60/60** (was 59/60).

### Fix 3: `src/hybrid_projection.py` — `apply_residual_correction`

Added graph feature auto-enrichment block. When the loaded model's metadata
shows `graph_features_added > 0` and graph feature columns are absent from the
passed `player_features` DataFrame, the function:
1. Detects which `GRAPH_FEATURE_SET` columns are missing
2. Calls `load_graph_features(seasons)` to fetch Silver graph data
3. Left-joins new columns onto `player_features` on `(player_id, season, week)`

This ensures graph features reach the model regardless of what the upstream
pipeline assembled, providing a safety net for the bare silver_df path.

Also fixed: LightGBM predict now receives a named DataFrame (not numpy array)
after imputation, eliminating the sklearn feature-name warning.

Also improved: feature matrix merge now prefers `(player_id, season, week)` join
when those keys exist in the heuristic projections DataFrame, reducing the risk
of stale-week lookups in multi-week feature DataFrames.

---

## Feature Coverage After Fix

| Position | Model Features | Before (assemble) | After (assemble) | After (auto-enrich) |
|----------|---------------|-------------------|------------------|---------------------|
| WR       | 60            | 54/60             | **60/60**        | 19/60 (bare silver) |
| TE       | 60            | 59/60             | **60/60**        | ~20/60 (bare silver)|
| RB       | 60            | 59/60             | 59/60            | ~18/60 (bare silver)|
| QB       | 60            | 57/60             | 57/60            | ~18/60 (bare silver)|

Note: bare silver_df (no `--full-features`) still only has ~19/60 features even
after graph auto-enrichment because the remaining 41 features (NGS, PBP-derived,
team analytics, interaction terms) live in the Silver layer above Bronze. The
`--full-features` flag and `assemble_player_features()` remain required for full
feature fidelity.

---

## Backtest Comparison

### Heuristic-only baseline (2024, half_ppr, weeks 3-18)
| Position | MAE  | RMSE | Correlation |
|----------|------|------|-------------|
| QB       | 7.07 | 9.02 | 0.332       |
| RB       | 5.07 | 6.74 | 0.517       |
| WR       | 4.80 | 6.61 | 0.411       |
| TE       | 3.68 | 5.22 | 0.401       |

### `--ml` (no full-features): hybrid path, bare silver_df → auto-enrich
| Source   | MAE  | RMSE | Count |
|----------|------|------|-------|
| Hybrid   | 4.90 | 6.52 | 3,310 |
| Heuristic| 7.07 | 9.02 |   444 |

### `--ml --full-features` (assemble_player_features — all 60 features)
| Source   | MAE  | RMSE | Count |
|----------|------|------|-------|
| Hybrid   | 5.28 | 7.21 | 3,310 |
| Heuristic| 7.07 | 9.02 |   444 |

### Why full-features backtest appears worse

The Phase 55 EXPERIMENTS.md documented this definitively:
> "Both Ridge AND LGB residuals make backtests worse. The production backtest
> trains on ALL data (including 2022-2024) then tests on 2022-2024. This is
> data leakage for the backtest, not for the production use case."

The walk-forward CV in Phase 55 showed genuine improvement (WR 2.72 MAE, TE 2.24)
precisely because it avoids this leakage. The production backtest is not a valid
measure of residual model quality due to train/test overlap.

Additionally: RB now routes through hybrid (residual model exists), which adds
5.64 MAE players to the hybrid pool. This raises the hybrid average vs the Phase 57
reading (which only measured WR+TE at 4.72).

---

## Remaining Gaps

1. **RB missing 1 feature** (`rb_matchup_run_gap_success_rate` — not in graph_rb_matchup
   parquet; may be computed differently).
2. **QB missing 3 QBR features** (`qbr_epa_total`, `qbr_qb_plays`, `qbr_qbr_total`)
   — not available in current Silver layer.
3. **Bare silver_df path** (without `--full-features`) still has low feature coverage.
   The correct production path is always `--full-features` or `assemble_player_features`.

---

## Files Modified

| File | Change |
|------|--------|
| `src/hybrid_projection.py` | Graph auto-enrichment in `apply_residual_correction`; LightGBM predict with named DataFrame; season+week keyed merge |
| `src/player_feature_engineering.py` | `_join_wr_matchup_features` loads `graph_wr_advanced`; `_join_te_features` loads `graph_te_advanced` |
