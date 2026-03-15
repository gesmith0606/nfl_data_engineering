---
phase: 18-historical-context
plan: 02
subsystem: analytics
tags: [combine, draft, silver, cli, dimension-table, parquet]

# Dependency graph
requires:
  - phase: 18-01
    provides: historical_profiles.py compute module with build_combine_draft_profiles
provides:
  - scripts/silver_historical_transformation.py CLI for combine/draft Silver output
  - data/silver/players/historical/ Parquet dimension table (9892 rows, 63 columns)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [dimension-table CLI reads all seasons at once (not per-season like weekly CLIs)]

key-files:
  created:
    - scripts/silver_historical_transformation.py
  modified:
    - src/historical_profiles.py

key-decisions:
  - "Fixed NaN-NaN cross-product bug in outer join by separating null keys before merge"
  - "CLI reads all Bronze seasons at once since combine/draft is a static dimension table"

patterns-established:
  - "Dimension table CLI pattern: read all seasons, no --seasons flag, single output file"

requirements-completed: [HIST-01, HIST-02]

# Metrics
duration: 2min
completed: 2026-03-15
---

# Phase 18 Plan 02: Silver Historical Transformation CLI Summary

**CLI script producing 9892-row combine/draft dimension table with composites, percentiles, and draft values at data/silver/players/historical/**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-15T21:17:02Z
- **Completed:** 2026-03-15T21:19:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created silver_historical_transformation.py CLI reading all 26 seasons of combine and draft Bronze data
- Fixed NaN-NaN cross-product bug in join_combine_draft that caused 386K row explosion (should be ~10K)
- Output: 9892 rows, 63 columns including raw measurables, composites, percentiles, draft values, gsis_id
- Full test suite (289 tests) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create silver_historical_transformation.py CLI script** - `53a8d89` (feat)
2. **Task 2: Full validation** - no commit (validation-only, no file changes)

## Files Created/Modified
- `scripts/silver_historical_transformation.py` - CLI script for combine/draft dimension table generation
- `src/historical_profiles.py` - Fixed NaN-NaN cross-product bug in join_combine_draft outer join

## Decisions Made
- Fixed NaN-NaN cross-product in pandas outer join by separating null-key rows before merge and concatenating after
- CLI reads all Bronze seasons at once (no --seasons flag) since combine/draft is a static dimension table

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed NaN-NaN cross-product in join_combine_draft**
- **Found during:** Task 1 (CLI script creation and first run)
- **Issue:** pandas outer join matched NaN pfr_id keys, creating 1477 * 256 = 378K cross-product rows (386K total vs expected ~10K)
- **Fix:** Separated null-key rows from both sides before merge, then concatenated them back without joining
- **Files modified:** src/historical_profiles.py
- **Verification:** Output now 9892 rows (within 8K-12K expected range), assertion in build_combine_draft_profiles passes
- **Committed in:** 53a8d89 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential bug fix for correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed bug above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 18 complete: combine/draft dimension table available at data/silver/players/historical/
- 9892 player profiles with composites, percentiles, and draft capital ready for downstream use
- gsis_id column available for roster linkage in future phases

---
*Phase: 18-historical-context*
*Completed: 2026-03-15*
