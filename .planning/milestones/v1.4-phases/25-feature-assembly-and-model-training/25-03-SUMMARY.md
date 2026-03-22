---
phase: 25-feature-assembly-and-model-training
plan: 03
subsystem: ml-pipeline
tags: [xgboost, optuna, training-cli, feature-importance, hyperparameter-tuning]

# Dependency graph
requires:
  - phase: 25-feature-assembly-and-model-training-01
    provides: "assemble_multiyear_features(), get_feature_columns() for data loading"
  - phase: 25-feature-assembly-and-model-training-02
    provides: "walk_forward_cv(), train_final_model() for CV and model persistence"
provides:
  - "scripts/train_prediction_model.py CLI for training spread and total models"
  - "Optuna hyperparameter tuning with 50 trials default and TPE sampler"
  - "Feature importance report (top 20 console + full CSV)"
  - "--no-tune escape hatch for quick training with conservative defaults"
affects: [game-prediction-pipeline, backtesting, weekly-predictions]

# Tech tracking
tech-stack:
  added: []
  patterns: [optuna-objective-cv-wrapper, feature-importance-csv-export, cli-model-dir-override]

key-files:
  created:
    - scripts/train_prediction_model.py
    - tests/test_train_cli.py
    - scripts/__init__.py
  modified: []

key-decisions:
  - "Added --model-dir flag for test isolation (tmp_path in pytest)"
  - "main() accepts argv parameter for direct invocation from tests without subprocess"
  - "Optuna import deferred to _run_optuna_tuning() to avoid import cost in --no-tune path"

patterns-established:
  - "Training CLI: main(argv) pattern for testability without subprocess"
  - "Feature importance: gain-based from model.feature_importances_ sorted descending to CSV"

requirements-completed: [MODL-04, FEAT-03]

# Metrics
duration: 3min
completed: 2026-03-21
---

# Phase 25 Plan 03: Training CLI Summary

**Training CLI with Optuna TPE tuning (50 trials), --no-tune conservative defaults, and gain-based feature importance report (top 20 console + CSV)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-21T02:11:48Z
- **Completed:** 2026-03-21T02:15:25Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- Training CLI matches roadmap success criteria: `python scripts/train_prediction_model.py --target spread` trains and saves model
- Optuna tuning wired with 50 trials default, TPE sampler, search ranges from research (max_depth 2-6, lr 0.01-0.15)
- Feature importance report prints top 20 features by gain to console and saves full importance to CSV
- --no-tune path tested end-to-end with model.json, metadata.json, and feature_importance.csv verified
- 396 total tests passing (14 new + 382 existing)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for CLI** - `d10f2c5` (test)
2. **Task 1 (GREEN): Training CLI implementation** - `cbba24b` (feat)

## Files Created/Modified
- `scripts/train_prediction_model.py` - Training CLI with argparse, Optuna tuning, feature importance report
- `tests/test_train_cli.py` - 14 tests: imports, argparse, integration (no-tune spread/total + importance CSV)
- `scripts/__init__.py` - Package init for test importability

## Decisions Made
- Added `--model-dir` flag for test isolation via pytest tmp_path (avoids polluting models/ during tests)
- Used `main(argv)` pattern instead of subprocess for integration tests (faster, better error messages)
- Deferred Optuna import inside `_run_optuna_tuning()` to avoid unnecessary import cost on --no-tune path

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added scripts/__init__.py for package importability**
- **Found during:** Task 1 (RED phase)
- **Issue:** `from scripts.train_prediction_model import TARGET_MAP` requires scripts/ to be a Python package
- **Fix:** Created empty `scripts/__init__.py`
- **Files modified:** scripts/__init__.py
- **Verification:** Import succeeds in test suite
- **Committed in:** d10f2c5 (RED commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for test importability. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Training CLI complete -- all Phase 25 plans delivered
- Ready for Phase 26 (backtesting/holdout evaluation) or Phase 27 (weekly prediction pipeline)
- 396 total tests passing

---
*Phase: 25-feature-assembly-and-model-training*
*Completed: 2026-03-21*
