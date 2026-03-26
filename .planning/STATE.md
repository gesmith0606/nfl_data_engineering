---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Prediction Model Improvement
status: unknown
stopped_at: Completed 30-01-PLAN.md
last_updated: "2026-03-26T00:53:44.640Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 6
  completed_plans: 5
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 30 — model-ensemble

## Current Milestone

v2.0 Prediction Model Improvement -- 4 phases (28-31), 19 requirements

## Current Position

Phase: 30 (model-ensemble) — EXECUTING
Plan: 2 of 2

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
- [Phase 29-01]: TreeExplainer over KernelExplainer for exact SHAP on XGBoost
- [Phase 29]: SELECTED_FEATURES initialized as None in config.py -- Phase 30 branches on None vs list
- [Phase 29]: Config rewriting via regex for SELECTED_FEATURES persistence
- [Phase 30]: Generalized CV via model_factory + fit_kwargs_fn callback pattern
- [Phase 30]: RidgeCV auto-selects alpha from [0.01, 0.1, 1.0, 10.0, 100.0] for meta-learner

### Pending Todos

- Commit leakage fix to feature_engineering.py (Phase 28)
- Verify player Silver shift(1) lag status before building player features (Phase 28)

### Blockers/Concerns

- ~2,100 training games with 283 features -- overfitting risk remains
- Player-level features need careful aggregation to game level (avoid leakage again)
- SHAP 0.48.0 is the last Python 3.9 compatible version -- must pin exactly

## Session Continuity

Last session: 2026-03-26T00:53:44.637Z
Stopped at: Completed 30-01-PLAN.md
Resume file: None

---
*Last updated: 2026-03-24 after v2.0 roadmap created*
