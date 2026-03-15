---
phase: 15-pbp-team-metrics-and-tendencies
plan: 03
subsystem: analytics
tags: [pandas, parquet, team-tendencies, pace, proe, fourth-down, early-down, rolling-windows]

requires:
  - phase: 15-02
    provides: "team_analytics.py with PBP metrics, _filter_valid_plays, apply_team_rolling"
provides:
  - "Tendency metric functions (pace, PROE, 4th down, early-down run rate) in team_analytics.py"
  - "compute_tendency_metrics orchestrator with rolling windows"
  - "Silver team transformation CLI at scripts/silver_team_transformation.py"
  - "Data dictionary schemas for Silver team tables"
affects: [16-situational-breakdowns, 17-advanced-player-profiles, projection-engine]

tech-stack:
  added: []
  patterns: [tendency-metric-computation, cli-script-mirroring]

key-files:
  created:
    - scripts/silver_team_transformation.py
  modified:
    - src/team_analytics.py
    - tests/test_team_analytics.py
    - docs/NFL_DATA_DICTIONARY.md

key-decisions:
  - "4th down aggressiveness accepts raw PBP (not _filter_valid_plays output) to include punt/FG play types in denominator"
  - "PROE uses pandas mean() for xpass which auto-excludes NaN while keeping NaN rows in total play count"

patterns-established:
  - "Tendency functions return (team, season, week, metric) DataFrames matching PBP metric pattern"
  - "Silver team CLI mirrors silver_player_transformation.py structure exactly"

requirements-completed: [TEND-01, TEND-02, TEND-03, TEND-04, INFRA-02, INFRA-03]

duration: 4min
completed: 2026-03-14
---

# Phase 15 Plan 03: Team Tendency Metrics Summary

**Tendency metrics (pace, PROE, 4th down aggressiveness, early-down run rate) with rolling windows, Silver CLI script, and data dictionary schemas**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T03:49:14Z
- **Completed:** 2026-03-14T03:53:11Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Implemented 4 tendency metric functions + orchestrator with rolling window support
- Created Silver team transformation CLI producing two Parquet outputs per season
- Documented both Silver team table schemas in the data dictionary
- 14 new tests (36 total team analytics tests), 225 full suite passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement tendency metric functions with tests** - `4a8c952` (feat, TDD)
2. **Task 2: Create Silver team transformation CLI script** - `959d790` (feat)
3. **Task 3: Update data dictionary with Silver team table schemas** - `e40a36c` (docs)

## Files Created/Modified
- `src/team_analytics.py` - Added compute_pace, compute_proe, compute_fourth_down_aggressiveness, compute_early_down_run_rate, compute_tendency_metrics
- `tests/test_team_analytics.py` - Added TestPace, TestPROE, TestFourthDown, TestEarlyDownRunRate, TestTendencyMetricsOrchestrator (14 new tests)
- `scripts/silver_team_transformation.py` - New CLI script for Silver team transformation (PBP metrics + tendencies)
- `docs/NFL_DATA_DICTIONARY.md` - Added Silver Team PBP Metrics and Silver Team Tendencies table schemas

## Decisions Made
- 4th down aggressiveness accepts raw PBP (not _filter_valid_plays output) because _filter_valid_plays strips punt/field_goal play types which are needed as the denominator for go rate
- PROE leverages pandas mean() auto-NaN-exclusion for xpass while keeping NaN rows in total play count for actual_pass_rate

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 15 complete: all 3 plans (infrastructure, PBP metrics, tendencies) are finished
- team_analytics.py provides full PBP + tendency metrics for downstream phases
- Silver team CLI can produce Parquet files for situational breakdowns (Phase 16)
- Rolling window pattern established for all future team-level metrics

## Self-Check: PASSED

- All 5 files found on disk
- All 3 task commits verified (4a8c952, 959d790, e40a36c)
- Line counts: team_analytics.py=535 (>=250), tests=737 (>=200), CLI=225 (>=80)

---
*Phase: 15-pbp-team-metrics-and-tendencies*
*Completed: 2026-03-14*
