---
phase: 41-accuracy-improvements
plan: 01
subsystem: ml-features
tags: [feature-engineering, efficiency-ratios, td-regression, momentum, player-prediction]

requires:
  - phase: 39-player-feature-assembly
    provides: "assemble_player_features with 9 Silver source joins and get_player_feature_columns"
provides:
  - "12 efficiency ratio features (yards_per_carry/target/reception, catch_rate, rush/rec_td_rate x roll3/roll6)"
  - "2 TD regression features (expected_td_pos_avg, expected_td_player)"
  - "3 momentum delta features (snap_pct_delta, target_share_delta, carry_share_delta)"
  - "POSITION_AVG_RZ_TD_RATE config constants"
affects: [41-02, player-model-training, feature-selection]

tech-stack:
  added: []
  patterns: ["safe division via np.where for ratio features", "shift(1) rolling computation for ad-hoc features"]

key-files:
  created: []
  modified:
    - src/player_feature_engineering.py
    - src/config.py
    - tests/test_player_feature_engineering.py

key-decisions:
  - "Safe division with np.where (NaN for zero denominator) rather than fillna(0) to preserve signal quality"
  - "POSITION_AVG_RZ_TD_RATE uses league-average red zone TD conversion rates per position"

patterns-established:
  - "Derived feature functions called at end of assemble_player_features before return"
  - "Column existence checks before each computation to handle missing Silver sources gracefully"

requirements-completed: [ACCY-01, ACCY-02, ACCY-03]

duration: 3min
completed: 2026-03-31
---

# Phase 41 Plan 01: Derived Feature Functions Summary

**17 derived features (efficiency ratios, TD regression, momentum deltas) added to player feature vector with safe division and auto-discovery**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-31T02:32:30Z
- **Completed:** 2026-03-31T02:35:25Z
- **Tasks:** 1 (TDD)
- **Files modified:** 3

## Accomplishments
- 12 efficiency ratio columns decompose opportunity from efficiency signal across roll3/roll6 windows
- 2 TD regression columns replace noisy raw TD rolling averages with expected TD rates
- 3 momentum delta columns detect role changes via roll3-minus-roll6
- All features auto-discovered by get_player_feature_columns (numeric, not in exclusion sets)
- 632 tests passing (10 new + 622 existing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add derived feature functions and config constants**
   - `0e4f391` (test: RED - failing tests for all three feature groups)
   - `a77b50f` (feat: GREEN - implementation of all three functions + config + wiring)

## Files Created/Modified
- `src/player_feature_engineering.py` - Added compute_efficiency_features, compute_td_regression_features, compute_momentum_features; wired into assemble_player_features
- `src/config.py` - Added POSITION_AVG_RZ_TD_RATE constants (RB: 0.08, WR: 0.12, TE: 0.14)
- `tests/test_player_feature_engineering.py` - 10 new unit tests covering all three feature groups

## Decisions Made
- Safe division with np.where (NaN for zero denominator) preserves signal quality for downstream models
- POSITION_AVG_RZ_TD_RATE uses league-average red zone TD conversion rates
- Momentum deltas skip silently when source columns are missing (graceful degradation)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 17 derived features ready for model training in 41-02
- Features auto-discovered by get_player_feature_columns -- no manual feature list updates needed
- Full test suite green (632 tests)

---
## Self-Check: PASSED

All files exist, all commits verified, all content checks passed.

---
*Phase: 41-accuracy-improvements*
*Completed: 2026-03-31*
