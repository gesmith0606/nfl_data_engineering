---
phase: 21-pbp-derived-team-metrics
plan: 03
subsystem: analytics
tags: [pbp, team-metrics, rolling-windows, orchestrator, silver-layer]

# Dependency graph
requires:
  - phase: 21-01
    provides: penalty, turnover luck, red zone trips, third down, explosive, sack metric functions
  - phase: 21-02
    provides: FG accuracy, return metrics, drive efficiency, TOP, _filter_st_plays helper
provides:
  - compute_pbp_derived_metrics orchestrator merging all 11 compute functions
  - pbp_derived Silver layer config key and pipeline wiring
  - Integration tests verifying orchestrator merge and rolling window behavior
affects: [22-game-prediction-features, silver-team-transformation, pipeline-health]

# Tech tracking
tech-stack:
  added: []
  patterns: [orchestrator-with-selective-rolling-exclusion]

key-files:
  created: []
  modified:
    - src/team_analytics.py
    - src/config.py
    - scripts/silver_team_transformation.py
    - scripts/check_pipeline_health.py
    - tests/test_team_analytics.py

key-decisions:
  - "Turnover luck columns excluded from rolling windows (uses expanding window internally)"
  - "Orchestrator follows exact pattern of existing compute_pbp_metrics with 11 functions instead of 4"

patterns-established:
  - "Selective rolling exclusion: turnover_cols set filters columns before apply_team_rolling"

requirements-completed: [INTEG-02]

# Metrics
duration: 3min
completed: 2026-03-16
---

# Phase 21 Plan 03: PBP-Derived Metrics Orchestrator Summary

**compute_pbp_derived_metrics orchestrator calling all 11 PBP functions with rolling windows (excluding turnover luck), wired into Silver pipeline and health checks**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-16T22:35:13Z
- **Completed:** 2026-03-16T22:38:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created compute_pbp_derived_metrics orchestrator merging all 11 PBP-derived metric functions
- Rolling windows (_roll3, _roll6, _std) applied to all metrics except turnover luck columns
- Wired orchestrator into silver_team_transformation.py, config.py, and check_pipeline_health.py
- Added 2 integration tests verifying merge correctness and rolling window exclusion
- 325 tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create orchestrator + wire config, script, and health check** - `89d604f` (feat)
2. **Task 2: Add integration tests for orchestrator + rolling windows** - `6924723` (test)

## Files Created/Modified
- `src/team_analytics.py` - Added compute_pbp_derived_metrics orchestrator function
- `src/config.py` - Added pbp_derived key to SILVER_TEAM_S3_KEYS
- `scripts/silver_team_transformation.py` - Imported and called orchestrator, saves output
- `scripts/check_pipeline_health.py` - Added pbp_derived to REQUIRED_SILVER_PREFIXES
- `tests/test_team_analytics.py` - Added 2 integration tests with comprehensive synthetic PBP fixture

## Decisions Made
- Turnover luck columns (fumbles_lost, fumbles_forced, own_fumble_recovery_rate, opp_fumble_recovery_rate, is_turnover_lucky) excluded from rolling windows since they use their own expanding window internally
- Orchestrator follows the exact pattern of compute_pbp_metrics: filter valid plays, call compute functions, merge on (team, season, week), apply rolling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test fixture missing column propagation**
- **Found during:** Task 2 (integration tests)
- **Issue:** _make_pbp_rows helper does not propagate down, third_down_converted, third_down_failed, yards_gained, sack, rush_attempt columns from play dicts
- **Fix:** Set these columns directly on the DataFrame after calling _make_pbp_rows
- **Files modified:** tests/test_team_analytics.py
- **Verification:** Both integration tests pass, 325 total tests green
- **Committed in:** 6924723 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test fixture)
**Impact on plan:** Minor test data fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 11 PBP-derived metrics are now production-ready in a single orchestrator
- Silver pipeline produces pbp_derived parquet files alongside existing pbp_metrics, tendencies, sos, situational
- Phase 21 complete: ready for Phase 22 (game prediction features) which consumes these team metrics

---
*Phase: 21-pbp-derived-team-metrics*
*Completed: 2026-03-16*
