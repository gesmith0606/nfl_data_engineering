---
phase: 26-backtesting-and-validation
plan: 01
subsystem: prediction
tags: [backtesting, ats, over-under, vig, xgboost, sports-betting]

# Dependency graph
requires:
  - phase: 25-feature-assembly-and-model-training
    provides: trained XGBoost spread/total models with load_model(), feature_engineering assembly
provides:
  - "ATS evaluation function (evaluate_ats) with nflverse spread convention"
  - "O/U evaluation function (evaluate_ou)"
  - "Vig-adjusted profit accounting at -110 odds (compute_profit)"
  - "CLI for running prediction backtests (scripts/backtest_predictions.py)"
affects: [26-02, backtesting, prediction-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [vig-adjusted profit accounting, ATS/OU backtest evaluation]

key-files:
  created:
    - src/prediction_backtester.py
    - scripts/backtest_predictions.py
    - tests/test_prediction_backtester.py
  modified: []

key-decisions:
  - "Used bool() wrapper for numpy bool identity checks in tests"
  - "Pushes excluded from W/L record and profit calculation (money returned)"

patterns-established:
  - "ATS evaluation: home covers when actual_margin > spread_line (nflverse positive-home-favored convention)"
  - "Vig constants: VIG_WIN = 100/110, VIG_LOSS = -1.0, BREAK_EVEN_PCT = 52.38%"

requirements-completed: [BACK-01]

# Metrics
duration: 4min
completed: 2026-03-21
---

# Phase 26 Plan 01: Prediction Backtester Summary

**ATS and O/U evaluation library with vig-adjusted profit accounting at -110 odds, plus CLI for running backtests against historical Vegas closing lines**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-21T21:23:26Z
- **Completed:** 2026-03-21T21:27:36Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Built evaluate_ats() with nflverse convention (positive spread = home favored, home covers when actual_margin > spread_line)
- Built evaluate_ou() for over/under classification with push handling
- Built compute_profit() with -110 vig accounting (break-even at 52.38%, pushes excluded)
- CLI loads model, assembles features, predicts, evaluates, and prints formatted W-L-P report with per-season breakdown
- 18 new tests covering ATS, O/U, profit math, pushes, break-even, edge cases
- Full suite: 414 tests passing (18 new + 396 existing)

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1 RED: Failing tests for prediction backtester** - `b34c91d` (test)
2. **Task 1 GREEN: Implement backtester library and CLI** - `7e89b6d` (feat)

## Files Created/Modified
- `src/prediction_backtester.py` - ATS evaluation, O/U evaluation, vig-adjusted profit accounting
- `tests/test_prediction_backtester.py` - 18 unit tests with synthetic DataFrames
- `scripts/backtest_predictions.py` - CLI with --target spread/total/both, per-season breakdown

## Decisions Made
- Used `bool()` wrapper for numpy bool identity checks in pytest assertions (numpy booleans fail `is True`)
- Pushes return stake (0 profit) and are excluded from W-L record and ROI calculation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed numpy bool identity comparison in tests**
- **Found during:** Task 1 GREEN phase
- **Issue:** `assert result["col"].iloc[0] is True` fails because pandas returns numpy.bool_ which is not Python's True
- **Fix:** Wrapped with `bool()`: `assert bool(result["col"].iloc[0]) is True`
- **Files modified:** tests/test_prediction_backtester.py
- **Verification:** All 18 tests pass
- **Committed in:** 7e89b6d (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test assertion fix for numpy/Python bool mismatch. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backtester library ready for Plan 26-02 (holdout evaluation, per-season stability analysis)
- Models must be trained before CLI can produce results (depends on Phase 25 trained models on disk)

---
*Phase: 26-backtesting-and-validation*
*Completed: 2026-03-21*
