---
gsd_state_version: 1.0
milestone: v3.1
milestone_name: Graph-Enhanced Fantasy Projections
status: complete
stopped_at: null
last_updated: "2026-04-02T00:00:00.000Z"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 11
  completed_plans: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-02)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** v3.1 complete — preparing next milestone

## Current Milestone

v3.1 Graph-Enhanced Fantasy Projections — COMPLETE

## Current Position

Phase: All 5 phases complete (49-53)
Plan: All 11 plans executed (49-01, 50-01, 51-01, 52-01, 53-01 through 53-06)
Status: Milestone complete — ready for archival
Last activity: 2026-04-02 — Phase 53-06 shipped (MAE 4.91 -> 4.77)

## Phase Summary

| Phase | Name | Plans | Status |
|-------|------|-------|--------|
| 49 | PBP Participation Data Ingestion | 1 | DONE |
| 50 | Populate Graph Features | 1 | DONE |
| 51 | Ship/Skip Gate — Graph Models | 1 | DONE |
| 52 | Kicker Backtesting | 1 | DONE |
| 53 | Model Architecture Improvements | 6 | DONE |

## Key Results

- **Graph features**: 17/22 survived SHAP selection but did not beat heuristic for RB/WR/TE
- **Hybrid residual**: WR and TE improved via heuristic + Ridge residual correction
- **Final routing**: QB=XGB ML, RB=XGB ML, WR=Heuristic+Residual, TE=Heuristic+Residual
- **Fantasy MAE**: 4.91 -> 4.77 (overall, Half-PPR, 2022-2024 backtest)
- **Kicker**: MAE 4.14, near-random correlation (0.034) — kickers are inherently volatile
- **Tests**: 899 passing (up from 841)

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Config | .planning/config.json |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Requirements | .planning/REQUIREMENTS.md |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

- [Phase 43]: Game-level constraints SKIP for default — MAE 4.91->5.12 worse, bias improved. Stays opt-in.
- [Phase 44]: Dual-path architecture — Neo4j for graph queries, pure-pandas fallback when unavailable
- [Phase 45]: PBP participation stored separately to avoid breaking existing PBP consumers
- [Phase 46]: Only 4/22 graph features had data — PBP participation ingestion is the blocker
- [Phase 47]: Scheme features are RB-only (NaN for other positions)
- [Phase 48]: Kicker projections opt-in via --include-kickers flag
- [Phase 49]: 2016-2019 participation data sparse — 2020-2025 sufficient for training
- [Phase 50]: cb_cooccurrence_quality, te_red_zone_target_share, rb_ypc_delta_backup_ol always NaN
- [Phase 51]: Graph features have real SHAP importance but cannot beat heuristic for RB/WR/TE
- [Phase 52]: Kicker MAE 4.14 worse than flat 8.0 baseline — kickers are near-random
- [Phase 53]: Hybrid residual SHIPS for WR/TE; heuristic weight tuning further improves MAE

### Research Flags

- PBP participation data ~10GB for 2016-2025 — storage consideration
- PFF paid data ($300-500/season) could dramatically improve WR-CB and OL quality features
- Football Outsiders adjusted line yards as cheaper OL quality proxy
- Full-feature residual (466 features) could unlock 22% WR improvement but needs unified evaluation pipeline

### Blockers/Concerns

- None — milestone complete

## Session Continuity

Last session: 2026-04-02
Stopped at: Milestone v3.1 complete
Resume file: None

---
*Last updated: 2026-04-02 — v3.1 milestone complete*
