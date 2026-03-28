---
gsd_state_version: 1.0
milestone: v2.2
milestone_name: Full Odds + Holdout Reset
status: ready_to_plan
stopped_at: Roadmap created, ready to plan Phase 35
last_updated: "2026-03-28T18:00:00.000Z"
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 7
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-28)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** v2.2 Phase 35 — Bronze Data Completion

## Current Milestone

v2.2 Full Odds + Holdout Reset — 4 phases (35-38), 7 plans

## Current Position

Phase: 35 (1 of 4 in v2.2) — Bronze Data Completion
Plan: 0 of 2 in current phase
Status: Ready to plan
Last activity: 2026-03-28 — Roadmap created

Progress: [░░░░░░░░░░] 0% (0/7 plans)

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Config | .planning/config.json |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Requirements | .planning/REQUIREMENTS.md |
| Research | .planning/research/SUMMARY.md |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.
Recent decisions affecting v2.2:
- [v2.1]: Opening lines only in _PRE_GAME_CONTEXT; closing-line features excluded
- [v2.1]: Ship market features only if holdout ATS improves (strict >)
- [v2.1]: FinnedAI covers 2016-2021 only; market features NaN for 2022-2024

### Research Flags

- Phase 35: Verify 2025 nfl-data-py coverage (smoke test: 285+ games)
- Phase 35: Verify nflverse schedules schema for 2022+ (spread_line, total_line)
- Fallback: If 2025 incomplete, keep HOLDOUT_SEASON=2024 with expanded FinnedAI training

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-28
Stopped at: Roadmap created, ready to plan Phase 35
Resume file: None

---
*Last updated: 2026-03-28 after v2.2 roadmap creation*
