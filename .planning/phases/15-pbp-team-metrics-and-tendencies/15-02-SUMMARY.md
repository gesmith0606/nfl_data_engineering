---
phase: 15-pbp-team-metrics-and-tendencies
plan: 02
subsystem: analytics
tags: [epa, success-rate, cpoe, red-zone, pbp, team-metrics, silver-layer, tdd]

requires:
  - phase: 15-01
    provides: team_analytics.py skeleton with _filter_valid_plays and apply_team_rolling
provides:
  - Team EPA per play (offense/defense, pass/rush splits)
  - Team success rate (offense/defense)
  - Team CPOE (offense, NaN-excluded)
  - Red zone efficiency with drive-based TD rate
  - compute_pbp_metrics orchestrator with rolling windows
affects: [15-03, silver-player-transformation, projection-engine]

tech-stack:
  added: []
  patterns: [offense/defense split aggregation, drive-based denominator, NaN-aware CPOE]

key-files:
  created: [tests/test_team_analytics.py]
  modified: [src/team_analytics.py]

key-decisions:
  - "Red zone TD rate uses nunique(drive) denominator, not play count -- prevents inflating rate from multi-play drives"
  - "CPOE is offense-only metric -- no defensive CPOE column"
  - "Teams with zero red zone plays get NaN metrics via empty DataFrame return"

requirements-completed: [PBP-01, PBP-02, PBP-03, PBP-04]

duration: 3min
completed: 2026-03-14
---

# Phase 15 Plan 02: PBP Performance Metrics Summary

**EPA/success rate/CPOE/red zone metrics with offense-defense splits, drive-based RZ TD rate, and rolling windows via compute_pbp_metrics orchestrator**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T03:44:25Z
- **Completed:** 2026-03-14T03:47:20Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Implemented compute_team_epa with offense/defense EPA per play plus pass/rush splits
- Implemented compute_team_success_rate with offense/defense success rate
- Implemented compute_team_cpoe filtering NaN CPOE values (offense-only)
- Implemented compute_red_zone_metrics with drive-based TD rate denominator
- Created compute_pbp_metrics orchestrator wiring all 4 metric functions plus apply_team_rolling
- 22 unit tests covering EPA, success rate, CPOE, red zone, zero-trip edge case, rolling windows, cross-season isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement PBP metric compute functions with TDD** - `f5b8e09` (feat)
2. **Task 2: Add rolling window integration tests** - `40d9d1c` (test)

## Files Created/Modified

- `src/team_analytics.py` - Added compute_team_epa, compute_team_success_rate, compute_team_cpoe, compute_red_zone_metrics, compute_pbp_metrics (grew from 127 to 350+ lines)
- `tests/test_team_analytics.py` - New: 22 tests across 7 test classes (TestEPA, TestSuccessRate, TestCPOE, TestRedZone, TestRedZoneZeroTrips, TestPBPRolling, TestPBPCrossSeason)

## Decisions Made

- Red zone TD rate uses `nunique(drive)` denominator instead of play count to prevent inflating rate from multi-play drives
- CPOE is offense-only (no defensive CPOE column) matching NFL analytics convention
- Teams with zero red zone plays in a week get NaN metrics via empty DataFrame return

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- All PBP performance metrics ready for Plan 03 (tendencies: play calling, pace, personnel)
- compute_pbp_metrics orchestrator provides single entry point for Silver pipeline integration
- Rolling windows (_roll3, _roll6, _std) applied to all stat columns
- Full test suite: 211 tests passing

## Self-Check: PASSED

All artifacts verified: 2 files found (team_analytics.py: 348 lines, test_team_analytics.py: 458 lines), 2 commits found (f5b8e09, 40d9d1c), min_lines thresholds exceeded (150 for src, 100 for tests).

---
*Phase: 15-pbp-team-metrics-and-tendencies*
*Completed: 2026-03-14*
