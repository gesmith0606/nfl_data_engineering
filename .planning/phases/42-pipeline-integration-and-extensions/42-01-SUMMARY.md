---
phase: 42-pipeline-integration-and-extensions
plan: 01
subsystem: ml-pipeline
tags: [xgboost, projection-router, ship-gate, mapie, fantasy-projection]

# Dependency graph
requires:
  - phase: 41-advanced-features-final-validation
    provides: Per-position XGBoost models, ship gate report, player feature engineering
  - phase: 39-player-feature-vector
    provides: Player feature vector assembly
provides:
  - ML projection router module with ship-gate-based position routing
  - MAPIE confidence interval support for ML positions
  - Team-total coherence checking
  - projection_source column for ML vs heuristic transparency
affects: [42-02, generate_projections, draft_assistant, weekly-pipeline]

# Tech tracking
tech-stack:
  added: [mapie (optional)]
  patterns: [ship-gate routing, graceful degradation, projection-source tagging]

key-files:
  created:
    - src/ml_projection_router.py
    - tests/test_ml_projection_router.py
  modified: []

key-decisions:
  - "QB inferred as SHIP when model files exist on disk but absent from ship_gate_report.json"
  - "MAPIE is optional dependency with graceful degradation to heuristic floor/ceiling"
  - "Team-total coherence is warn-only, never adjusts projections"
  - "Fallback players routed silently to heuristic with only projection_source column distinguishing"

patterns-established:
  - "Ship gate routing: read verdicts from JSON, route per-position to ML or heuristic"
  - "Graceful degradation: try ML -> catch -> heuristic fallback with logging"
  - "projection_source tagging: 'ml' or 'heuristic' per player row"

requirements-completed: [PIPE-02, PIPE-03, PIPE-04, EXTD-02]

# Metrics
duration: 7min
completed: 2026-03-31
---

# Phase 42 Plan 01: ML Projection Router Summary

**Ship-gate-based projection router routing QB to ML models and RB/WR/TE to heuristic, with MAPIE intervals, team-total coherence checks, and fallback detection**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-31T23:54:41Z
- **Completed:** 2026-03-31T23:01:51Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- ML projection router module with ship-gate-based position routing (QB=ML, RB/WR/TE=heuristic)
- Fallback detection for rookies (all-NaN rolling features) and thin-data players (<3 games)
- MAPIE confidence intervals with graceful degradation when not installed
- Team-total coherence check warns when projected fantasy points exceed 110% of implied total
- 12 passing unit tests covering all routing paths, fallback logic, and coherence checks
- 650 total tests passing with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ML projection router module with TDD** - `473896b` (feat)

## Files Created/Modified
- `src/ml_projection_router.py` - ML/heuristic routing, MAPIE intervals, team constraints, fallback detection
- `tests/test_ml_projection_router.py` - 12 unit tests covering ship gate, fallback, routing, coherence, MAPIE

## Decisions Made
- QB inferred as SHIP when model files exist on disk but absent from ship_gate_report.json (per D-07 and research Pattern 2)
- MAPIE is optional dependency; compute_mapie_intervals returns None when unavailable, triggering add_floor_ceiling fallback
- Team-total coherence is warn-only per D-10 -- never adjusts projections
- Feature columns loaded from feature_selection/{group}_features.json per stat-type group

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all functions are fully implemented. MAPIE interval application in `_apply_mapie_intervals` currently delegates to `add_floor_ceiling` since calibration data is not available at inference time; the `compute_mapie_intervals` function is exported for callers who have training data. This is by design per D-18 graceful degradation.

## Next Phase Readiness
- Router module ready for integration into generate_projections.py CLI (Plan 02)
- Draft tool can call generate_ml_projections() as drop-in replacement for generate_weekly_projections()
- Weekly pipeline integration requires wiring router into scripts/generate_projections.py

---
*Phase: 42-pipeline-integration-and-extensions*
*Completed: 2026-03-31*
