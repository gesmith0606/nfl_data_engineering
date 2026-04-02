---
phase: 53-model-architecture-improvements
plan: 02
subsystem: ml
tags: [data-expansion, player-models, walk-forward-cv, overfitting-test, 2016-2025]

key-files:
  modified:
    - src/player_model_training.py

key-decisions:
  - "Expanded PLAYER_VALIDATION_SEASONS from [2022,2023,2024] to [2019,2020,2021,2022,2023,2024] to leverage new data"
  - "Data expansion did NOT fix OOF overfitting — RB/WR/TE still SKIP across all model types"
  - "QB remains the only position where ML ships (XGB: 6.72 vs heuristic 14.16)"

requirements-completed: [53-02]

duration: 8min
completed: 2026-04-02
---

# Phase 53 Plan 02: Expanded Training Data (2016-2025) Ship Gate Results

**Hypothesis: More training data (51,758 vs ~31,000 player-weeks) fixes OOF overfitting for RB/WR/TE.**

**Result: HYPOTHESIS REJECTED. Data expansion improved some numbers marginally but did not flip any SKIP to SHIP.**

## Configuration Changes

- `PLAYER_DATA_SEASONS`: 2016-2025 (10 seasons, was 2020-2025 / 6 seasons)
- `PLAYER_VALIDATION_SEASONS`: [2019, 2020, 2021, 2022, 2023, 2024] (6 folds, was 3 folds)
- Total player-weeks: 51,758 (was ~31,000)
- Walk-forward CV: train on 2016..N-1, validate on N (6 folds instead of 3)

## Ship Gate Results (OOF, half-PPR)

### Stage 1: XGBoost (2016-2025 data)

| Position | Heuristic MAE | XGB OOF MAE | Delta % | Verdict |
|----------|--------------|-------------|---------|---------|
| QB       | 14.16        | 6.72        | +52.5%  | SHIP    |
| RB       | 4.72         | 5.01        | -6.0%   | SKIP    |
| WR       | 4.33         | 4.68        | -8.0%   | SKIP    |
| TE       | 3.37         | 3.56        | -5.7%   | SKIP    |

### Stage 1: Ridge (2016-2025 data)

| Position | Heuristic MAE | Ridge OOF MAE | Delta % | Verdict |
|----------|--------------|---------------|---------|---------|
| QB       | 14.16        | 7.52          | +46.9%  | SHIP    |
| RB       | 4.72         | 5.57          | -17.9%  | SKIP    |
| WR       | 4.33         | 4.62          | -6.5%   | SKIP    |
| TE       | 3.37         | 3.53          | -4.7%   | SKIP    |

### Stage 2: XGB+LGB+Ridge Ensemble (2016-2025 data)

| Position | Heuristic MAE | Ensemble OOF MAE | Delta % | Verdict |
|----------|--------------|------------------|---------|---------|
| RB       | 4.72         | 4.97             | -5.2%   | SKIP    |
| WR       | 4.33         | 4.66             | -7.5%   | SKIP    |
| TE       | 3.37         | 3.55             | -5.4%   | SKIP    |

## Comparison: Old (2020-25) vs New (2016-25)

| Position | Heuristic (backtest) | XGB 2020-25 OOF | XGB 2016-25 OOF | Ridge 2016-25 OOF | Ensemble 2016-25 | Decision |
|----------|---------------------|-----------------|-----------------|-------------------|------------------|----------|
| QB       | 6.58                | 7.84*           | 6.72            | 7.52              | ---              | SHIP (XGB) |
| RB       | 5.06                | 5.22            | 5.01            | 5.57              | 4.97             | SKIP     |
| WR       | 4.85                | 4.93            | 4.68            | 4.62              | 4.66             | SKIP     |
| TE       | 3.77                | 3.66            | 3.56            | 3.53              | 3.55             | SKIP     |

*QB was already SHIP in Phase 41 (different heuristic baseline in OOF context vs backtest context).

**Important note on heuristic baselines:** The heuristic MAEs in the training script (14.16 for QB, 4.72 for RB, 4.33 for WR, 3.37 for TE) differ from the backtest baselines (6.58, 5.06, 4.85, 3.77) because:
1. Training script evaluates on OOF rows from 6 validation seasons (2019-2024), including early-season weeks
2. Backtest evaluates on 2022-2024 weeks 3-18 only with tuned projection parameters
3. The ship gate compares ML vs heuristic on *identical rows*, so the relative comparison is valid

## Key Observations

1. **QB improved significantly**: XGB OOF dropped from 7.84 to 6.72 (+14.3% better) with more data. QB remains a clear SHIP.

2. **RB/WR/TE improved marginally but still lose to heuristic**:
   - RB XGB: 5.22 -> 5.01 (4% better) but still -6% vs heuristic
   - WR XGB: 4.93 -> 4.68 (5% better) but still -8% vs heuristic
   - TE XGB: 3.66 -> 3.56 (3% better) but still -5.7% vs heuristic

3. **Ridge slightly beats XGB for WR (4.62 vs 4.68) and TE (3.53 vs 3.56)** but still loses to heuristic.

4. **Ensemble provides minimal lift over XGB alone** (RB: 4.97 vs 5.01, WR: 4.66 vs 4.68, TE: 3.55 vs 3.56).

5. **The gap between ML and heuristic is structural, not data-limited.** More data helped ML get closer but the heuristic's rolling-average approach is fundamentally well-suited to these positions where consistency matters more than feature-driven prediction.

## Why Heuristic Wins for RB/WR/TE

The heuristic projection model uses:
- Recency-weighted rolling averages (roll3: 45%, roll6: 30%, std: 25%)
- Usage multiplier, matchup adjustment, Vegas multiplier
- Position-specific ceiling shrinkage

This is hard to beat because:
- Fantasy football for skill positions is largely explained by recent usage patterns
- ML models must predict many individual stats (rushing_yards, rushing_tds, etc.) and errors compound when aggregating to fantasy points
- The heuristic directly models the aggregate outcome pattern

## No Pipeline Changes Needed

Since no new positions passed the ship gate, the ML projection router remains unchanged:
- QB: ML (XGB) -- already wired in Phase 42
- RB/WR/TE: Heuristic -- remains the production model

## Test Results

870 tests passing, 1 skipped, 0 failures.

## Conclusion

**Data expansion from 6 to 10 seasons was NOT sufficient to flip RB/WR/TE from SKIP to SHIP.** The overfitting problem is structural: ML models struggle to beat a well-tuned rolling-average heuristic for these positions. Further improvements would require:
- Better features (e.g., graph-based WR-CB matchup features from Neo4j)
- Different modeling targets (e.g., predicting fantasy points directly instead of individual stats)
- Hybrid approaches (e.g., ML adjustments on top of heuristic baseline)

---
*Phase: 53-model-architecture-improvements*
*Completed: 2026-04-02*
