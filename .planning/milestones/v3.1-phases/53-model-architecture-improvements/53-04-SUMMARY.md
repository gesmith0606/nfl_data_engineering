# Phase 53-04: Production Residual Experiment

## Objective

Test whether residual correction improves the PRODUCTION heuristic (not the simplified version tested in 53-03). The production heuristic includes ceiling shrinkage, matchup factor [0.85-1.15], and usage multiplier [0.80-1.15].

## Experiment Setup

- **Data**: 51,758 player-weeks across 2016-2025 (PLAYER_DATA_SEASONS), holdout 2025 excluded
- **Evaluation window**: Seasons 2022-2024, weeks 3-18
- **Scoring**: Half-PPR
- **Production heuristic**: `_weighted_baseline * usage_mult * matchup_factor`, then `calculate_fantasy_points_df`, then `PROJECTION_CEILING_SHRINKAGE` (15/20/25 pt thresholds). Same pipeline as `project_position()` in projection_engine.py. Does NOT include Vegas multiplier (unavailable in historical feature data) or bye week zeroing.
- **Residual model**: RidgeCV on 466 features -> (actual - production_heuristic), walk-forward CV (train on seasons < val, predict val)
- **Opponent rankings**: Built from Bronze weekly + schedule data via `compute_opponent_rankings()`

## Results

| POSITION | PROD HEUR MAE | PROD+RESID MAE | IMPROVEMENT | DECISION |
|----------|--------------|----------------|-------------|----------|
| QB       | 13.742       | 4.355          | +68.3%      | SKIP*    |
| RB       | 4.249        | 3.649          | +14.1%      | SKIP*    |
| WR       | 4.026        | 3.124          | +22.4%      | SHIP     |
| TE       | 3.122        | 2.509          | +19.6%      | SHIP     |
| Overall  | 5.117        | 3.287          | +35.8%      |          |

*QB/RB SKIP because standalone ML (from 53-03) already achieves QB 3.312, RB 3.274 which are better than residual QB 4.355, RB 3.649. For these positions, pure ML is superior.

### Per-Fold Stability

**WR** (consistent across all 3 folds):
- 2022: Heur 4.190 -> Hybrid 3.200 (-23.6%), Ridge alpha=4.7
- 2023: Heur 3.881 -> Hybrid 3.033 (-21.8%), Ridge alpha=3.6
- 2024: Heur 4.013 -> Hybrid 3.142 (-21.7%), Ridge alpha=8.3

**TE** (consistent across all 3 folds):
- 2022: Heur 3.345 -> Hybrid 2.675 (-20.0%), Ridge alpha=0.37
- 2023: Heur 3.026 -> Hybrid 2.387 (-21.1%), Ridge alpha=0.28
- 2024: Heur 2.996 -> Hybrid 2.465 (-17.7%), Ridge alpha=0.49

### Comparison to ML Standalone (from 53-03)

| Position | ML Standalone | Prod Residual | Winner |
|----------|--------------|---------------|--------|
| QB       | 3.312        | 4.355         | ML     |
| RB       | 3.274        | 3.649         | ML     |
| WR       | 3.553        | 3.124         | Residual (-12.1%) |
| TE       | 2.785        | 2.509         | Residual (-9.9%)  |

## Key Findings

1. **Production residual beats standalone ML for WR and TE.** WR improves from 3.553 to 3.124 (-12.1%), TE from 2.785 to 2.509 (-9.9%). This holds across all 3 validation folds consistently.

2. **The production heuristic provides complementary signal for WR/TE.** The heuristic's rolling averages capture "player identity" (target share, receiving volume) while ML captures "situation" (matchup, team context, graph features). For WR/TE, the residual approach combines both signals optimally.

3. **QB and RB should remain on standalone ML.** The residual model over-corrects for backup QBs (mean residual +14 pts, indicating the heuristic grossly over-projects backups). For RB, standalone ML's 3.274 beats residual's 3.649.

4. **Population note**: These MAE numbers are on the FULL player population (all player-weeks in the feature data), including low-usage backups. The production backtest MAE of 4.91 is on a filtered population (only players who appear in both projections and actuals). The relative improvements are valid for comparison.

5. **Ridge regularization patterns**: WR uses moderate alpha (4-8), TE uses low alpha (0.3-0.5). TE's lower alpha means Ridge is making more confident corrections, consistent with TE being more predictable (smaller target population, more stable roles).

## Decision

**SHIP for WR and TE.** The residual model consistently and substantially beats both the production heuristic and standalone ML for these positions.

**SKIP for QB and RB.** Standalone ML already beats the residual approach for these positions.

## Optimal Position Router

Based on 53-03 and 53-04 combined results:

| Position | Best Approach        | MAE   |
|----------|---------------------|-------|
| QB       | ML Standalone (XGB) | 3.312 |
| RB       | ML Standalone (XGB) | 3.274 |
| WR       | Production Residual  | 3.124 |
| TE       | Production Residual  | 2.509 |

## Next Steps

- Wire WR/TE residual correction into the ML projection router
- Production heuristic + Ridge residual for WR/TE
- ML standalone (XGB) for QB/RB
- Add `--hybrid` flag or make residual the default for WR/TE

## Files

| File | Purpose |
|------|---------|
| `scripts/run_production_residual_experiment.py` | Experiment runner |
| `src/hybrid_projection.py` | Core residual model infrastructure (from 53-03) |
| `src/projection_engine.py` | Production heuristic source functions |
