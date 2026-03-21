---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: ML Game Prediction
status: unknown
stopped_at: Completed 26-02-PLAN.md
last_updated: "2026-03-21T21:33:58.095Z"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 7
  completed_plans: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-19)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 26 — backtesting-and-validation

## Current Milestone

v1.4 ML Game Prediction — 4 phases (24-27), 20 requirements, 8 plans

## Current Position

Phase: 26 (backtesting-and-validation) — EXECUTING
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
Recent decisions for v1.4:

- XGBoost only (no LightGBM) — sufficient at ~1,900 game scale
- Differential features (home-away) halves feature space from ~680 to ~180
- Conservative hyperparameters mandatory (shallow trees, strong regularization, early stopping)
- 2024 season sealed as untouched holdout
- Vegas lines excluded as input features (zero edge by definition)
- [Phase 24-documentation-refresh]: Fixed generate_inventory.py to use latest file schema for PBP 140-column count
- [Phase 24]: Document all 12 Silver paths (not 11) -- research confirmed 12 exist on disk
- [Phase 25]: Vectorized diff computation with pd.concat to avoid DataFrame fragmentation
- [Phase 25]: 337 feature columns (322 diff + 15 context) from 8 Silver sources via game_context bridge
- [Phase 25]: early_stopping_rounds popped from params and passed to XGBRegressor constructor separately
- [Phase 25]: Added --model-dir flag for test isolation via pytest tmp_path
- [Phase 26]: Pushes excluded from W/L record and profit (money returned at -110 vig)
- [Phase 26]: LEAKAGE_THRESHOLD=0.58 per STATE.md blocker guidance
- [Phase 26]: Holdout section only for spread target (ATS is primary market-beating metric)

### Pending Todos

None.

### Blockers/Concerns

- Verify `spread_line` in schedules is closing line (not opening) before backtesting
- ~1,900 training games with 180+ features — overfitting risk
- Realistic ATS accuracy: 52-55%; above 58% should trigger leakage investigation

## Session Continuity

Last session: 2026-03-21T21:33:58.092Z
Stopped at: Completed 26-02-PLAN.md
Resume file: None

---
*Last updated: 2026-03-20 after v1.4 roadmap created*
