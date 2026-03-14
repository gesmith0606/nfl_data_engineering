---
phase: 17-advanced-player-profiles
plan: 01
subsystem: analytics
tags: [ngs, pfr, qbr, rolling-windows, player-profiles, silver-layer]

requires:
  - phase: 15-pbp-team-metrics
    provides: apply_team_rolling pattern and team_analytics module
provides:
  - apply_player_rolling utility with min_periods=3 and player-level groupby
  - NGS receiving/passing/rushing profile compute functions
  - PFR pressure rate and team blitz rate compute functions
  - QBR profile compute function
  - NaN coverage logging utility
  - Config registration for advanced_profiles Silver output
affects: [17-02-bronze-ingestion, 17-03-silver-cli, gold-projections]

tech-stack:
  added: []
  patterns: [player-level rolling windows with min_periods=3, generic _compute_profile helper]

key-files:
  created:
    - src/player_advanced_analytics.py
    - tests/test_player_advanced_analytics.py
  modified:
    - src/config.py

key-decisions:
  - "Used generic _compute_profile helper to DRY up 6 compute functions"
  - "min_periods=3 for player rolling (stricter than team min_periods=1) per success criteria"
  - "PFR team blitz rate reuses apply_team_rolling from team_analytics (team-level groupby)"

patterns-established:
  - "Player-level rolling: groupby([player_gsis_id, season]) with shift(1) and min_periods=3"
  - "Profile prefix convention: ngs_, pfr_, qbr_ for source attribution"

requirements-completed: [PROF-01, PROF-02, PROF-03, PROF-04, PROF-05, PROF-06]

duration: 3min
completed: 2026-03-14
---

# Phase 17 Plan 01: Player Advanced Analytics Module Summary

**NGS/PFR/QBR compute functions with player-level rolling windows (min_periods=3) and 28 unit tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T21:37:11Z
- **Completed:** 2026-03-14T21:40:41Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- Created player_advanced_analytics.py with 8 exported functions covering all 6 PROF requirements
- Implemented apply_player_rolling with shift(1), groupby([player_gsis_id, season]), min_periods=3 -- no cross-season leakage
- 28 new tests all passing; full suite at 274 tests with no regressions
- Registered advanced_profiles in SILVER_PLAYER_S3_KEYS config

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Failing tests** - `0f71349` (test)
2. **Task 1 GREEN: Implementation** - `2e2eba8` (feat)

## Files Created/Modified
- `src/player_advanced_analytics.py` - All 8 compute functions + rolling utility + NaN coverage logger
- `tests/test_player_advanced_analytics.py` - 28 tests covering rolling, profiles, missing cols, logging
- `src/config.py` - Added advanced_profiles entry to SILVER_PLAYER_S3_KEYS

## Decisions Made
- Used generic _compute_profile helper to DRY up the 6 profile compute functions (all follow same extract-prefix-roll pattern)
- PFR team blitz rate imports and reuses apply_team_rolling from team_analytics since it operates at team level, not player level
- min_periods=3 for player rolling is stricter than team version (min_periods=1) to require meaningful history before producing values

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Module ready for Plan 02 (Bronze ingestion of NGS/PFR/QBR data) and Plan 03 (Silver CLI wiring)
- All 8 functions importable and tested for downstream consumption
- PFR player ID match rate blocker noted in STATE.md still applies to Plan 03 integration

---
*Phase: 17-advanced-player-profiles*
*Completed: 2026-03-14*
