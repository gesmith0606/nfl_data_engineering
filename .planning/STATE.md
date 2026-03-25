---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Prediction Model Improvement
status: unknown
stopped_at: Completed 28-02-PLAN.md (Silver player quality transformation)
last_updated: "2026-03-25T21:23:31.176Z"
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 2
  completed_plans: 2
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 28 — infrastructure-player-features

## Current Milestone

v2.0 Prediction Model Improvement -- 4 phases (28-31), 19 requirements

## Current Position

Phase: 29
Plan: Not started

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Config | .planning/config.json |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Requirements | .planning/REQUIREMENTS.md |
| Research | .planning/research/SUMMARY.md |
| Codebase Map | .planning/codebase/ |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

Carried from v1.4:

- Differential features (home-away) halves feature space from ~680 to ~180
- Conservative hyperparameters mandatory (shallow trees, strong regularization, early stopping)
- 2024 season sealed as untouched holdout
- Vegas lines excluded as input features (zero edge by definition)

New for v2.0:

- Data leakage fix: 110 same-week raw stats excluded from features (337->283 features)
- Real baseline: 53.2% ATS overall, 50.0% holdout (not the 90.7% from leaked model)
- Build order: infra -> player features -> feature selection -> ensemble -> advanced features
- Feature budget ceiling: 150 features max in final model
- [Phase 28]: CatBoost 1.2.10 pinned (above 1.2.7 floor); SHAP 0.49.1 Python 3.9 compatible via numba 0.60.0
- [Phase 28]: carry_share computed from carries/team_total_carries (Bronze lacks this column)
- [Phase 28]: backup_qb_start excluded from features until added to _PRE_GAME_CONTEXT
- [Phase 28]: Defensive injury impact uses equal weighting (no usage shares for defense)

### Pending Todos

- Commit leakage fix to feature_engineering.py (Phase 28)
- Verify player Silver shift(1) lag status before building player features (Phase 28)

### Blockers/Concerns

- ~2,100 training games with 283 features -- overfitting risk remains
- Player-level features need careful aggregation to game level (avoid leakage again)
- SHAP 0.48.0 is the last Python 3.9 compatible version -- must pin exactly

## Session Continuity

Last session: 2026-03-25T13:48:20.098Z
Stopped at: Completed 28-02-PLAN.md (Silver player quality transformation)
Resume file: None

---
*Last updated: 2026-03-24 after v2.0 roadmap created*
