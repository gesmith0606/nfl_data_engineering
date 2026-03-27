---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: Market Data
status: defining_requirements
stopped_at: null
last_updated: "2026-03-27"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Defining requirements for v2.1 Market Data

## Current Milestone

v2.1 Market Data -- historical odds, line movement features, CLV tracking

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-27 — Milestone v2.1 started

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Config | .planning/config.json |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Research | .planning/research/SUMMARY.md |
| Codebase Map | .planning/codebase/ |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

Carried from v2.0:
- 2024 season sealed as untouched holdout
- Vegas closing lines excluded as input features (zero edge by definition)
- Conservative hyperparameters mandatory (shallow trees, strong regularization, early stopping)
- P30 Ensemble is v2.0 production model (53.0% ATS, +$3.09 on 2024 holdout)
- Ablation protocol: add candidate features → re-run selection → ship only if holdout improves
- Ensemble features loaded from metadata.json not config.py

### Pending Todos

None — fresh milestone.

### Blockers/Concerns

- ~2,100 training games with ~100 features — overfitting risk with additional market features
- Need free/low-cost historical odds source with good coverage (2016-2024)
- Opening lines may not be available for all games in older seasons

## Session Continuity

Last session: 2026-03-27
Stopped at: null
Resume file: None

---
*Last updated: 2026-03-27 after v2.1 milestone start*
