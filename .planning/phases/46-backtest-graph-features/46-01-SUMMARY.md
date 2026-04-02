# Phase 46-01: Backtest Graph Features — Summary

**Completed:** 2026-04-02
**Verdict:** ALL POSITIONS SKIP — graph features do not change the ship/skip outcome

## What Was Done

### T-01: Computed Graph Features for Training Data
- Ran `compute_all_graph_features_from_data()` (pure-pandas, no Neo4j) for seasons 2020-2024
- Produced **27,926 player-week rows** of injury cascade features
- Cached to `data/silver/graph_features/season={2020..2024}/graph_injury_cascade_*.parquet`
- Feature population rates:
  - `injury_cascade_target_boost`: 25.9% non-zero (7,240 rows)
  - `injury_cascade_carry_boost`: 12.3% non-zero (3,445 rows)
  - `teammate_injured_starter`: 29.0% non-zero (8,110 rows)
  - `historical_absorption_rate`: 57.0% non-zero (15,920 rows)
- 2025 holdout has no Bronze injury data, so graph features are NaN for holdout season
- WR matchup, OL/RB, and TE features are all NaN (require PBP participation data not ingested)

### T-02: Retrained Per-Position Models with Graph Features
- SHAP feature selection picked up graph features in 3 of 4 stat-type groups:
  - **Yardage group:** `historical_absorption_rate`, `injury_cascade_carry_boost`
  - **TD group:** `injury_cascade_target_boost`, `historical_absorption_rate`
  - **Volume group:** `injury_cascade_target_boost`, `historical_absorption_rate`, `injury_cascade_carry_boost`
  - **Turnover group:** none selected
- `teammate_injured_starter` was not selected by SHAP in any group
- 14 of 18 graph features were NaN everywhere (WR/OL/TE features need participation data)

### T-03: Ship/Skip Gate Results

#### Stage 1: XGB-Only

| Position | Heuristic MAE | ML MAE (Holdout) | ML MAE (OOF) | Holdout Delta | OOF Delta | Verdict |
|----------|--------------|-------------------|--------------|---------------|-----------|---------|
| QB       | 13.348       | 3.291             | 7.850        | +75.3%        | +43.9%    | SHIP    |
| RB       | 4.182        | 3.231             | 5.205        | +22.7%        | -12.3%    | SKIP    |
| WR       | 3.599        | 3.098             | 4.924        | +13.9%        | -14.4%    | SKIP    |
| TE       | 3.034        | 2.613             | 3.660        | +13.9%        | -11.5%    | SKIP    |

#### Stage 2: Ensemble (XGB + LGB + Ridge) — SKIP positions only

| Position | Heuristic MAE | Ensemble MAE (OOF) | OOF Delta | Verdict |
|----------|--------------|---------------------|-----------|---------|
| RB       | 4.633        | 5.185               | -11.9%    | SKIP    |
| WR       | 4.304        | 4.883               | -13.4%    | SKIP    |
| TE       | 3.283        | 3.633               | -10.7%    | SKIP    |

#### Comparison to Phase 41 Baseline (Without Graph Features)

| Position | Phase 41 OOF ML MAE | Phase 46 OOF ML MAE | Change |
|----------|---------------------|---------------------|--------|
| RB       | 5.210               | 5.205               | -0.005 (negligible) |
| WR       | 4.893               | 4.924               | +0.031 (negligible) |
| TE       | 3.641               | 3.660               | +0.019 (negligible) |

### T-04: ML Projection Router
- No changes needed — QB remains the only SHIP position, same as Phase 41
- RB/WR/TE continue using heuristic projection engine

### T-05: Full Backtest Comparison
- Ran `backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr`
- Results identical to baseline (heuristic engine unchanged):
  - **Overall MAE: 4.91** (unchanged)
  - QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77 (all unchanged)

## Analysis

### Why Graph Features Did Not Help

1. **Only 4 of 18 features had data.** The WR matchup (4), OL/RB (5), and TE (4) features all require PBP participation data that is not currently ingested. These 13 features were NaN everywhere and contributed nothing.

2. **Injury cascade features have modest signal.** The 4 injury features that did populate show small SHAP importance (selected in some groups but not dominant). The absorption rate concept is sound but the pandas fallback computes a noisy signal — it tracks share deltas around injury events, which are affected by many confounders (scheme changes, matchup variance, sample size).

3. **The OOF vs holdout gap persists.** The fundamental issue from Phase 41 remains: ML models improve on holdout (+13-22% for RB/WR/TE) but degrade on OOF (-11-14%). This suggests the models overfit to validation folds in ways that happen to help on the 2025 holdout but don't generalize reliably. Graph features don't address this structural issue.

4. **2025 holdout has no graph features.** Since there's no 2025 Bronze injury data, the graph features are NaN for the holdout season. The model can't use them for holdout evaluation, so any holdout improvement from graph features is impossible to measure.

### What Would Help

- **Ingest PBP participation data** to enable the 13 currently-NaN features (WR-CB matchup, OL continuity, TE coverage rates). These are the highest-signal graph features by design.
- **Neo4j graph database** would enable richer relational queries (multi-hop paths, network centrality) that the pandas fallback can't efficiently compute.
- **Address the OOF-holdout gap** — this is the gating issue for all positions except QB. Potential approaches: different regularization, more conservative feature selection thresholds, or ensemble architectures that weight OOF stability.

## Test Suite
- 841 tests passing, 0 failures, 1 skipped
