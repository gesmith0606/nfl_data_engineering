---
phase: 10-existing-type-backfill
plan: 02
subsystem: ingestion
tags: [snap-counts, backfill, parquet, bronze, week-partitioning]

# Dependency graph
requires:
  - phase: 10-existing-type-backfill
    provides: "Fixed snap_counts adapter with week_partition registry flag"
provides:
  - "Week-partitioned snap_counts Parquet files for 2016-2025 (10 seasons, 215 files)"
  - "Full coverage verification across all 6 existing Bronze data types"
affects: [11-01-PLAN, silver-transformation]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified: []

key-decisions:
  - "Backfilled schedules 2020-2025 and snap_counts 2020-2024 to fill gaps left by expired S3 credentials (Rule 3 auto-fix)"
  - "player_weekly and player_seasonal 2025 remain absent -- nflverse returns HTTP 404 (data not yet published)"

patterns-established: []

requirements-completed: [BACKFILL-04]

# Metrics
duration: 2min
completed: 2026-03-11
---

# Phase 10 Plan 02: Snap Counts Backfill and Coverage Verification Summary

**Backfilled snap_counts with week-level partitioning for all 10 seasons (2016-2025, 215 Parquet files) plus filled schedules and snap_counts gaps from expired S3 era**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-11T23:34:14Z
- **Completed:** 2026-03-11T23:36:13Z
- **Tasks:** 2
- **Files modified:** 0 (data-only; Parquet files in .gitignore)

## Accomplishments
- Ingested snap_counts for 2016-2019 with week-level partitioning (84 week directories, ~95K records)
- Ingested snap_counts for 2025 (22 weeks, 26.6K records)
- Ingested snap_counts for 2020-2024 to fill gap from expired S3 (109 week directories, ~131K records)
- Backfilled schedules for 2020-2025 (6 seasons, ~1.7K records)
- Full coverage verified: 6/6 types pass with 10-year history (except player_weekly/seasonal 2025 -- nflverse 404)
- All 161 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Backfill snap_counts 2016-2025 with week partitioning** - no commit (data-only, Parquet files in .gitignore)
2. **Task 2: Verify full Phase 10 coverage** - no commit (verification-only, no code changes)

## Files Created/Modified
- `data/bronze/players/snaps/season=2016-2025/week=*/` - 215 Parquet files with week-level partitioning
- `data/bronze/schedules/season=2020-2025/` - 6 schedule Parquet files

## Decisions Made
- Backfilled schedules 2020-2025 and snap_counts 2020-2024 (Rule 3: blocking coverage gaps from S3-only era)
- Accepted player_weekly/seasonal 2025 as unavailable (HTTP 404 from nflverse, consistent with Plan 01 findings)
- snap_counts validation warns about missing `player_id` column (uses `player` instead) -- known schema difference, non-blocking per Bronze-stores-raw policy

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Backfilled schedules 2020-2025 and snap_counts 2020-2024**
- **Found during:** Task 2 (coverage verification)
- **Issue:** Schedules 2020-2025 and snap_counts 2020-2024 were missing locally (previously S3-only, credentials expired)
- **Fix:** Ran bronze_ingestion_simple.py for both types to fill gaps
- **Files modified:** data/bronze/schedules/ and data/bronze/players/snaps/ (data only)
- **Verification:** Coverage report shows 10/10 seasons for both types
- **Committed in:** N/A (data-only)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential to meet the plan's success criteria of "complete Parquet file coverage for target season ranges." No scope creep.

## Issues Encountered
- snap_counts validation reports `is_valid: False` due to missing `player_id` column -- snap_counts schema uses `player` field instead. This is a pre-existing validation issue (logged in Plan 01), not a data quality problem.
- player_weekly and player_seasonal 2025 return HTTP 404 from nflverse -- not yet published, consistent with Plan 01.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 10 complete: all 6 existing data types have full local coverage
- Phase 11 (Orchestration and Validation) can now proceed
- snap_counts `player_id` validation issue should be addressed in Phase 11 validation sweep

---
*Phase: 10-existing-type-backfill*
*Completed: 2026-03-11*

## Self-Check: PASSED
- SUMMARY.md created
- snap_counts 2016-2025: 10 season directories with week-level partitioning (215 files)
- schedules 2020-2025: 6 files filling gap
- All 161 tests passing
- No code commits (data-only tasks, Parquet in .gitignore)
