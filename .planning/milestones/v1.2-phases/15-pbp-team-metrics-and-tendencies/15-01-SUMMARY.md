---
phase: 15-pbp-team-metrics-and-tendencies
plan: 01
subsystem: analytics
tags: [rolling-windows, team-metrics, pbp, silver-layer, pandas]

requires:
  - phase: none
    provides: existing player_analytics.py and config.py
provides:
  - Fixed rolling window groupby preventing cross-season contamination
  - SILVER_TEAM_S3_KEYS config registration (pbp_metrics, tendencies)
  - team_analytics.py skeleton with _filter_valid_plays and apply_team_rolling utilities
affects: [15-02, 15-03, silver-player-transformation]

tech-stack:
  added: []
  patterns: [team-season groupby for rolling windows, shared play filtering utility]

key-files:
  created: [src/team_analytics.py]
  modified: [src/player_analytics.py, src/config.py, tests/test_player_analytics.py]

key-decisions:
  - "Rolling window groupby uses [entity, season] tuple to prevent cross-season data leakage"
  - "team_analytics.py uses same rolling pattern as player_analytics.py but grouped by [team, season]"

patterns-established:
  - "Season-scoped rolling: always group by [entity, season] for shift+rolling transforms"
  - "Play filtering: _filter_valid_plays() as standard entry point for PBP analysis"

requirements-completed: [PBP-05, INFRA-01]

duration: 2min
completed: 2026-03-14
---

# Phase 15 Plan 01: Foundation and Bug Fix Summary

**Fixed rolling window cross-season contamination bug, registered Silver team S3 paths, and created team_analytics.py skeleton with shared play filtering and rolling window utilities**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T03:40:31Z
- **Completed:** 2026-03-14T03:42:13Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Fixed PBP-05: rolling window groupby changed from player_id to [player_id, season] preventing cross-season data leakage
- Added 3 regression tests (TestRollingSeasonFix) proving season boundary reset works correctly
- Registered SILVER_TEAM_S3_KEYS in config.py with pbp_metrics and tendencies paths
- Created team_analytics.py with _filter_valid_plays() and apply_team_rolling() shared utilities

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix rolling window bug and add regression test** - `de3870d` (fix)
2. **Task 2: Register config paths and create team_analytics.py skeleton** - `8336138` (feat)

## Files Created/Modified
- `src/player_analytics.py` - Fixed groupby in rolling window loop (line 213)
- `tests/test_player_analytics.py` - Added TestRollingSeasonFix class with 3 regression tests
- `src/config.py` - Added SILVER_TEAM_S3_KEYS dict with pbp_metrics and tendencies entries
- `src/team_analytics.py` - New module with _filter_valid_plays() and apply_team_rolling() utilities

## Decisions Made
- Rolling window groupby uses [entity, season] tuple to prevent cross-season contamination -- matches existing STD expanding average pattern
- team_analytics.py apply_team_rolling() mirrors player_analytics.py compute_rolling_averages() pattern but groups by [team, season]

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- team_analytics.py skeleton ready for Plan 02 (PBP team metrics) and Plan 03 (tendencies)
- SILVER_TEAM_S3_KEYS registered for Silver output paths
- All 189 tests passing (12 player_analytics tests including 3 new regression tests)

## Self-Check: PASSED

All artifacts verified: 4 files found, 2 commits found, all content assertions passed, team_analytics.py has 126 lines (> 60 minimum).

---
*Phase: 15-pbp-team-metrics-and-tendencies*
*Completed: 2026-03-14*
