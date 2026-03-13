---
phase: 09-new-data-type-ingestion
plan: 01
subsystem: ingestion
tags: [bronze, cli, parquet, nfl-data-py, schema-diff]

# Dependency graph
requires:
  - phase: 08-pre-backfill-guards
    provides: "DATA_TYPE_REGISTRY, NFLDataAdapter, validate_season_for_type"
provides:
  - "CLI variant looping (sub-type + frequency auto-iteration)"
  - "Schema diff logging between consecutive seasons"
  - "Ingestion summary with ingested/skipped counts"
  - "Bronze data: teams, draft_picks (2000-2025), combine (2000-2025), depth_charts (2001-2025)"
affects: [09-02-PLAN, 09-03-PLAN, silver-transformation]

# Tech tracking
tech-stack:
  added: []
  patterns: [variant-looping, schema-diff-logging, ingestion-summary]

key-files:
  created: []
  modified:
    - scripts/bronze_ingestion_simple.py
    - tests/test_advanced_ingestion.py

key-decisions:
  - "QBR frequency choices changed from ['weekly','seasonal'] to ['weekly','season'] to match nfl-data-py API"
  - "Variant looping wraps season loop, not vice versa, for cleaner schema diff tracking per variant"
  - "Depth charts 2025 schema has 11 new columns and 14 removed vs 2024 -- ingested as-is per Bronze-stores-raw policy"

patterns-established:
  - "Variant loop pattern: sub_types list or frequency list iterated automatically when CLI arg is None"
  - "Schema diff: log_schema_diff() compares column sets between consecutive seasons"
  - "Ingestion summary: per-variant count of ingested/skipped seasons printed after each run"

requirements-completed: [INGEST-01, INGEST-02, INGEST-03, INGEST-04]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 9 Plan 01: Simple Type Ingestion Summary

**Enhanced Bronze CLI with variant looping, schema diff logging, and ingestion summary; ingested teams + draft picks + combine + depth charts across full valid season ranges**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-09T20:02:04Z
- **Completed:** 2026-03-09T20:05:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- CLI now auto-loops all sub-types/frequencies when None (no more mandatory --sub-type flag)
- Schema diff logging detects column changes between seasons (caught depth_charts 2025 schema change: 11 new, 14 removed)
- Ingestion summary reports ingested/skipped counts per variant
- Ingested 4 simple data types: teams (1 file), draft_picks (26 seasons), combine (26 seasons), depth_charts (25 seasons)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing tests** - `312cfef` (test)
2. **Task 1 GREEN: CLI enhancements** - `a2a3eaa` (feat)

_Task 2 produced no code changes (data files are gitignored); verified via file existence checks._

## Files Created/Modified
- `scripts/bronze_ingestion_simple.py` - Added variant looping, schema diff, ingestion summary, relaxed sub-type validation, QBR frequency default change
- `tests/test_advanced_ingestion.py` - 7 new tests: variant looping (3), schema diff (1), ingestion summary (1), empty data (1), teams no-season (1)

## Decisions Made
- Changed QBR frequency choices from `["weekly", "seasonal"]` to `["weekly", "season"]` to match nfl-data-py API parameter naming
- Variant loop wraps around the season loop (not inside) so schema diff tracking stays per-variant
- Depth charts 2025 ingested as-is despite major schema change (Bronze stores raw, Silver normalizes)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Depth charts 2025 has a completely different schema from 2024 (11 new columns, 14 removed including `season`, `club_code`, `week`, `position`). Schema diff logging correctly caught this. No action needed -- Bronze stores raw data per project convention.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- CLI variant looping pattern ready for Plan 02 (sub-type data: NGS, PFR weekly, PFR seasonal, QBR)
- Schema diff and ingestion summary will automatically apply to all future ingestion runs
- 152 tests passing (7 new + 145 existing)

## Self-Check: PASSED

- scripts/bronze_ingestion_simple.py: FOUND
- tests/test_advanced_ingestion.py: FOUND
- 09-01-SUMMARY.md: FOUND
- Commit 312cfef: FOUND
- Commit a2a3eaa: FOUND

---
*Phase: 09-new-data-type-ingestion*
*Completed: 2026-03-09*
