---
phase: 21-pbp-derived-team-metrics
plan: 01
subsystem: analytics
tags: [pandas, numpy, pbp, team-metrics, penalties, turnovers, red-zone, sack-rate, explosive-plays]

requires:
  - phase: 20-infrastructure-and-data-expansion
    provides: 140-column PBP Bronze data with penalty, fumble, drive, ST columns
provides:
  - 7 new compute_* functions for PBP-derived team metrics in team_analytics.py
  - _filter_st_plays helper for special teams play filtering
  - 13 unit tests covering all new functions
affects: [21-02-plan, 21-03-plan]

tech-stack:
  added: []
  patterns:
    - "Raw-PBP functions (penalty, turnover) apply own season_type/week filters"
    - "Turnover luck uses expanding window with shift(1), not rolling"
    - "Red zone trips use drive nunique, not play count"

key-files:
  created: []
  modified:
    - src/team_analytics.py
    - tests/test_team_analytics.py

key-decisions:
  - "Penalty metrics use penalty==1 flag with penalty_team split (not play_type=='penalty')"
  - "Turnover luck expanding window produces _std columns inline (not via apply_team_rolling)"
  - "is_turnover_lucky uses 0.60/0.40 thresholds producing 1/0/-1 flag"

patterns-established:
  - "Phase 21 metric functions follow Section header pattern: PBP-Derived Metric Functions (Phase 21, Plan 01)"
  - "Raw-PBP functions receive unfiltered pbp_df; filtered-play functions receive valid_plays"

requirements-completed: [PBP-01, PBP-02, PBP-03, PBP-04, PBP-07, PBP-08, PBP-10]

duration: 6min
completed: 2026-03-16
---

# Phase 21 Plan 01: Core PBP-Derived Metric Functions Summary

**7 team-level PBP metric functions (penalties, turnovers, red zone trips, 3rd down, explosive plays, sack rates) plus ST filter helper with 13 passing unit tests**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-16T22:26:22Z
- **Completed:** 2026-03-16T22:32:29Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Implemented 7 core compute functions covering penalty metrics (off/def split), opponent-drawn penalties, turnover luck with expanding window, red zone trip volume, 3rd down conversion rates, explosive play rates, and sack rates
- Added _filter_st_plays helper using union of special_teams_play==1 and play_type in ST types
- 13 new unit tests with deterministic synthetic data and exact value assertions
- All 78 tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 7 core compute functions + ST filter helper** - `b84a38a` (feat)
2. **Task 2: Add unit tests for all 7 new compute functions** - `e526771` (test)

## Files Created/Modified
- `src/team_analytics.py` - Added 501 lines: 7 compute_* functions + _filter_st_plays helper in new "PBP-Derived Metric Functions (Phase 21, Plan 01)" section
- `tests/test_team_analytics.py` - Added 333 lines: 8 test classes with 13 test methods covering all new functions

## Decisions Made
- Used penalty==1 flag with penalty_team column split (not play_type=='penalty') per research findings
- Turnover luck computes expanding window STD columns inline rather than via apply_team_rolling (per user decision to use expanding, not rolling)
- is_turnover_lucky threshold: >0.60 = lucky (1), <0.40 = unlucky (-1), else neutral (0)
- Null fumble_recovery_1_team rows excluded from both recovered and lost counts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 7 functions ready for orchestrator integration in Plan 03
- _filter_st_plays helper ready for Plan 02 ST metric functions
- Test infrastructure extended with new test classes for easy pattern reuse

## Self-Check: PASSED

All files found, all commits verified.

---
*Phase: 21-pbp-derived-team-metrics*
*Completed: 2026-03-16*
