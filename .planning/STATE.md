---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Prediction Model Improvement
status: defining_requirements
stopped_at: null
last_updated: "2026-03-23"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Defining v2.0 requirements

## Current Milestone

v2.0 Prediction Model Improvement — defining requirements

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-23 — Milestone v2.0 started

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
- XGBoost only (no LightGBM) — sufficient at ~1,900 game scale → REVISITING in v2.0
- Differential features (home-away) halves feature space from ~680 to ~180
- Conservative hyperparameters mandatory (shallow trees, strong regularization, early stopping)
- 2024 season sealed as untouched holdout
- Vegas lines excluded as input features (zero edge by definition)

New for v2.0:
- Data leakage fix: 110 same-week raw stats excluded from features (337→283 features)
- Real baseline: 53.2% ATS overall, 50.0% holdout (not the 90.7% from leaked model)
- O/U model below break-even (51.9%) — needs most improvement

### Pending Todos

- Commit leakage fix to feature_engineering.py

### Blockers/Concerns

- ~2,100 training games with 283 features — overfitting risk remains
- Player-level features need careful aggregation to game level (avoid leakage again)
- Ensemble adds complexity — ensure each model adds independent signal

## Session Continuity

Last session: 2026-03-23
Stopped at: Defining v2.0 requirements
Resume file: None

---
*Last updated: 2026-03-23 after v2.0 milestone started*
