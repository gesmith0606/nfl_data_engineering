---
phase: 09-new-data-type-ingestion
plan: 02
subsystem: ingestion
tags: [bronze, parquet, qbr, ngs, pfr, nfl-data-py, sub-types]

# Dependency graph
requires:
  - phase: 09-01
    provides: "CLI variant looping, schema diff logging, ingestion summary"
provides:
  - "Bronze QBR data (2006-2025, weekly + seasonal frequencies)"
  - "Bronze NGS data (2016-2025, passing/rushing/receiving)"
  - "Bronze PFR weekly data (2018-2025, pass/rush/rec/def)"
  - "Bronze PFR seasonal data (2018-2025, pass/rush/rec/def)"
  - "Integration tests for variant looping (4 new tests)"
affects: [silver-transformation, 09-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created:
    - data/bronze/qbr/
    - data/bronze/ngs/
    - data/bronze/pfr/
  modified:
    - tests/test_advanced_ingestion.py

key-decisions:
  - "QBR 2024 and 2025 return 0 rows for seasonal frequency -- skipped per empty-data handling, consistent with STATE.md blocker"
  - "PFR seasonal def sub-type missing 'team' column across all seasons -- validation warns but data saved per Bronze-stores-raw policy"

patterns-established: []

requirements-completed: [INGEST-05, INGEST-06, INGEST-07, INGEST-08]

# Metrics
duration: 64min
completed: 2026-03-09
---

# Phase 9 Plan 02: Sub-Type Data Ingestion Summary

**Ingested QBR (20 seasons x 2 frequencies), NGS (10 seasons x 3 stat types), PFR weekly (8 seasons x 4 sub-types), PFR seasonal (8 seasons x 4 sub-types) into Bronze layer with 4 new integration tests**

## Performance

- **Duration:** 64 min
- **Started:** 2026-03-09T20:39:42Z
- **Completed:** 2026-03-09T21:44:01Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Full Bronze coverage for all 4 sub-type/multi-frequency data types across their valid season ranges
- QBR: 36 Parquet files (18 weekly + 18 seasonal; 2024-2025 empty for seasonal variant)
- NGS: 30 Parquet files (10 passing + 10 rushing + 10 receiving)
- PFR weekly: 32 Parquet files (8 pass + 8 rush + 8 rec + 8 def)
- PFR seasonal: 32 Parquet files (8 pass + 8 rush + 8 rec + 8 def)
- 4 new integration tests verifying variant looping and filename prefix behavior
- Full test suite: 156 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Run sub-type data ingestion** - _No commit (data files are gitignored)_
2. **Task 2: Add integration tests** - `832d345` (test)

_Task 1 produced only data files (gitignored); verified via file existence checks._

## Files Created/Modified
- `tests/test_advanced_ingestion.py` - Added 4 tests: PFR weekly all-variants, PFR seasonal all-variants, PFR seasonal single-filter, QBR filename prefix
- `data/bronze/qbr/` - 36 Parquet files across seasons 2006-2025
- `data/bronze/ngs/` - 30 Parquet files (passing/rushing/receiving, 2016-2025)
- `data/bronze/pfr/weekly/` - 32 Parquet files (pass/rush/rec/def, 2018-2025)
- `data/bronze/pfr/seasonal/` - 32 Parquet files (pass/rush/rec/def, 2018-2025)

## Decisions Made
- QBR 2024 + 2025 seasonal frequency returned 0 rows (known nflverse delay per STATE.md blocker) -- skipped gracefully
- PFR seasonal def sub-type has 'team' column missing across all 8 seasons -- validation warns but data saved per Bronze-stores-raw policy
- QBR schema diff: seasons 2006-2019 have 30 columns, 2020+ have 23 columns (7 columns removed including game_id, week_text, opp_* fields)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- QBR 2024 seasonal returns 0 rows (expected per STATE.md blocker -- nflverse data delay)
- QBR 2025 seasonal also returns 0 rows (no data yet for current/upcoming season)
- PFR seasonal def sub-type missing 'team' column -- known schema quirk, validation warns only

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 4 sub-type data types have full Bronze coverage
- Plan 03 can proceed with any remaining ingestion types
- Silver transformation will need to handle QBR schema differences (30 vs 23 columns across seasons)
- PFR seasonal def 'team' column absence should be accounted for in Silver normalization

## Self-Check: PASSED

- tests/test_advanced_ingestion.py: FOUND
- data/bronze/qbr/: FOUND (36 files)
- data/bronze/ngs/: FOUND (30 files)
- data/bronze/pfr/weekly/: FOUND (32 files)
- data/bronze/pfr/seasonal/: FOUND (32 files)
- Commit 832d345: FOUND

---
*Phase: 09-new-data-type-ingestion*
*Completed: 2026-03-09*
