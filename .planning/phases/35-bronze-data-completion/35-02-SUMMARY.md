---
phase: 35-bronze-data-completion
plan: 02
subsystem: testing
tags: [bronze, smoke-tests, 2025, data-completeness, holdout]

# Dependency graph
requires:
  - phase: v1.1 Bronze Backfill
    provides: 2025 Bronze data files for 7 core data types
provides:
  - 11 smoke tests verifying 2025 Bronze data completeness (BRNZ-03)
  - Automated holdout readiness check (schedules >= 285 games)
  - Injury gap documentation (nflverse caps at 2024)
affects: [phase-36-silver-transformations, phase-37-holdout-reset]

# Tech tracking
tech-stack:
  added: []
  patterns: [smoke-test-class-per-season, glob-based-file-existence]

key-files:
  created:
    - tests/test_bronze_2025.py
  modified: []

key-decisions:
  - "Smoke tests use glob patterns for file existence -- no S3 or API dependency"
  - "Row count thresholds based on research: >= 285 schedules, >= 40000 PBP"

patterns-established:
  - "Season completeness test class: TestBronze{YYYY}Completeness with per-type existence + row count + meta-test"

requirements-completed: [BRNZ-03]

# Metrics
duration: 2min
completed: 2026-03-28
---

# Phase 35 Plan 02: 2025 Bronze Completeness Summary

**11 smoke tests confirming all 7 available Bronze data types exist for 2025, with schedule row count (285+ games) validating holdout candidacy**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-28T23:24:11Z
- **Completed:** 2026-03-28T23:26:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- All 7 available Bronze data types verified present for 2025 season
- Schedule row count confirmed >= 285 games (272 REG + 13 POST), satisfying D-06 holdout threshold
- PBP row count confirmed >= 40,000 rows (full season coverage)
- Injury data gap documented as expected -- nflverse caps at 2024, validate_season_for_type returns False
- Meta-test validates all 7 types in single assertion for quick regression detection

## Task Commits

Each task was committed atomically:

1. **Task 1: Create 2025 Bronze completeness smoke tests** - `9d46b2c` (test)

## Files Created/Modified
- `tests/test_bronze_2025.py` - 11 smoke tests for 2025 Bronze data completeness (BRNZ-03)

## Decisions Made
- Used glob-based file existence checks (no S3 or API calls) for fast, offline-capable testing
- Row count thresholds set conservatively: >= 285 schedules (272 REG + 13 POST), >= 40000 PBP rows
- Snap count threshold at >= 18 week subdirectories (allows for partial playoff weeks)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all tests are fully wired to local Bronze data.

## Next Phase Readiness
- 2025 confirmed as viable holdout candidate for Phase 37
- All 7 Bronze data types ready for Silver transformations in Phase 36
- Injury gap is a known limitation (not a blocker) -- downstream injury adjustments will be absent for 2025

---
*Phase: 35-bronze-data-completion*
*Completed: 2026-03-28*
