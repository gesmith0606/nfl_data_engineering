---
phase: 18-historical-context
plan: 01
subsystem: analytics
tags: [combine, draft, jimmy-johnson, speed-score, dimension-table, percentiles]

# Dependency graph
requires:
  - phase: none
    provides: standalone dimension table (uses Bronze combine/draft data)
provides:
  - src/historical_profiles.py with 8 pure compute functions for combine/draft profiles
  - tests/test_historical_profiles.py with 15 unit tests
  - SILVER_PLAYER_S3_KEYS entry for historical_profiles
affects: [18-02-historical-context]

# Tech tracking
tech-stack:
  added: []
  patterns: [pure-function compute module with no I/O, full-outer-join with coalesce pattern]

key-files:
  created:
    - src/historical_profiles.py
    - tests/test_historical_profiles.py
  modified:
    - src/config.py

key-decisions:
  - "NaN propagation for all composite scores -- no imputation or fill"
  - "Catch radius proxy uses raw height_inches (simplest meaningful proxy)"
  - "Compensatory picks 225-262 use linear extrapolation with 0.4 floor"

patterns-established:
  - "Pure compute module + CLI separation: all transform logic in src/, all I/O in scripts/"
  - "Coalesce pattern for outer joins: prefer combine values, fall back to draft values"

requirements-completed: [HIST-01, HIST-02]

# Metrics
duration: 3min
completed: 2026-03-15
---

# Phase 18 Plan 01: Historical Profiles Compute Module Summary

**Pure compute module with 8 functions for combine/draft dimension table: speed score, BMI, burst score, position percentiles, Jimmy Johnson chart (262 picks), and full-outer-join pipeline with dedup**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-15T21:11:19Z
- **Completed:** 2026-03-15T21:14:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created src/historical_profiles.py with 8 exported pure functions and full type hints/docstrings
- Jimmy Johnson chart covers all 262 picks (224 standard + 38 compensatory via linear extrapolation)
- Combine dedup resolves duplicate pfr_ids by preferring season==draft_year match quality
- Full outer join preserves combine-only (UDFAs) and draft-only (no combine) players
- 15 unit tests covering NaN propagation, dedup logic, join row counts, chart monotonicity, and end-to-end pipeline

## Task Commits

Each task was committed atomically:

1. **Task 1: Register config path and create historical_profiles.py module** - `3d8eef8` (feat)
2. **Task 2: Write unit tests for historical_profiles module** - `07d2486` (test)

## Files Created/Modified
- `src/historical_profiles.py` - 8 pure compute functions for combine/draft dimension table
- `tests/test_historical_profiles.py` - 15 unit tests covering all compute functions
- `src/config.py` - Added historical_profiles to SILVER_PLAYER_S3_KEYS

## Decisions Made
- NaN propagation for all composite scores (no imputation) -- matches plan specification and research recommendation
- Catch radius proxy is simply height_inches -- simplest meaningful proxy per user constraint
- Compensatory picks 225-262 extrapolated linearly with 0.042/pick decay and 0.4 floor

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Compute module ready for Plan 02 (CLI script wiring)
- All 8 functions tested and importable
- Config path registered for Silver output
- Full test suite (289 tests) passes with no regressions

---
*Phase: 18-historical-context*
*Completed: 2026-03-15*
