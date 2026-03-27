---
phase: 31-advanced-features-final-validation
plan: 01
subsystem: feature-engineering
tags: [momentum, ewm, rolling-windows, xgboost, prediction]

requires:
  - phase: 28-infrastructure-player-features
    provides: "feature_engineering.py with leakage guard and differential pipeline"
provides:
  - "_compute_momentum_features() producing win_streak, ats_cover_sum3, ats_margin_avg3"
  - "EWM windows (halflife=3) on EPA/success/CPOE/red zone team metrics"
  - "_is_rolling() recognizes ewm3 pattern for leakage guard"
affects: [31-02, model-training, feature-selection]

tech-stack:
  added: []
  patterns: ["EWM via apply_team_rolling ewm_cols parameter", "Momentum from Bronze schedules with signed streak counter"]

key-files:
  created: []
  modified:
    - src/feature_engineering.py
    - src/team_analytics.py
    - src/config.py
    - tests/test_feature_engineering.py
    - tests/test_team_analytics.py

key-decisions:
  - "Momentum features merged into team_df before home/away split (flows through differential pipeline)"
  - "EWM restricted to PBP metrics caller only (not SOS/tendencies/situational) to avoid feature explosion"
  - "Away team ATS margin uses -result + spread_line for correct sign convention"

patterns-established:
  - "EWM param pattern: ewm_cols/ewm_halflife optional params on apply_team_rolling"
  - "Momentum via Bronze schedules: reshape to per-team rows, compute streak/cover/margin, shift(1)"

requirements-completed: [ADV-01, ADV-02]

duration: 5min
completed: 2026-03-26
---

# Phase 31 Plan 01: Momentum Features and EWM Windows Summary

**Momentum streak/ATS signals from Bronze schedules plus EWM adaptive windows on team EPA/success/CPOE metrics, all with shift(1) leakage prevention**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-26T20:45:32Z
- **Completed:** 2026-03-26T20:50:22Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added _compute_momentum_features() producing win_streak (signed consecutive counter), ats_cover_sum3 (rolling ATS cover count), and ats_margin_avg3 (rolling ATS margin mean)
- Extended apply_team_rolling() with optional ewm_cols/ewm_halflife parameters for exponentially weighted moving averages
- Updated leakage guard: _PRE_GAME_CUMULATIVE includes momentum columns, _is_rolling() recognizes ewm3 pattern
- 13 new tests (8 momentum + 5 EWM), full suite at 495 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add momentum features to feature_engineering.py with tests** - `32748fa` (feat)
2. **Task 2: Add EWM windows to team_analytics.py with tests** - `e2b5ff1` (feat)

## Files Created/Modified
- `src/feature_engineering.py` - Added _compute_momentum_features(), integrated into assemble_game_features(), updated _PRE_GAME_CUMULATIVE and _is_rolling()
- `src/team_analytics.py` - Extended apply_team_rolling() with ewm_cols/ewm_halflife, imported EWM_TARGET_COLS for compute_pbp_metrics
- `src/config.py` - Added EWM_TARGET_COLS constant (7 core efficiency metrics)
- `tests/test_feature_engineering.py` - Added TestMomentumFeatures (7 tests) and TestEWMFeatures (1 test)
- `tests/test_team_analytics.py` - Added TestEWMRolling (5 tests)

## Decisions Made
- Momentum features merged into team_df before home/away split so they flow through the existing differential pipeline automatically
- EWM only applied to compute_pbp_metrics caller (not SOS, tendencies, situational) to keep feature count bounded per D-09
- Away team ATS margin computed as -result + spread_line (negation of home perspective)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Momentum and EWM features are available to feature selection and model training
- Plan 31-02 can proceed with final validation using the expanded feature set

## Self-Check: PASSED

All files exist, both commit hashes verified, acceptance criteria grep checks confirmed.

---
*Phase: 31-advanced-features-final-validation*
*Completed: 2026-03-26*
