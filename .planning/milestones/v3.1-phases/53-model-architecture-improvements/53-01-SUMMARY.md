# Phase 53-01: Ridge/ElasticNet as Primary Model for RB/WR/TE

## Objective

Test whether Ridge regression (lower capacity, less overfitting) can beat the
heuristic baseline on the dual agreement ship gate for RB/WR/TE fantasy
projections, where XGBoost was SKIP due to OOF overfitting.

## What Was Built

### 1. Interaction Features (`src/player_feature_engineering.py`)
- Added `compute_interaction_features()`: 7 key rolling stats x 3 context
  columns = up to 21 multiplicative interactions
- Stats: passing_yards, rushing_yards, rushing_tds, receptions, receiving_yards,
  receiving_tds, targets (all roll3 variants)
- Context: implied_team_total (Vegas), opp_avg_pts_allowed (matchup), snap_pct_roll3 (usage)
- Wired into `assemble_player_features()` step 10

### 2. Ridge/ElasticNet Model Factories (`src/player_model_training.py`)
- `create_ridge_pipeline()`: SimpleImputer(median) + RidgeCV(50 alphas, 10^-3 to 10^3)
- `create_elasticnet_pipeline()`: SimpleImputer(median) + ElasticNetCV(5 l1_ratios, 20 alphas)
- `_linear_fit_kwargs()`: returns empty dict (no eval_set for linear models)
- `train_position_models_linear()`: full per-position training loop for linear models
  - Skips SHAP feature selection (L2/L1 handles multicollinearity)
  - Uses all non-zero-variance features
  - Saves models via joblib (sklearn Pipeline, not XGBoost JSON)
- `predict_player_stats_linear()`: prediction using feature list from model dict

### 3. CLI Flag (`scripts/train_player_models.py`)
- `--model-type {xgb, ridge, elasticnet}` flag (default: xgb)
- Linear models skip SHAP feature selection step
- Stage 1 header shows model type

### 4. Tests (12 new tests, 870 total passing)
- `TestInteractionFeatures`: 6 tests (creation, values, missing cols, NaN, copy safety)
- `TestPlayerModelTraining`: 6 tests (Ridge pipeline, ElasticNet pipeline,
  linear fit kwargs, Ridge walk-forward CV, linear training, linear prediction)

## Ship Gate Results

```
POSITION | HEURISTIC MAE | XGB OOF MAE | RIDGE OOF MAE | DECISION
QB       | 13.99         | ~8.5        | 8.42          | SHIP (Ridge matches XGB)
RB       | 4.63          | 5.22        | 5.67          | SKIP (Ridge worse than XGB)
WR       | 4.30          | 4.93        | 4.76          | SKIP (Ridge better than XGB, still > heuristic)
TE       | 3.28          | 3.66        | 3.68          | SKIP (Ridge matches XGB)
```

## Key Findings

1. **Ridge cannot beat the heuristic for RB/WR/TE.** The heuristic (weighted
   rolling averages x usage multiplier) IS effectively an optimally tuned
   linear model with strong domain priors. Ridge with 300+ features and L2
   regularization cannot find enough additional signal to overcome the
   noise from extra features.

2. **Ridge slightly outperforms XGB for WR** (4.76 vs 4.93) but still trails
   the heuristic (4.30). This confirms the overfitting hypothesis -- Ridge
   overfits less than XGB, but neither captures enough nonlinear signal
   to justify their complexity over the handcrafted heuristic.

3. **The heuristic IS the optimal model for RB/WR/TE** with current data
   (2020-2025, ~5-10k rows per position). The signal-to-noise ratio at the
   player-week level is too low for ML models to outperform domain-tuned
   weighted averages.

4. **QB is the exception** -- Ridge ships at 8.42 MAE vs 13.99 heuristic
   (40% improvement). QB has higher variance, more predictable patterns,
   and the heuristic's generic approach underperforms a model that can
   weight QB-specific features.

## Recommendation

- **Keep heuristic as primary for RB/WR/TE** -- confirmed by both XGB and Ridge
- **Use Ridge as QB fallback** (simpler than XGB, same performance, faster training)
- **Expanding to 2016-2025 data** (Track 2) may change this -- with 3x more
  training data, Ridge/XGB may have enough signal to beat the heuristic
- **Alternative approaches worth testing**: gradient-boosted heuristic (use ML
  to learn residuals on top of the heuristic baseline), or ensemble the heuristic
  as a meta-feature

## Files Changed

| File | Change |
|------|--------|
| `src/player_feature_engineering.py` | Added `compute_interaction_features()`, wired into assembly |
| `src/player_model_training.py` | Added Ridge/ElasticNet factories, `train_position_models_linear()`, `predict_player_stats_linear()` |
| `scripts/train_player_models.py` | Added `--model-type` CLI flag, linear model training branch |
| `tests/test_player_model_training.py` | 6 new tests for Ridge/ElasticNet |
| `tests/test_player_feature_engineering.py` | 6 new tests for interaction features |
