---
phase: 37-holdout-reset-and-baseline
plan: 01
subsystem: infra
tags: [config, holdout, testing, model-training]

requires:
  - phase: 36-silver-feature-assembly
    provides: "2025 feature vector and Silver data for all seasons"
provides:
  - "HOLDOUT_SEASON = 2025 with derived season ranges"
  - "All test files import holdout config from src.config"
  - "Future holdout rotations are a one-line change"
affects: [37-02, ensemble-training, prediction-backtest]

tech-stack:
  added: []
  patterns: ["Derived season ranges from single HOLDOUT_SEASON constant"]

key-files:
  created: []
  modified:
    - src/config.py
    - tests/test_model_training.py
    - tests/test_ensemble_training.py
    - tests/test_prediction_backtester.py
    - tests/test_feature_selector.py

key-decisions:
  - "HOLDOUT_SEASON placed first in config block so PREDICTION_SEASONS, TRAINING_SEASONS, VALIDATION_SEASONS derive from it"
  - "VALIDATION_SEASONS now has 6 folds (2019-2024) instead of 5 -- test assertions updated to use len(VALIDATION_SEASONS)"

patterns-established:
  - "Holdout rotation: change HOLDOUT_SEASON in config.py, all downstream ranges update automatically"
  - "Tests reference config constants (HOLDOUT_SEASON, TRAINING_SEASONS) instead of hardcoded year values"

requirements-completed: [HOLD-01, HOLD-02]

duration: 5min
completed: 2026-03-29
---

# Phase 37 Plan 01: Holdout Rotation Summary

**Rotated holdout from 2024 to 2025 with all season ranges derived from HOLDOUT_SEASON; updated 4 test files to eliminate hardcoded holdout references**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-29T15:15:32Z
- **Completed:** 2026-03-29T15:20:05Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- HOLDOUT_SEASON = 2025 in config.py with PREDICTION_SEASONS, TRAINING_SEASONS, VALIDATION_SEASONS all computed from it
- All 4 test files updated to import and use config constants instead of hardcoded year values
- Zero holdout-related 2024 references remain in test files
- All 594 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Rotate holdout and derive season ranges in config.py** - `5f909fd` (feat)
2. **Task 2: Audit and update ALL holdout-referencing tests** - `aef4492` (feat)

## Files Created/Modified
- `src/config.py` - HOLDOUT_SEASON = 2025, derived PREDICTION/TRAINING/VALIDATION seasons
- `tests/test_model_training.py` - Import TRAINING_SEASONS, use VALIDATION_SEASONS for fold count
- `tests/test_ensemble_training.py` - Import TRAINING_SEASONS, filter for >= 2018
- `tests/test_prediction_backtester.py` - Import HOLDOUT_SEASON/TRAINING_SEASONS, replace 15 occurrences
- `tests/test_feature_selector.py` - Remove stale "(2024)" from docstring

## Decisions Made
- HOLDOUT_SEASON placed first in the config block so other constants can reference it
- VALIDATION_SEASONS expanded to 6 folds (2019-2024) as a natural consequence of the holdout shift; test assertions updated to use len(VALIDATION_SEASONS) rather than hardcoded 5

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed fold count assertion in test_model_training.py**
- **Found during:** Task 2 (test suite run)
- **Issue:** test_returns_walk_forward_result_with_5_folds asserted exactly 5 folds, but VALIDATION_SEASONS now has 6 entries (2019-2024)
- **Fix:** Changed assertion to `len(VALIDATION_SEASONS)` and renamed test to `test_returns_walk_forward_result_with_correct_folds`
- **Files modified:** tests/test_model_training.py
- **Verification:** All 594 tests pass
- **Committed in:** aef4492 (Task 2 commit)

**2. [Rule 1 - Bug] Updated last-fold test to use VALIDATION_SEASONS[-1]**
- **Found during:** Task 2 (test suite run)
- **Issue:** test_fold_5_trains_before_2023_validates_on_2023 hardcoded fold index 4 and season 2023
- **Fix:** Changed to test_last_fold_validates_on_last_validation_season using VALIDATION_SEASONS[-1]
- **Files modified:** tests/test_model_training.py
- **Verification:** All 594 tests pass
- **Committed in:** aef4492 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs caused by holdout rotation)
**Impact on plan:** Both fixes were direct consequences of the holdout rotation changing VALIDATION_SEASONS length. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Holdout is sealed at 2025, ready for Plan 02 to retrain ensemble and establish new baselines
- All season ranges are derived, so ensemble training will automatically use 2016-2024 for training

---
*Phase: 37-holdout-reset-and-baseline*
*Completed: 2026-03-29*
