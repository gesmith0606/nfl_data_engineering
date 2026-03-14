---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Silver Expansion
status: executing
stopped_at: Completed 16-02-PLAN.md
last_updated: "2026-03-14T18:55:38.086Z"
last_activity: 2026-03-14 — Completed 16-02 situational splits (home/away, divisional, game script EPA splits + CLI wiring)
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 5
  completed_plans: 5
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** A rich NFL data lake powering both fantasy football projections and game outcome predictions
**Current focus:** Phase 16 — Strength of Schedule and Situational Splits

## Current Milestone

v1.2 Silver Expansion — Expand Silver layer with PBP team metrics, tendencies, situational breakdowns, advanced player profiles, strength of schedule, and historical context using rolling windows.

## Current Position

Phase: 16 of 18 (Strength of Schedule and Situational Splits) — 2 of 4 in milestone
Plan: 2 of 2 complete in current phase (Phase 16 COMPLETE)
Status: Phase Complete
Last activity: 2026-03-14 — Completed 16-02 situational splits (home/away, divisional, game script EPA splits + CLI wiring)

Progress: [██████████] 100% (16-01 + 16-02 complete)

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Config | .planning/config.json |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Requirements | .planning/REQUIREMENTS.md |
| Research | .planning/research/SUMMARY.md |
| v1.0 Archive | .planning/milestones/v1.0-* |
| v1.1 Archive | .planning/milestones/v1.1-* |
| Codebase Map | .planning/codebase/ |

## Accumulated Context

### Decisions

- [v1.2]: Rolling windows group by (entity, season) — fix existing bug in Phase 15
- [v1.2]: New Silver modules separate from existing player_analytics.py — protect test suite
- [v1.2]: SOS uses lagged (week N-1) opponent strength only — avoid circular dependency
- [v1.2]: Combine/draft stored as static dimension table — avoid row explosion
- [15-01]: Rolling window groupby uses [entity, season] tuple — prevents cross-season contamination
- [15-01]: team_analytics.py mirrors player_analytics.py rolling pattern with [team, season] groupby
- [Phase 15]: Red zone TD rate uses nunique(drive) denominator, not play count
- [Phase 15]: CPOE is offense-only metric -- no defensive CPOE column
- [15-03]: 4th down aggressiveness accepts raw PBP to include punt/FG in denominator
- [15-03]: PROE uses pandas mean() for xpass auto-NaN-exclusion
- [16-01]: SOS uses per-game opponent EPA from specific week faced, not cumulative season-to-date
- [16-01]: Bye weeks produce no row in SOS output (skip, not NaN fill)
- [16-01]: SOS rankings use ascending=False, method=min (rank 1 = hardest schedule)
- [Phase 16]: SOS uses per-game opponent EPA from specific week faced, not cumulative season-to-date
- [Phase 16]: Game script uses 7-point threshold: leading >= 7, trailing <= -7, neutral excluded
- [Phase 16]: Situational splits pivot to wide format before rolling to avoid cross-situation contamination

### Pending Todos

None.

### Blockers/Concerns

- PFR player ID match rate (~80% estimated) needs validation before Phase 17
- NGS weekly qualification thresholds need Bronze data inspection before Phase 17
- Schedules Bronze covers 2020-2025 only; situational splits limited to that range

## Session Continuity

Last session: 2026-03-14T18:55:38.083Z
Stopped at: Completed 16-02-PLAN.md
Resume file: None

---
*Last updated: 2026-03-14 after 16-02 plan execution*
