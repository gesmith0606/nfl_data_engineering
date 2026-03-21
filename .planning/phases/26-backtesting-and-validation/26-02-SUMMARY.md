---
phase: 26-backtesting-and-validation
plan: 02
subsystem: prediction
tags: [backtesting, holdout, stability, leakage-detection, xgboost]

# Dependency graph
requires:
  - phase: 26-01
    provides: ATS evaluation (evaluate_ats), O/U evaluation (evaluate_ou), profit accounting (compute_profit)
provides:
  - "Sealed holdout evaluation function (evaluate_holdout) with leakage guard"
  - "Per-season stability analysis (compute_season_stability) with mean/std/min/max accuracy"
  - "Leakage detection at 58% ATS threshold"
  - "CLI holdout section and per-season breakdown table"
affects: [26-03, backtesting, prediction-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [sealed holdout evaluation, per-season stability analysis, leakage threshold detection]

key-files:
  created: []
  modified:
    - src/prediction_backtester.py
    - tests/test_prediction_backtester.py
    - scripts/backtest_predictions.py

key-decisions:
  - "LEAKAGE_THRESHOLD=0.58 per STATE.md blocker guidance"
  - "Holdout section only prints for spread target (not O/U) since ATS is the primary metric"
  - "Single-season std_accuracy returns 0.0 (not NaN) for clean reporting"

patterns-established:
  - "Holdout guard: ValueError if holdout_season in metadata['training_seasons']"
  - "Stability analysis: per-season groupby with profit + accuracy + leakage warning"

requirements-completed: [BACK-02, BACK-03]

# Metrics
duration: 3min
completed: 2026-03-21
---

# Phase 26 Plan 02: Holdout Validation and Season Stability Summary

**Sealed 2024 holdout evaluation with leakage guard plus per-season ATS stability analysis with 58% leakage threshold warning**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-21T21:29:40Z
- **Completed:** 2026-03-21T21:33:03Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Built evaluate_holdout() that guards against data leakage (ValueError if holdout season in training data) and filters to holdout-only rows
- Built compute_season_stability() returning per-season DataFrame (games, accuracy, profit, ROI) and stability summary (mean/std/min/max accuracy)
- Added LEAKAGE_THRESHOLD=0.58 with automatic warning when any season exceeds threshold
- Updated CLI with PER-SEASON BREAKDOWN table showing stability metrics and SEALED HOLDOUT section with training provenance note
- 12 new tests (5 holdout, 7 stability), 30 backtester tests total, 426 full suite passing

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1 RED: Failing tests for holdout and stability** - `b809bdf` (test)
2. **Task 1 GREEN: Implement holdout validation and season stability** - `1c21e80` (feat)

## Files Created/Modified
- `src/prediction_backtester.py` - Added evaluate_holdout(), compute_season_stability(), LEAKAGE_THRESHOLD
- `tests/test_prediction_backtester.py` - Added TestHoldoutValidation (5 tests), TestStabilityAnalysis (7 tests)
- `scripts/backtest_predictions.py` - Added PER-SEASON BREAKDOWN table, SEALED HOLDOUT section, leakage warnings

## Decisions Made
- LEAKAGE_THRESHOLD set to 0.58 per STATE.md blocker guidance (realistic ATS accuracy is 52-55%)
- Holdout section only prints for spread target since ATS accuracy is the primary market-beating metric
- Single-season std_accuracy returns 0.0 rather than NaN for clean output handling

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Holdout evaluation and stability analysis ready for use in full backtesting workflow
- Phase 26 backtesting-and-validation complete (2/2 plans done)
- Ready for Phase 27 (weekly prediction pipeline with edge detection)

---
*Phase: 26-backtesting-and-validation*
*Completed: 2026-03-21*
