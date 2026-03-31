---
phase: 40-baseline-models-ship-gate
plan: 01
subsystem: ml
tags: [xgboost, walk-forward-cv, shap, feature-selection, player-models, fantasy]

requires:
  - phase: 39-player-feature-vector-assembly
    provides: assemble_multiyear_player_features, get_player_feature_columns
provides:
  - Per-position per-stat XGBoost training with walk-forward CV (3 folds)
  - SHAP-based feature selection per stat-type group (yardage/td/volume/turnover)
  - Model serialization to models/player/{position}/{stat}.json with metadata sidecars
  - predict_player_stats for raw stat prediction enabling fantasy point conversion
affects: [40-02-PLAN, projection-engine-ml-upgrade]

tech-stack:
  added: []
  patterns: [per-stat-type hyperparameter profiles, player walk-forward CV with row-index OOF]

key-files:
  created:
    - src/player_model_training.py
    - tests/test_player_model_training.py
  modified: []

key-decisions:
  - "TD and turnover stats use shallower trees (max_depth=3) and higher min_child_weight (10) vs yardage/volume (max_depth=4, min_child_weight=5)"
  - "Walk-forward CV requires >= 2 training seasons per fold, skipping folds with insufficient data"
  - "OOF predictions keyed by row index (not game_id) since player data has no game_id equivalent"

patterns-established:
  - "STAT_TYPE_GROUPS mapping stat names to groups for shared feature selection and hyperparameters"
  - "player_walk_forward_cv adapts game-level walk_forward_cv_with_oof for player-level granularity"

requirements-completed: [MODL-01, MODL-02, PIPE-01]

duration: 33min
completed: 2026-03-30
---

# Phase 40 Plan 01: Player Model Training Summary

**Per-position per-stat XGBoost training with walk-forward CV, SHAP feature selection per stat-type group, and model serialization to JSON**

## Performance

- **Duration:** 33 min
- **Started:** 2026-03-30T23:55:09Z
- **Completed:** 2026-03-31T00:28:09Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Built player_model_training.py with 7 functions covering the full training pipeline
- Walk-forward CV produces 3 folds (2022/2023/2024) with holdout guard excluding 2025
- SHAP-based feature selection per 4 stat-type groups with correlation filtering (r > 0.90)
- Model serialization to JSON with metadata sidecars (MAE, features, training seasons)
- predict_player_stats enables downstream fantasy point conversion via scoring_calculator
- 8 tests passing, 616 total tests with 0 regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create test scaffold and stubs (RED)** - `8248704` (test)
2. **Task 2: Implement player model training (GREEN)** - `1cad2a6` (feat)

## Files Created/Modified

- `src/player_model_training.py` - Per-position per-stat model training, walk-forward CV, feature selection, serialization (452 lines)
- `tests/test_player_model_training.py` - 8 unit tests: model count, stat groups, CV folds, holdout guard, hyperparams, fantasy conversion, feature selection, serialization (250 lines)

## Decisions Made

- TD and turnover stats use shallower trees (max_depth=3, min_child_weight=10) to reduce overfitting on sparse count data
- Feature selection uses representative targets per group (rushing_yards for yardage, rushing_tds for td, receptions for volume, interceptions for turnover)
- Walk-forward CV skips folds with fewer than 2 training seasons to ensure meaningful model training

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed XGBoost early stopping in serialization test**
- **Found during:** Task 1 (RED phase)
- **Issue:** Test model.fit() with make_xgb_model required eval_set for early stopping, causing ValueError in test
- **Fix:** Used XGBRegressor directly without early stopping for the small serialization test
- **Files modified:** tests/test_player_model_training.py
- **Verification:** Test fails on NotImplementedError (correct RED behavior), not on XGBoost error

**2. [Rule 1 - Bug] Fixed fantasy scoring interception multiplier in test**
- **Found during:** Task 1 (RED phase)
- **Issue:** Test assumed interception = -1 point but SCORING_CONFIGS uses -2
- **Fix:** Updated expected calculation to use -2 multiplier matching half_ppr config
- **Files modified:** tests/test_player_model_training.py
- **Verification:** test_stat_to_fantasy_conversion passes with correct expected value (19.7)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both were test fixture corrections. No scope creep.

## Issues Encountered

None beyond the auto-fixed test issues above.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all functions fully implemented.

## Next Phase Readiness

- player_model_training.py is ready for integration with the training CLI (40-02)
- Feature columns from player_feature_engineering.py feed directly into run_player_feature_selection
- Model serialization format (JSON + metadata sidecar) supports the ship gate evaluation in 40-02

---
*Phase: 40-baseline-models-ship-gate*
*Completed: 2026-03-30*
