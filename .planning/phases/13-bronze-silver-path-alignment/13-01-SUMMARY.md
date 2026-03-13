---
phase: 13-bronze-silver-path-alignment
plan: 01
subsystem: pipeline
tags: [bronze, silver, parquet, path-alignment, snap-counts, schedules]

requires:
  - phase: 10-bronze-ingestion-expansion
    provides: "Reorganized Bronze storage paths (players/snaps/, schedules/)"
provides:
  - "Silver pipeline reads snap_counts from correct players/snaps/ path"
  - "Silver pipeline reads schedules from correct schedules/ path"
  - "validate_data() uses correct 'player' column for snap_counts"
affects: [silver-pipeline, projection-engine, weekly-pipeline]

tech-stack:
  added: []
  patterns: ["week-partitioned concat for snap_counts in Silver reader"]

key-files:
  created: []
  modified:
    - scripts/silver_player_transformation.py
    - src/nfl_data_integration.py

key-decisions:
  - "snap_counts reader concatenates all week-partitioned files (pd.concat) rather than taking latest"
  - "Removed residual data/bronze/players/snap_counts/ directory (superseded by players/snaps/)"

patterns-established:
  - "Week-partitioned Bronze data: concat all week files when reading into Silver"

requirements-completed: []

duration: 1min
completed: 2026-03-12
---

# Phase 13 Plan 01: Bronze-Silver Path Alignment Summary

**Fixed Silver reader paths for snap_counts (players/snaps/) and schedules (schedules/), corrected validate_data column from player_id to player**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-13T01:58:28Z
- **Completed:** 2026-03-13T01:59:51Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Silver pipeline reads snap_counts from correct `players/snaps/` week-partitioned path with concatenation
- Silver pipeline reads schedules from correct `schedules/` path instead of non-existent `games/`
- `validate_data()` snap_counts validation uses `player` column (matches actual nfl-data-py schema)
- Old `data/bronze/players/snap_counts/` directory removed
- Silver pipeline runs end-to-end for season 2020 without network fallback

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix Silver reader paths and validate_data columns** - `375b253` (fix)
2. **Task 2: Remove residual old snap_counts directory and run Silver pipeline** - no commit (data directory not version-controlled; verification only)

## Files Created/Modified
- `scripts/silver_player_transformation.py` - Fixed `_read_local_bronze()` snap_counts path and `_read_local_schedules()` path
- `src/nfl_data_integration.py` - Changed validate_data snap_counts required column from `player_id` to `player`

## Decisions Made
- snap_counts reader concatenates all week-partitioned files rather than taking latest single file, since snap_counts are stored one file per week
- Removed old snap_counts directory as cleanup (data duplicated in players/snaps/)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Silver pipeline fully functional for all Bronze data types
- Ready for Phase 13 Plan 02 or Phase 14

---
*Phase: 13-bronze-silver-path-alignment*
*Completed: 2026-03-12*
