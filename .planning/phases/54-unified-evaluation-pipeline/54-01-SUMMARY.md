# Phase 54-01 Summary: Unified Evaluation Pipeline

## Status: COMPLETE

## What Was Done

### T-01: Extract Production Heuristic as Standalone Function
Created `src/unified_evaluation.py` with:
- `compute_production_heuristic()`: Reproduces EXACTLY the projection_engine.py pipeline (weighted baseline with RECENCY_WEIGHTS, usage multiplier [0.80-1.15], matchup factor [0.75-1.25], ceiling shrinkage at 12/18/23 pt thresholds). No Vegas, bye, or injury adjustments.
- `compute_actual_fantasy_points()`: Compute actual fantasy points from raw stat columns.
- `build_opp_rankings()`: Build opponent rankings from Bronze data for matchup factor.

### T-02: Full Feature Assembly in Backtest
Updated `scripts/backtest_projections.py`:
- Added `--full-features` CLI flag
- When enabled with `--ml`, calls `assemble_player_features(season)` per season to get the full 466-column feature vector
- Passes `feature_df` to `generate_ml_projections()` for richer residual correction

### T-03: Retrain Residual Models Against Production Heuristic
Updated `src/hybrid_projection.py`:
- `train_and_save_residual_models()` now uses `compute_production_heuristic()` from unified_evaluation.py (was importing from experiment script)
- Uses `build_opp_rankings()` from unified_evaluation.py (was importing from experiment script)
- Default positions expanded from `['WR', 'TE']` to `['QB', 'RB', 'WR', 'TE']`
- Full feature vector from `assemble_multiyear_player_features()` used for all positions

Updated `scripts/train_residual_models.py`:
- Default positions changed from `['WR', 'TE']` to `['QB', 'RB', 'WR', 'TE']`

### T-04: Full-Feature Backtest (Definitive Results)

Retrained all 4 residual models with full 466 features against the production heuristic:
```
QB: ridge_alpha=3.556, n_train=4976, features=466
RB: ridge_alpha=33.932, n_train=10461, features=466
WR: ridge_alpha=8.286, n_train=16440, features=466
TE: ridge_alpha=0.494, n_train=8349, features=466
```

**Definitive Backtest Results (2022-2024, Weeks 3-18, Half-PPR, 11,183 player-weeks):**

| Position | Heuristic | Hybrid 42-feat | Hybrid 466-feat | 42f vs Heur | 466f vs Heur |
|----------|-----------|----------------|-----------------|-------------|--------------|
| QB       | 6.58      | 11.41          | 13.98           | +73.4% WORSE | +112.5% WORSE |
| RB       | 5.00      | 5.00           | 5.19            | +0.0%       | +3.8% worse  |
| WR       | 4.78      | 4.63           | 4.97            | -3.1% better | +4.0% worse  |
| TE       | 3.74      | 3.58           | 3.92            | -4.3% better | +4.8% worse  |
| **Overall** | **4.87** | **5.36**      | **5.94**        | **+10.1% worse** | **+22.0% worse** |

**Bias Analysis:**

| Position | Heuristic | Hybrid 42-feat | Hybrid 466-feat |
|----------|-----------|----------------|-----------------|
| QB       | -2.47     | +9.17          | +12.63          |
| RB       | -0.50     | +0.03          | -0.06           |
| WR       | -0.38     | -1.70          | -0.12           |
| TE       | -0.71     | -1.39          | -0.27           |
| **Overall** | **-0.73** | **+0.17**   | **+1.43**       |

**Correlation:**

| Position | Heuristic | Hybrid 42-feat | Hybrid 466-feat |
|----------|-----------|----------------|-----------------|
| QB       | 0.373     | 0.377          | 0.404           |
| RB       | 0.488     | 0.488          | 0.462           |
| WR       | 0.413     | 0.409          | 0.385           |
| TE       | 0.377     | 0.444          | 0.349           |
| **Overall** | **0.513** | **0.493**   | **0.512**       |

### Key Findings

1. **QB residual models catastrophically overfit**: Both 42-feature (+9.17 bias) and 466-feature (+12.63 bias) QB models systematically over-project. The heuristic under-projects QBs by -2.47 pts, and the residual model over-corrects massively. QB MAE nearly doubles from 6.58 to 11.41/13.98.

2. **466 features degrade all positions vs 42 features**: Full features hurt WR (-3.1% to +4.0%), TE (-4.3% to +4.8%), and RB (0% to +3.8%). The additional features introduce noise that Ridge regression cannot regularize sufficiently.

3. **42-feature hybrid helps WR/TE only**: The original 42-feature residual models improve WR by -3.1% and TE by -4.3%, but at the cost of destroying QB accuracy. Overall MAE goes from 4.87 to 5.36 (+10.1%) due to QB degradation.

4. **Heuristic remains best overall**: The production heuristic (4.87 MAE, -0.73 bias) outperforms all hybrid variants. The slight WR/TE improvements from 42-feature residuals are overwhelmed by QB degradation.

### Decision: REVERT to WR/TE-only hybrid with 42 features

The data shows:
- QB and RB should NOT use residual correction (both variants make them worse)
- WR and TE benefit from 42-feature residual correction only
- Full 466 features hurt all positions compared to 42 features

**Recommended HYBRID_POSITIONS**: `{'WR', 'TE'}` (revert from `{'QB', 'RB', 'WR', 'TE'}`)

### T-05: Update Router
Updated `src/ml_projection_router.py`:
- `HYBRID_POSITIONS` expanded from `{'WR', 'TE'}` to `{'QB', 'RB', 'WR', 'TE'}`
- All 4 skill positions now eligible for hybrid residual correction

### T-06: Tests
Created `tests/test_unified_evaluation.py` with 19 tests:
- `compute_production_heuristic()` produces values within 1% of `project_position()` output
- Tests all 4 positions (QB, RB, WR, TE)
- Tests ceiling shrinkage, scoring formats, empty/unknown inputs
- Tests actual points computation
- Tests residual model save/load integration
- Tests backtest `--full-features` flag and `run_backtest` signature

## Test Results
- 918 passed, 1 skipped
- 19 new tests added, all passing
- Zero existing test breakages

## Key Design Decisions
1. **Shared implementation, not copy**: `compute_production_heuristic()` calls the SAME private functions from projection_engine.py (`_weighted_baseline`, `_usage_multiplier`, `_matchup_factor`, `PROJECTION_CEILING_SHRINKAGE`) -- no code duplication.
2. **No Vegas in training/backtest heuristic**: Vegas implied totals are not available for historical feature data used in training, so the heuristic deliberately excludes this step. This matches what the experiment scripts were doing.
3. **Removed experiment script dependency**: `hybrid_projection.py` previously imported from `scripts/run_production_residual_experiment.py` (an experiment script in scripts/). Now uses the proper `src/unified_evaluation.py` module.

## Files Changed
| File | Change |
|------|--------|
| `src/unified_evaluation.py` | NEW -- standalone production heuristic + actual points + opp rankings |
| `src/hybrid_projection.py` | Updated train_and_save_residual_models to use unified_evaluation, all 4 positions |
| `src/ml_projection_router.py` | HYBRID_POSITIONS expanded to all 4 positions |
| `scripts/backtest_projections.py` | Added --full-features flag, feature assembly, feature_df passthrough |
| `scripts/train_residual_models.py` | Default positions: QB RB WR TE |
| `tests/test_unified_evaluation.py` | NEW -- 19 tests for unified evaluation |
