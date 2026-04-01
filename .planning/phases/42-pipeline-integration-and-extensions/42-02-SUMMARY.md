---
phase: 42-pipeline-integration-and-extensions
plan: 02
subsystem: cli, projections
tags: [argparse, ml-routing, draft-capital, preseason, projection-engine]

# Dependency graph
requires:
  - phase: 42-01
    provides: MLProjectionRouter with generate_ml_projections() entry point
provides:
  - "--ml CLI flag on generate_projections.py for ML-based weekly projections"
  - "draft_capital_boost() function for rookie preseason projection enhancement"
  - "historical_df parameter on generate_preseason_projections (backward compatible)"
affects: [draft-tool, fantasy-projections, preseason-rankings]

# Tech tracking
tech-stack:
  added: []
  patterns: ["opt-in ML routing via CLI flag", "linear decay draft capital boost"]

key-files:
  created: []
  modified:
    - scripts/generate_projections.py
    - src/projection_engine.py
    - tests/test_ml_projection_router.py

key-decisions:
  - "--ml flag is opt-in; default behavior unchanged (backward compatible per D-04)"
  - "--ml in preseason mode is a no-op with informational message, not an error"
  - "Draft capital boost uses linear decay from 1.20 (pick 1) to 1.00 (pick 64+)"
  - "Rookie detection uses single-season presence in seasonal data"

patterns-established:
  - "Opt-in ML flag: new ML features are additive, never replace default behavior without explicit flag"
  - "Draft capital boost: multiplicative adjustment applied after base projection calculation"

requirements-completed: [PIPE-03, EXTD-01]

# Metrics
duration: 27min
completed: 2026-03-31
---

# Phase 42 Plan 02: CLI ML Flag and Preseason Draft Capital Boost Summary

**--ml CLI flag routing QB to ML models with heuristic fallback, plus draft capital boost giving first-round rookies up to 20% preseason projection increase**

## Performance

- **Duration:** 27 min
- **Started:** 2026-04-01T00:17:22Z
- **Completed:** 2026-04-01T00:44:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added --ml flag to generate_projections.py routing weekly projections through ML router (QB uses ML, RB/WR/TE use heuristic)
- Preseason mode gracefully handles --ml as no-op with informational message
- Draft capital boost function gives pick 1 a 20% increase linearly decaying to 0% at pick 64+
- generate_preseason_projections accepts optional historical_df for draft capital data (backward compatible)
- CLI loads Silver historical dimension table automatically in preseason mode
- 5 new tests for draft_capital_boost, all passing (655 total tests, 0 regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --ml flag to generate_projections.py CLI** - `0a15fb6` (feat)
2. **Task 2: Add draft capital boost to preseason projections** - `3be3856` (feat)

## Files Created/Modified
- `scripts/generate_projections.py` - Added --ml flag, ML router import, preseason no-op, historical_df loading
- `src/projection_engine.py` - Added draft_capital_boost(), historical_df param on generate_preseason_projections
- `tests/test_ml_projection_router.py` - Added TestDraftCapitalBoost class with 5 tests

## Decisions Made
- --ml flag is opt-in; without it, behavior is identical to before (per D-04 backward compatibility)
- --ml with --preseason prints informational note and proceeds with heuristic (not an error)
- Draft capital boost uses linear decay formula: 1.20 - (pick - 1) * (0.20 / 63)
- Rookies identified by having data in only 1 season of the seasonal DataFrame
- Join historical_df on gsis_id = player_id to get draft_ovr

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is fully wired and operational.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 42 complete: ML projection router (Plan 01) and CLI integration (Plan 02) both shipped
- Draft assistant can consume ML projection output via --projections-file with no code changes needed
- Ready for v3.1 Neo4j foundation or production pipeline work

---
*Phase: 42-pipeline-integration-and-extensions*
*Completed: 2026-03-31*
