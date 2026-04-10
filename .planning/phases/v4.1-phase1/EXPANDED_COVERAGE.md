# v4.1 Phase 1: Expand Hybrid Coverage

**Date:** 2026-04-10
**Objective:** Lower overall MAE below 4.5 by expanding hybrid model coverage beyond WR/TE
**Result:** HYBRID_POSITIONS remains {"WR", "TE"} -- both RB and QB routing degraded on sealed 2025 holdout

## Baseline (v3.2, WR/TE Hybrid Only)

### 2024 (in-sample, training set overlap)

| Metric | Value |
|--------|-------|
| Player-weeks | 3,754 |
| Overall MAE | 5.10 |
| Hybrid (WR/TE) MAE | 4.72 |
| Heuristic (QB/RB) MAE | 5.66 |

### 2025 (sealed holdout, no training overlap)

| Metric | Value |
|--------|-------|
| Player-weeks | 4,836 |
| Overall MAE | 5.26 |
| RMSE | 7.43 |
| Correlation | 0.421 |
| Bias | +0.60 |

| Position | MAE | RMSE | Corr | Count |
|----------|------|------|------|-------|
| QB | 8.64 | 10.66 | 0.131 | 560 |
| RB | 5.39 | 7.79 | 0.417 | 1,348 |
| WR | 4.73 | 6.70 | 0.395 | 2,008 |
| TE | 4.18 | 5.83 | 0.351 | 920 |

| Source | MAE | Count | % |
|--------|------|-------|---|
| Hybrid (WR+TE) | 4.56 | 2,928 | 61% |
| Heuristic (QB+RB) | 6.34 | 1,908 | 39% |

## Experiment 1: RB Hybrid Routing

**Hypothesis:** Walk-forward CV showed RB -25.1% MAE improvement (5.00 -> 3.15 MAE), so routing RB through LGB residual should improve production.

**Change:** `HYBRID_POSITIONS = {"WR", "TE", "RB"}`

### Result on 2025 Sealed Holdout

| Metric | Baseline | RB Hybrid | Delta |
|--------|----------|-----------|-------|
| Overall MAE | 5.26 | 5.43 | **+0.17 (worse)** |
| RB MAE | 5.39 | 5.98 | **+0.59 (+11% worse)** |
| Hybrid MAE | 4.56 | 5.01 | +0.45 (worse, diluted by RB) |

### Root Cause Analysis

The RB LGB residual model was trained on 2016-2024 data. On 2025:

- Mean correction: **+0.77 pts (upward bias)** -- model systematically inflates RB projections
- When correction is positive (+corr): heuristic MAE 5.85 -> hybrid MAE 7.93 (+2.08 worse)
- When correction is negative (-corr): heuristic MAE 7.73 -> hybrid MAE 6.60 (-1.13 better)
- Net: Positive corrections outnumber and outweigh negative corrections

The walk-forward CV trains on data *before* each val season, so it avoids overfitting to the test period. The production model trains on ALL 2016-2024 data and applies to 2025 -- a different player pool, schedule, and usage pattern.

**Decision:** Revert RB to heuristic. The LGB residual model overfits to 2016-2024 patterns.

## Experiment 2: QB Routing Investigation

### Finding 1: XGB SHIP Path is Architecturally Broken

The QB XGBoost SHIP path (direct stat prediction) has been silently failing since deployment:

1. **Feature file format bug:** `_load_feature_cols()` read `{"group": ..., "features": [...]}` as a raw dict, then iterated the keys `["group", "features"]` instead of the feature list. Zero features matched -> all NaN predictions -> 0.0 fantasy points.

2. **Duplicate column bug:** After renaming `proj_{stat}` -> `{stat}`, the DataFrame had duplicate column names (raw stat from silver_df + renamed pred). `calculate_fantasy_points_df` triggered `'<' not supported between str and int` via pandas index alignment.

3. **Feature mismatch (deeper):** Even with bugs 1+2 fixed, XGB models expect ~80 features including `qbr_epa_total`, `qbr_qb_plays`, `qbr_qbr_total`, `qbr_qb_plays_roll6` -- which are absent from both silver_df and the `--full-features` feature_df pipeline. The SHIP path falls back to heuristic after throwing `feature_names mismatch`.

**Bottom line:** QB has been on pure heuristic projections all along -- the SHIP verdict in `ship_gate_report.json` never translated to actual ML predictions.

### Finding 2: QB LGB Hybrid Routing Catastrophically Fails

**Hypothesis:** Since XGB SHIP is broken, route QB through LGB residual (walk-forward CV showed -72% improvement).

**Change:** `HYBRID_POSITIONS = {"WR", "TE", "QB"}`

### Result on 2025 Sealed Holdout

| Metric | Baseline (heuristic) | QB Hybrid | Delta |
|--------|---------------------|-----------|-------|
| QB MAE | 8.64 | 16.15 | **+7.51 (+87% worse)** |
| QB Bias | +1.52 | +14.91 | **+13.39** |
| Overall MAE | 5.26 | 6.13 | +0.87 |

The LGB residual model adds roughly **+15 points** to every QB projection. Top misses included J.Allen W3 projected 44.2 (actual 0.0), D.Jones W3 projected 43.0 (actual 0.0).

### Root Cause

- QB residual model was trained on 2016-2024 residuals with features including `travel_miles`, `temperature`, `rb_weighted_epa`, etc.
- These features don't transfer stably to a new season (2025)
- Of 60 SHAP-selected features, 7 were imputed to median at inference (missing from player_features)
- The model trained on 4,976 QB-weeks with train MAE 2.11 -- very low, suggesting overfitting
- Also surfaced a duplicate-row bug: apply_residual_correction's merge creates fan-out duplicates for QBs with the same player_name

**Decision:** Revert QB to heuristic (via the broken XGB SHIP path). Both ML approaches -- XGB direct and LGB residual -- are worse than the 8.64 MAE heuristic for QB on 2025.

## Experiment 3: Lower Minimum Training History Threshold

**Finding:** There is no minimum training history threshold to lower.

The 40% of player-weeks on heuristic = QB (560) + RB (1,348). These are NOT low-history players falling through a filter -- they are entire positions (QB/RB) that route through the broken XGB SHIP path and silently fall back to heuristic.

The `_is_fallback_player()` function (min_games=3) only applies within the SHIP path. The HYBRID path (used by WR/TE) applies residual correction to ALL players regardless of history. There is no threshold to lower.

## Bug Fixes Committed

| Bug | Fix | Impact |
|-----|-----|--------|
| Feature file format | `_load_feature_cols()` now handles `{"group":..., "features":[...]}` format | Unblocks future XGB SHIP work |
| Duplicate column names | Build clean scoring DataFrame from proj_* columns only | Prevents phantom NaN predictions |

These fixes surface the real blocker (feature_names mismatch) instead of silently returning heuristic.

## Why Walk-Forward CV Doesn't Predict Production

| Factor | Walk-Forward CV | Production |
|--------|----------------|------------|
| Training data | Seasons < val_season only | All 2016-2024 |
| Test data | Same season as recent training | New 2025 season |
| Feature coverage | Full feature vector | Missing features -> imputation |
| Player pool | Established players with history | New players, different usage |
| Model training MAE | Low (well-fit) | Low (overfitting) |

The core issue: walk-forward CV tests on the SAME temporal distribution as training (just a held-out year). Production tests on a TRULY UNSEEN future year with different players, schedules, and conditions.

## Recommendations for v4.2

1. **Retrain RB/QB residuals with stricter regularization** -- increase `min_child_samples` from 20 to 40, reduce `n_estimators` from 500 to 200, add stronger L1/L2
2. **Feature pruning** -- remove non-causal features (travel_miles, temperature) from QB model; focus on rolling stat features only
3. **Damped corrections** -- clip residual corrections to [-3, +3] and multiply by 0.5 for QB/RB
4. **Re-validate on 2025 sealed holdout** before shipping any new position routing
5. **Fix XGB SHIP path** -- wire full feature engineering pipeline into SHIP branch (requires adding QBR columns to player_feature_engineering.py)
6. **Fix apply_residual_correction duplicate rows** -- add player_id-based merge or drop_duplicates guard

## Final State

```python
HYBRID_POSITIONS = {"WR", "TE"}  # Unchanged from v3.2
```

**2025 holdout MAE: 5.26** (unchanged from baseline)
**Target (4.5): NOT MET** -- requires fundamentally different approach, not just routing changes
