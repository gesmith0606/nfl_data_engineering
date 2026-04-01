---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: Player Fantasy Prediction System
status: unknown
stopped_at: Completed 42-02-PLAN.md
last_updated: "2026-04-01T00:50:57.048Z"
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 8
  completed_plans: 8
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-29)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 42 — pipeline-integration-and-extensions

## Current Milestone

v3.0 Player Fantasy Prediction System -- Phases 39-42

## Current Position

Phase: 42
Plan: Not started

## Performance Metrics

**Velocity:**

- Total plans completed: 0 (v3.0)
- Average duration: --
- Total execution time: --

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Config | .planning/config.json |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Requirements | .planning/REQUIREMENTS.md |
| Research | .planning/research/SUMMARY.md |
| Phase 39 P01 | 4min | 2 tasks | 3 files |
| Phase 40 P01 | 33min | 2 tasks | 2 files |
| Phase 40 P02 | 5min | 2 tasks | 3 files |
| Phase 41 P01 | 3min | 1 tasks | 3 files |
| Phase 41 P02 | 5min | 2 tasks | 3 files |
| Phase 42 P01 | 7min | 1 tasks | 2 files |
| Phase 42 P02 | 27min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

- [Phase 39]: Separate player_feature_engineering.py module to keep game-level and player-level assembly independent
- [Phase 39]: Team-level def_epa_per_play as proxy for position-specific defensive EPA (lagged with shift(1))
- [Phase 40]: TD/turnover stats use shallower trees (max_depth=3, min_child_weight=10) vs yardage/volume for sparse count data
- [Phase 40]: Player OOF predictions keyed by row index (not game_id) since player-week data lacks game_id equivalent
- [Phase 40]: Heuristic baseline re-runs usage_multiplier inline to avoid coupling with projection_engine internals
- [Phase 41]: Safe division with np.where for ratio features (NaN for zero denominator)
- [Phase 41]: XGB+LGB+Ridge (no CatBoost) for player ensemble per D-10 design
- [Phase 41]: Two-stage ship gate: features-only first, ensemble only for SKIP positions
- [Phase 42]: QB inferred as SHIP when model files exist on disk but absent from ship_gate_report.json
- [Phase 42]: MAPIE optional with graceful degradation to heuristic floor/ceiling
- [Phase 42]: Team-total coherence is warn-only, never adjusts projections
- [Phase 42]: --ml CLI flag is opt-in; default behavior unchanged (backward compatible)
- [Phase 42]: Draft capital boost: linear decay from 1.20 (pick 1) to 1.00 (pick 64+) for rookie preseason projections

### Research Flags

- Phase 41 (MAPIE integration): Confirm MapieRegressor wraps stacked model correctly
- Phase 39: Validate red zone carry share availability in Silver before committing to TD regression approach
- QB sample size (~300 player-weeks/season): May keep heuristic for QBs if CV does not improve

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-04-01T00:46:20.621Z
Stopped at: Completed 42-02-PLAN.md
Resume file: None

---
*Last updated: 2026-03-29 after v3.0 roadmap created*
