---
phase: 34-clv-tracking-ablation
plan: 01
subsystem: prediction
tags: [clv, backtesting, sports-betting, model-evaluation]

requires:
  - phase: 30-model-ensemble
    provides: prediction_backtester.py with ATS/O-U evaluation framework
provides:
  - evaluate_clv() function for per-game CLV computation
  - compute_clv_by_tier() for confidence-tier CLV breakdown
  - compute_clv_by_season() for seasonal CLV breakdown
  - print_clv_report() CLI output in backtest_predictions.py
affects: [34-02-ablation, betting-framework, model-monitoring]

tech-stack:
  added: []
  patterns: [CLV = predicted_margin - spread_line, confidence tier bucketing via pd.cut]

key-files:
  created: []
  modified:
    - src/prediction_backtester.py
    - tests/test_prediction_backtester.py
    - scripts/backtest_predictions.py

key-decisions:
  - "CLV computed as predicted_margin - spread_line (positive = model beat the close)"
  - "Confidence tiers use existing edge thresholds: high>=3.0, medium>=1.5, low<1.5"
  - "CLV reporting only for spread predictions (not totals) -- CLV is spread-specific"

patterns-established:
  - "CLV functions follow evaluate_ats/evaluate_ou copy-return pattern"
  - "Tier bucketing via pd.cut with observed=True groupby"

requirements-completed: [CLV-01, CLV-02, CLV-03]

duration: 3min
completed: 2026-03-28
---

# Phase 34 Plan 01: CLV Tracking Summary

**Three CLV functions (evaluate_clv, compute_clv_by_tier, compute_clv_by_season) with 9 TDD tests and CLI reporting in backtest_predictions.py**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-28T14:25:12Z
- **Completed:** 2026-03-28T14:28:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- evaluate_clv() computes per-game CLV as predicted_margin - spread_line
- compute_clv_by_tier() groups CLV by confidence tier (high/medium/low) with mean, median, pct_beating_close
- compute_clv_by_season() groups CLV by season with same metrics
- print_clv_report() formatted output wired into ensemble, comparison, and holdout backtest modes
- 9 new tests across 3 test classes (TestCLVEvaluation, TestCLVByTier, TestCLVBySeason)
- Full suite: 554 tests passing (up from 545)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add CLV functions with TDD tests** - `fef6bd1` (feat)
2. **Task 2: Wire CLV reporting into backtest CLI** - `6d1b821` (feat)

## Files Created/Modified
- `src/prediction_backtester.py` - Added evaluate_clv, compute_clv_by_tier, compute_clv_by_season
- `tests/test_prediction_backtester.py` - Added TestCLVEvaluation, TestCLVByTier, TestCLVBySeason (9 tests)
- `scripts/backtest_predictions.py` - Added print_clv_report, wired into ensemble/comparison/holdout modes

## Decisions Made
- CLV = predicted_margin - spread_line (positive means model beat the closing line)
- Reused existing confidence tier thresholds (3.0/1.5) from edge detection for consistency
- CLV reporting only applies to spread predictions, not totals (CLV is inherently spread-specific)
- print_clv_report calls evaluate_clv internally so callers don't need to pre-compute CLV

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- CLV functions ready for 34-02 ablation plan to use
- evaluate_clv/compute_clv_by_tier/compute_clv_by_season available as programmatic API for future JSON/CSV export
- backtest_predictions.py --ensemble now prints CLV section automatically

---
*Phase: 34-clv-tracking-ablation*
*Completed: 2026-03-28*
