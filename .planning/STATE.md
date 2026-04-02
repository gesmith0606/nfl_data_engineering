---
gsd_state_version: 1.0
milestone: v3.1
milestone_name: Graph-Enhanced Fantasy Projections
status: defining_requirements
stopped_at: null
last_updated: "2026-04-02T00:00:00.000Z"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-02)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** v3.1 — Graph-Enhanced Fantasy Projections

## Current Milestone

v3.1 Graph-Enhanced Fantasy Projections

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-04-02 — Milestone v3.1 started

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

- [Phase 43]: Game-level constraints SKIP for default — MAE 4.91→5.12 worse, bias improved. Stays opt-in.
- [Phase 44]: Dual-path architecture — Neo4j for graph queries, pure-pandas fallback when unavailable
- [Phase 45]: PBP participation stored separately to avoid breaking existing PBP consumers
- [Phase 46]: Only 4/22 graph features had data — PBP participation ingestion is the blocker
- [Phase 47]: Scheme features are RB-only (NaN for other positions)
- [Phase 48]: Kicker projections opt-in via --include-kickers flag

### Research Flags

- PBP participation data ~10GB for 2016-2025 — storage consideration
- PFF paid data ($300-500/season) could dramatically improve WR-CB and OL quality features
- Football Outsiders adjusted line yards as cheaper OL quality proxy

### Blockers/Concerns

- PBP participation ingestion in progress (running now)
- 2025 holdout has no injury Bronze data — graph features NaN there

## Session Continuity

Last session: 2026-04-02
Stopped at: Milestone v3.1 initialization
Resume file: None

---
*Last updated: 2026-04-02 — v3.1 milestone started*
