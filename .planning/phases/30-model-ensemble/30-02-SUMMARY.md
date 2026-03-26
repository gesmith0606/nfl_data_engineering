---
phase: 30-model-ensemble
plan: 02
subsystem: ml
tags: [ensemble, cli, backtest, optuna, comparison, xgboost, lightgbm, catboost]

# Dependency graph
requires:
  - phase: 30-model-ensemble
    plan: 01
    provides: "train_ensemble, load_ensemble, predict_ensemble, model factories"
provides:
  - "Ensemble training CLI with optional Optuna tuning (scripts/train_ensemble.py)"
  - "Side-by-side backtest comparison via --ensemble flag (scripts/backtest_predictions.py)"
  - "Ensemble prediction dispatch via --ensemble flag (scripts/generate_predictions.py)"
affects: [backtest-workflow, prediction-pipeline, phase-31]

# Tech tracking
tech-stack:
  added: []
  patterns: [cli-ensemble-dispatch, side-by-side-comparison-table]

key-files:
  created:
    - scripts/train_ensemble.py
  modified:
    - scripts/backtest_predictions.py
    - scripts/generate_predictions.py

key-decisions:
  - "Ensemble features loaded from metadata.json not config.py (prevents feature mismatch per Pitfall 5)"
  - "Side-by-side comparison table printed when --ensemble used in backtest (not separate commands)"
  - "Optuna tuning uses last target's best params (spread tuned then total, total params kept)"

patterns-established:
  - "CLI ensemble dispatch: --ensemble flag branches loading/prediction while sharing output formatting"
  - "Comparison backtest: runs both models on same data, prints delta table"

requirements-completed: [ENS-05]

# Metrics
duration: 3min
completed: 2026-03-26
---

# Phase 30 Plan 02: Ensemble CLI Summary

**Ensemble training CLI with Optuna tuning, side-by-side ATS/ROI backtest comparison, and --ensemble prediction dispatch for XGB+LGB+CB+Ridge stacking**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T00:54:39Z
- **Completed:** 2026-03-26T00:57:39Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Ensemble training CLI (train_ensemble.py) with --tune flag for Optuna hyperparameter search across all 3 model types
- Backtest CLI updated with --ensemble flag that runs side-by-side comparison table showing XGBoost vs Ensemble accuracy/profit/ROI deltas
- Prediction CLI updated with --ensemble flag that loads ensemble models and generates v2.0-ensemble predictions with edge detection
- All 482 existing tests still pass (no regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create train_ensemble.py CLI** - `f4bf0ba` (feat)
2. **Task 2: Wire --ensemble flag into backtest and prediction CLIs** - `d3789b4` (feat)

## Files Created/Modified
- `scripts/train_ensemble.py` - Ensemble training CLI with --tune, --trials, --ensemble-dir flags and Optuna integration
- `scripts/backtest_predictions.py` - Added --ensemble flag, run_ensemble_backtest, run_comparison_backtest with side-by-side table
- `scripts/generate_predictions.py` - Added --ensemble flag with inline ensemble prediction and v2.0-ensemble model version

## Decisions Made
- Ensemble features loaded from metadata["selected_features"] rather than config.py SELECTED_FEATURES to prevent feature mismatch between training and inference
- Side-by-side comparison is the default behavior when --ensemble is passed to backtest (shows both models, not just ensemble)
- Optuna tuning in train_ensemble.py tunes all 6 studies (3 models x 2 targets) sequentially, keeping the last tuned params

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functions are fully implemented with real logic.

## Next Phase Readiness
- Full ensemble pipeline complete: train -> backtest -> predict
- Ready for Phase 31 (advanced features) or production use
- 482 tests passing

---
*Phase: 30-model-ensemble*
*Completed: 2026-03-26*
