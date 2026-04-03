# Phase 53-03: Hybrid Residual Projection Experiment

## Objective

Test whether combining heuristic projections with ML corrections can beat standalone approaches.

## Experiment Setup

- **Data**: 51,758 player-weeks across 2016-2025 (PLAYER_DATA_SEASONS), holdout 2025 excluded
- **Evaluation window**: Seasons 2022-2024, weeks 3-18 (matching production backtest)
- **Scoring**: Half-PPR
- **Heuristic baseline**: `generate_heuristic_predictions()` from player_model_training.py (simplified: _weighted_baseline * usage_mult only, NO ceiling shrinkage, NO matchup factor)
- **ML baseline**: XGBoost per-stat walk-forward CV with SHAP-selected features

## Results

### Approach 1: Simple Blend

`blended = alpha * heuristic + (1 - alpha) * ML`, grid-search alpha in [0.1, 0.2, ..., 0.9]

| Position | Heuristic MAE | ML MAE | Best Alpha | Blend MAE |
|----------|--------------|--------|------------|-----------|
| QB       | 13.742       | 3.312  | 0.1        | 3.595     |
| RB       | 4.517        | 3.274  | 0.1        | 3.275     |
| WR       | 4.199        | 3.553  | 0.1        | 3.553     |
| TE       | 3.219        | 2.785  | 0.1        | 2.782     |

**Finding**: Optimal alpha is always 0.1 (nearly pure ML). The simplified heuristic provides zero complementary signal -- blending always degrades or at best matches ML alone.

### Approach 2: Residual Model

Train RidgeCV on `target = actual - heuristic` using ML features, walk-forward CV.

`final = heuristic + ridge.predict(features)`

| Position | Heuristic MAE | Residual MAE | Improvement |
|----------|--------------|-------------|-------------|
| QB       | 13.742       | 4.355       | +68.3%      |
| RB       | 4.517        | 3.729       | +17.4%      |
| WR       | 4.199        | 3.168       | +24.6%      |
| TE       | 3.219        | 2.576       | +20.0%      |

Ridge alphas: QB ~5-6, RB ~35-45, WR ~4-8, TE ~0.4-0.7 (TE most regularized = most confident corrections).

### Overall Comparison

| Approach        | QB MAE | RB MAE | WR MAE | TE MAE | Overall |
|----------------|--------|--------|--------|--------|---------|
| Heuristic*     | 13.742 | 4.517  | 4.199  | 3.219  | 5.277   |
| ML Standalone  | 3.312  | 3.274  | 3.553  | 2.785  | 3.292   |
| Blend (opt)    | 3.595  | 3.275  | 3.553  | 2.782  | 3.327   |
| Residual       | 4.355  | 3.729  | 3.168  | 2.576  | 3.339   |

*Note: This is the SIMPLIFIED heuristic (no ceiling shrinkage, no matchup), not the production heuristic (MAE 4.91).

## Key Findings

1. **Blend approach is not useful**: When ML dominates the heuristic, blending always converges to alpha=0.1 (pure ML). The heuristic doesn't provide complementary error patterns.

2. **Residual model wins for WR and TE**: Residual correction beats standalone ML for WR (3.17 vs 3.55, -11%) and TE (2.58 vs 2.79, -8%). For QB and RB, residual is worse than standalone ML.

3. **Why residual works for WR/TE**: The heuristic's rolling averages capture "player identity" (who they are) while ML captures "situation" (matchup, team context). For WR/TE, combining both signals via residual correction is better than ML alone because the heuristic's inertia smooths out ML noise on volatile positions.

4. **QB heuristic is fundamentally broken on full population**: The simplified heuristic assigns ~12 pts to backup QBs who don't play, inflating MAE to 13.7. ML correctly uses snap_pct to predict near-zero for backups.

5. **These numbers are NOT comparable to the production 4.91 MAE**: The production heuristic uses ceiling shrinkage + matchup factors + bye handling and operates on a filtered player population (only matched projections). These results use the simplified heuristic on ALL player-weeks.

## Decision

**No wire-up to production pipeline.** Neither hybrid approach beats standalone ML on the same evaluation setup, and the ML standalone already benefits from the full feature set. The residual WR/TE improvements are interesting but need validation against the production heuristic before committing.

## Next Steps

- To make the hybrid approach production-viable, the residual model should correct the PRODUCTION heuristic (with ceiling shrinkage + matchup), not the simplified one
- Consider training residual models only for WR/TE where the approach showed promise
- The blend approach is definitively ruled out -- heuristic provides no complementary signal

## Files

| File | Purpose |
|------|---------|
| `src/hybrid_projection.py` | Core module: blend evaluation + residual model training |
| `scripts/run_hybrid_experiment.py` | Experiment runner with full results reporting |
| `tests/test_hybrid_projection.py` | 20 tests (blend, residual, fantasy point conversion) |
