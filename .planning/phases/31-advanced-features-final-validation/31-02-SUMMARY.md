---
phase: 31-advanced-features-final-validation
plan: 02
subsystem: model-validation
tags: [holdout, ablation, ensemble, xgboost, ship-decision, v2.0]

requires:
  - phase: 31-advanced-features-final-validation
    provides: "momentum features and EWM windows in feature_engineering.py"
  - phase: 30-model-ensemble
    provides: "ensemble training pipeline, backtest CLI with --ensemble flag"
provides:
  - "--holdout flag on backtest_predictions.py for sealed three-way comparison"
  - "print_holdout_comparison() in prediction_backtester.py"
  - "v2.0 ship decision: P30 Ensemble confirmed as production model (53.0% ATS, +3.09 profit)"
affects: [milestone-completion, v2.0-shipping]

tech-stack:
  added: []
  patterns: ["Three-way holdout comparison (v1.4 vs P30 Ensemble vs P31 Full)", "Sealed holdout evaluation as final gate before ship"]

key-files:
  created: []
  modified:
    - scripts/backtest_predictions.py
    - src/prediction_backtester.py
    - tests/test_prediction_backtester.py

key-decisions:
  - "P30 Ensemble is v2.0 production model -- Phase 31 momentum features did not improve sealed holdout ATS"
  - "Phase 31 features documented as non-improving; ensemble_p30 artifacts are the shipped configuration"

patterns-established:
  - "Sealed holdout comparison via --holdout flag as final validation gate"

requirements-completed: [ADV-03]

duration: 4min
completed: 2026-03-27
---

# Phase 31 Plan 02: Final Validation and Ship Decision Summary

**Three-way sealed holdout comparison (v1.4 vs P30 Ensemble vs P31 Full) confirming P30 Ensemble as v2.0 production model with 53.0% ATS accuracy and +3.09 profit on 2024 holdout**

## Performance

- **Duration:** 4 min (continuation after checkpoint approval)
- **Started:** 2026-03-26T20:51:00Z
- **Completed:** 2026-03-27T00:11:22Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added --holdout flag to backtest_predictions.py for sealed three-way comparison (v1.4 XGBoost vs P30 Ensemble vs P31 Full)
- Implemented print_holdout_comparison() in prediction_backtester.py with formatted table output including ATS accuracy, O/U accuracy, MAE, profit, and ROI
- Ran feature selection re-run with expanded momentum/EWM features, retrained ensemble, executed ablation
- Sealed 2024 holdout confirmed P30 Ensemble as best configuration (53.0% ATS, +3.09 profit)
- Phase 31 momentum features documented as non-improving on sealed holdout -- no regression, no improvement
- Human-approved ship decision: P30 Ensemble is the v2.0 production model

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --holdout flag and three-way comparison to backtest CLI** - `a221485` (feat)
2. **Task 2: Re-run feature selection, retrain ensemble, execute ablation and holdout comparison** - model artifacts only (no code changes to commit)
3. **Task 3: Verify holdout results and approve ship decision** - checkpoint approved by user

## Files Created/Modified
- `scripts/backtest_predictions.py` - Added --holdout CLI flag and holdout comparison flow
- `src/prediction_backtester.py` - Added print_holdout_comparison() for three-way sealed evaluation
- `tests/test_prediction_backtester.py` - Added TestHoldoutComparison test class

## Decisions Made
- P30 Ensemble is the v2.0 production model based on sealed 2024 holdout results (53.0% ATS, +3.09 profit)
- Phase 31 momentum features (win_streak, ats_cover, ats_margin, EWM windows) did not clear the ship bar (>= +1% ATS or profit flip) on sealed holdout
- Features remain in codebase for future experimentation but are not selected in the v2.0 production feature set

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- v2.0 milestone is complete: all 19 requirements satisfied across Phases 28-31
- P30 Ensemble artifacts in models/ensemble/ are the production model
- Phase 31 features available in feature_engineering.py for future experimentation
- Ready for milestone transition and PROJECT.md evolution

---
*Phase: 31-advanced-features-final-validation*
*Completed: 2026-03-27*
