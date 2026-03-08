---
phase: 03-advanced-stats-context-data
plan: 01
subsystem: ingestion
tags: [qbr, ngs, pfr, combine, depth-charts, draft-picks, validation, bronze]

requires:
  - phase: 01-infrastructure-prerequisites
    provides: Registry-based dispatch and NFLDataAdapter
provides:
  - QBR frequency CLI arg (--frequency weekly/seasonal)
  - QBR frequency-prefixed filenames preventing collisions
  - validate_data() entries for 7 new Bronze data types
affects: [03-advanced-stats-context-data, silver-transformation]

tech-stack:
  added: []
  patterns: [frequency-aware filename generation for multi-mode data types]

key-files:
  created: []
  modified:
    - scripts/bronze_ingestion_simple.py
    - src/nfl_data_integration.py

key-decisions:
  - "QBR filenames use frequency prefix (qbr_weekly_*.parquet / qbr_seasonal_*.parquet) to prevent collisions"
  - "validate_data() uses common columns shared across sub-types (conservative Bronze validation)"

patterns-established:
  - "Frequency-prefixed filenames: data types with multiple frequencies include frequency in filename to prevent overwrite"

requirements-completed: [ADV-04, VAL-01, VAL-02]

duration: 1min
completed: 2026-03-08
---

# Phase 3 Plan 1: QBR Frequency Fix and Validation Rules Summary

**QBR CLI now supports --frequency weekly/seasonal with distinct filenames; validate_data() expanded from 8 to 15 data type entries**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-08T17:05:16Z
- **Completed:** 2026-03-08T17:06:31Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- QBR ingestion supports both weekly and seasonal frequency via --frequency CLI arg
- QBR weekly and seasonal files save to distinct filenames (qbr_weekly_*.parquet / qbr_seasonal_*.parquet)
- validate_data() recognizes all 7 new data types (ngs, pfr_weekly, pfr_seasonal, qbr, depth_charts, draft_picks, combine)
- All 100 existing tests remain passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --frequency CLI arg and fix QBR wiring + filename** - `569d04b` (feat)
2. **Task 2: Add 7 new data type entries to validate_data()** - `39f30e0` (feat)

## Files Created/Modified
- `scripts/bronze_ingestion_simple.py` - Added --frequency arg, wired args.frequency into QBR kwargs, frequency-prefixed QBR filenames
- `src/nfl_data_integration.py` - Added 7 new required_columns entries to validate_data()

## Decisions Made
- QBR filenames use frequency prefix to prevent weekly/seasonal collisions in same directory
- validate_data() uses common columns shared across sub-types (e.g., NGS passing/rushing/receiving share the same required columns) -- detailed per-sub-type validation deferred to Silver layer

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 7 new data types now have Bronze validation rules
- QBR frequency handling complete for both weekly and seasonal ingestion
- Ready for remaining Phase 3 plans (Silver transformation for advanced stats)

---
*Phase: 03-advanced-stats-context-data*
*Completed: 2026-03-08*
