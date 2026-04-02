---
phase: 43-game-level-constraints
plan: 01
subsystem: projections, constraints
tags: [fantasy-multiplier, team-constraints, normalization, backtest]

# Dependency graph
requires:
  - phase: 42-pipeline-integration-and-extensions
    provides: ML projection router, --ml flag, generate_projections.py CLI
provides:
  - Calibrated NFL-to-fantasy multipliers per scoring format
  - apply_team_constraints() with dampened scaling and dead zone
  - --constrain opt-in CLI flag on generate_projections.py
affects: [generate_projections, ml_projection_router, backtest_projections]

# Tech tracking
tech-stack:
  added: []
  patterns: [dampened-scaling, dead-zone normalization, opt-in constraint flag]

key-files:
  created: []
  modified:
    - src/projection_engine.py
    - src/ml_projection_router.py
    - scripts/generate_projections.py
    - tests/test_ml_projection_router.py

key-decisions:
  - "Calibrated multipliers: half_ppr=3.36, ppr=3.77, standard=2.86 from 2020-2024 empirical data"
  - "Dead zone at +/- 10% of implied fantasy total — small deviations are not adjusted"
  - "Max per-player adjustment capped at 20% to prevent distortion"
  - "SKIP for default: backtest showed MAE regression (4.91 to 5.12); stays opt-in via --constrain"

patterns-established:
  - "Opt-in constraint: new normalization features are additive behind a flag until backtest proves value"
  - "Dampened scaling: proportional adjustment with dead zone and per-player cap"

requirements-completed: [CONSTRAIN-01, CONSTRAIN-02, CONSTRAIN-03, CONSTRAIN-04]

# Metrics
duration: ~45min
completed: 2026-04-01
---

# Phase 43 Plan 01: Game-Level Constraints Summary

**Calibrated team-level normalization with dampened scaling, dead zone, and opt-in --constrain flag; SKIP for default based on backtest regression**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-04-01
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments
- Calibrated NFL-to-fantasy multipliers from 2020-2024 historical data: half_ppr=3.36, ppr=3.77, standard=2.86
- `apply_team_constraints()` with dampened proportional scaling, +/-10% dead zone, and 20% per-player cap
- Wired into both heuristic (`projection_engine.py`) and ML (`ml_projection_router.py`) projection paths
- Added `--constrain` opt-in flag to `generate_projections.py` CLI
- 14 new tests covering calibration, scaling, dead zone, cap, and missing-data edge cases
- 669 total tests passing with no regressions

## Backtest Results

| Metric | Without Constraints | With Constraints | Delta |
|--------|-------------------|------------------|-------|
| MAE | 4.91 | 5.12 | +0.21 (worse) |
| RMSE | 6.72 | 6.89 | +0.17 (worse) |
| Bias | -0.60 | -0.33 | +0.27 (improved) |
| Correlation | 0.510 | 0.503 | -0.007 (worse) |

**Ship-gate decision: SKIP for default.** Constraints improve bias (closer to zero) but degrade individual accuracy (MAE, RMSE). The `--constrain` flag stays as opt-in for users who prefer team-level coherence over per-player accuracy.

## Files Created/Modified
- `src/projection_engine.py` — Added `FANTASY_MULTIPLIERS` constant, `apply_team_constraints()` function
- `src/ml_projection_router.py` — Wired `apply_team_constraints()` into ML projection path when constrain=True
- `scripts/generate_projections.py` — Added `--constrain` argparse flag, conditional call to `apply_team_constraints()`
- `tests/test_ml_projection_router.py` — Added TestTeamConstraints class with 14 tests

## Decisions Made
- Multipliers calibrated as mean(team_fantasy_pts / team_nfl_pts) across all team-games 2020-2024
- Dead zone threshold at 10% — calibrated to avoid adjusting teams with normal projection variance
- Max 20% per-player cap prevents a single player's projection from being distorted by team-level constraint
- Constraints stay opt-in (`--constrain`) not default, based on backtest MAE regression

## Deviations from Plan

None — plan executed as designed. Backtest confirmed the expected tradeoff (better bias, worse MAE).

## Issues Encountered

None.

## User Setup Required

None.

## Known Stubs

None — all functions are fully implemented.

## Next Phase Readiness
- Phase 43 complete: game-level constraints available as opt-in tool
- v3.0 player predictions feature set is closed out
- Ready for v3.1 Neo4j foundation (Phase 44)

---
*Phase: 43-game-level-constraints*
*Completed: 2026-04-01*
