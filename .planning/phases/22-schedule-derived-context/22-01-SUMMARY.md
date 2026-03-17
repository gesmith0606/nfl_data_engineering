---
phase: 22-schedule-derived-context
plan: 01
subsystem: analytics
tags: [schedules, weather, rest, travel, coaching, haversine, pytz, game-context]

# Dependency graph
requires:
  - phase: 20-infrastructure-and-data-expansion
    provides: STADIUM_COORDINATES dict, Bronze schedules data (2016-2025)
provides:
  - src/game_context.py module with unpivot, weather, rest, travel, coaching compute functions
  - STADIUM_ID_COORDS mapping (42 nflverse stadium_ids to lat/lon/tz)
  - game_context S3 key in SILVER_TEAM_S3_KEYS
  - 22 unit tests covering all five feature categories
affects: [22-02-schedule-script, phase-23-cross-source-features]

# Tech tracking
tech-stack:
  added: [pytz (timezone diffs)]
  patterns: [haversine distance, unpivot home/away to per-team rows, coaching tenure tracking]

key-files:
  created:
    - src/game_context.py
    - tests/test_game_context.py
  modified:
    - src/config.py

key-decisions:
  - "Used actual Bronze stadium_ids (42 verified from data) instead of research estimates -- 15 IDs differed from plan"
  - "Arizona timezone test corrected: summer=0h diff (both UTC-7), winter=1h diff (AZ UTC-7 vs LA UTC-8)"
  - "LON01 mapped to Twickenham Stadium (not Wembley alt) based on actual data inspection"

patterns-established:
  - "STADIUM_ID_COORDS: maps nflverse stadium_id codes to (lat, lon, tz) tuples"
  - "Unpivot pattern: home/away rows -> per-team rows with is_home flag"
  - "Coaching tenure: consecutive weeks with same coach, resets on change, carries across seasons"

requirements-completed: [SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-05]

# Metrics
duration: 6min
completed: 2026-03-17
---

# Phase 22 Plan 01: Game Context Module Summary

**Game context module with haversine travel, DST-aware timezone diffs, weather/rest/coaching features from schedules unpivot, plus 42-entry stadium ID mapping verified against Bronze data**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-17T22:38:06Z
- **Completed:** 2026-03-17T22:44:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Built complete src/game_context.py with 6 public functions and 2 private helpers for all five SCHED requirements
- Added STADIUM_ID_COORDS to config.py with all 42 stadium IDs verified against actual Bronze schedules data (2016-2025)
- 22 unit tests covering unpivot, weather (dome/outdoor/NaN), rest (cap/short/bye/advantage), travel (home/away/neutral), timezone (DST/Arizona), coaching (no-change/offseason/midseason/first-season), and E2E
- Full test suite: 347 tests pass with zero regressions

## Task Commits

1. **Task 1: Add STADIUM_ID_COORDS and create game_context.py** - `6fba767` (feat)
2. **Task 2: Unit tests for all game context functions** - `2c60ce7` (test)

## Files Created/Modified
- `src/game_context.py` - Game context module: unpivot, weather, rest, travel, coaching compute functions
- `src/config.py` - Added STADIUM_ID_COORDS (42 entries) and game_context S3 key
- `tests/test_game_context.py` - 22 unit tests for all compute functions

## Decisions Made
- Used actual Bronze data stadium_ids instead of research estimates -- 15 of 42 IDs differed (e.g., BOS00 not FOX00 for NE, CAR00 not CLT00 for CAR, CHI98 not CHI00 for CHI)
- LON01 mapped to Twickenham Stadium coordinates based on data showing it hosted CLE/LA games in 2016-2017
- Arizona timezone test corrected: 0h diff in summer (both UTC-7), 1h diff in winter (AZ stays UTC-7, LA falls to UTC-8)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected 15 stadium_id codes from research estimates to actual Bronze data values**
- **Found during:** Task 1 (STADIUM_ID_COORDS mapping)
- **Issue:** Plan listed research-estimated IDs (e.g., FOX00, CLT00, CHI00, DAL09) that did not match actual nflverse data
- **Fix:** Queried all Bronze schedules parquet files to extract actual 42 unique stadium_ids, built mapping from verified data
- **Files modified:** src/config.py
- **Verification:** All 42 IDs from Bronze data present in STADIUM_ID_COORDS
- **Committed in:** 6fba767

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential correctness fix -- using wrong stadium_ids would cause KeyError failures in travel distance computation.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- game_context.py ready for Plan 02 to wire into CLI script (silver_game_context_transformation.py)
- All functions tested and importable
- STADIUM_ID_COORDS verified against actual data

---
*Phase: 22-schedule-derived-context*
*Completed: 2026-03-17*
