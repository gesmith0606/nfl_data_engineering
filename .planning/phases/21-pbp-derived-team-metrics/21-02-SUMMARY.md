---
phase: 21-pbp-derived-team-metrics
plan: 02
subsystem: analytics
tags: [pandas, pbp, special-teams, drive-efficiency, field-goal, time-of-possession]

# Dependency graph
requires:
  - phase: 20-infrastructure-and-data-expansion
    provides: 140-column PBP Bronze data with ST, drive, kick_distance columns
provides:
  - compute_fg_accuracy with 4-bucket distance classification
  - compute_return_metrics with touchback proxy detection
  - compute_drive_efficiency with 3-and-out drive-level detection
  - compute_top with M:SS string parsing
  - _filter_st_plays helper for special teams play filtering
  - _parse_top_seconds and _fg_bucket helpers
affects: [21-03-orchestrator, silver-team-transformation]

# Tech tracking
tech-stack:
  added: []
  patterns: [touchback-proxy-detection, drive-level-then-team-week-aggregation, string-to-seconds-parsing]

key-files:
  created: []
  modified:
    - src/team_analytics.py
    - tests/test_team_analytics.py

key-decisions:
  - "Touchback proxy: KO uses return_yards==0 + kickoff_returner_player_id IS NULL; punt uses punt_in_endzone==1"
  - "FG buckets use kick_distance with NFL-standard <30/30-39/40-49/50+ split"
  - "Drive efficiency uses drive-level groupby first, then team-week aggregation"
  - "TOP parsing handles M:SS strings with try/except fallback to NaN"
  - "Added _filter_st_plays helper (Plan 01 dependency) as Rule 3 auto-fix"

patterns-established:
  - "Drive-level aggregation: groupby (team, season, week, drive) then aggregate to (team, season, week)"
  - "ST metrics attributed to returning team (defteam) not kicking team (posteam)"
  - "Proxy column detection when canonical column missing from PBP schema"

requirements-completed: [PBP-05, PBP-06, PBP-09, PBP-11]

# Metrics
duration: 4min
completed: 2026-03-16
---

# Phase 21 Plan 02: Complex PBP-Derived Metrics Summary

**FG accuracy by 4 distance buckets, punt/kick return metrics with touchback proxy detection, drive efficiency with 3-and-out flagging, and time of possession from parsed M:SS strings**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-16T22:26:53Z
- **Completed:** 2026-03-16T22:31:04Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- 4 complex compute functions + 2 helpers added to team_analytics.py
- 8 new tests (4 parse_top + 1 FG + 1 return + 1 drive + 1 TOP) all passing
- Touchback detection via proxy columns (no touchback column in PBP data)
- 65 total tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 4 complex compute functions + TOP parser** - `1b135d3` (feat)
2. **Task 2: Add unit tests for all 4 complex compute functions** - `7e00609` (test)

## Files Created/Modified
- `src/team_analytics.py` - Added _filter_st_plays, _parse_top_seconds, _fg_bucket, compute_fg_accuracy, compute_return_metrics, compute_drive_efficiency, compute_top
- `tests/test_team_analytics.py` - Added TestParseTopSeconds, TestComputeFGAccuracy, TestComputeReturnMetrics, TestComputeDriveEfficiency, TestComputeTOP

## Decisions Made
- Used _filter_st_plays as base filter for FG and return metrics (union of special_teams_play==1 OR ST play types)
- FG accuracy uses kick_distance (actual kick length) not yardline_100 for bucket classification
- Return metrics attributed to defteam (returning team) since posteam is the kicking team
- Drive efficiency counts plays via epa column count when play_id not available in test data
- TOP uses max per drive (all plays carry same drive TOP value) then sum across drives

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added _filter_st_plays helper from Plan 01**
- **Found during:** Task 1 (implementation)
- **Issue:** Plan 02 references _filter_st_plays which was specified in Plan 01 but Plan 01 hasn't been executed yet
- **Fix:** Added _filter_st_plays directly in Task 1 implementation, following the exact specification from 21-RESEARCH.md
- **Files modified:** src/team_analytics.py
- **Verification:** Import succeeds, FG and return metrics use it correctly
- **Committed in:** 1b135d3 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for FG and return metric functions to work. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 complex compute functions ready for orchestrator integration in Plan 03
- Plan 01 simple metrics should be executed to add remaining 7 compute functions before orchestrator
- _filter_st_plays helper already available (won't need duplicate in Plan 01)

---
*Phase: 21-pbp-derived-team-metrics*
*Completed: 2026-03-16*
