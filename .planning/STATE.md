---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Silver Expansion
status: executing
stopped_at: Completed 18-01-PLAN.md
last_updated: "2026-03-15T21:16:03.740Z"
last_activity: 2026-03-15 — Completed 18-01 historical profiles compute module (8 functions, 15 tests)
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 9
  completed_plans: 8
  percent: 89
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** A rich NFL data lake powering both fantasy football projections and game outcome predictions
**Current focus:** Phase 18 — Historical Context

## Current Milestone

v1.2 Silver Expansion — Expand Silver layer with PBP team metrics, tendencies, situational breakdowns, advanced player profiles, strength of schedule, and historical context using rolling windows.

## Current Position

Phase: 18 of 18 (Historical Context) — 4 of 4 in milestone
Plan: 1 of 2 complete in current phase
Status: In Progress
Last activity: 2026-03-15 — Completed 18-01 historical profiles compute module (8 functions, 15 tests)

Progress: [█████████░] 89% (18-01 complete, 18-02 remaining)

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
- [17-01]: Generic _compute_profile helper DRYs up 6 NGS/PFR/QBR compute functions
- [17-01]: Player rolling uses min_periods=3 (stricter than team min_periods=1) per success criteria
- [17-01]: PFR team blitz rate reuses apply_team_rolling from team_analytics (team-level groupby)
- [17-02]: Synthetic player_gsis_id from name+team enables PFR/QBR rolling despite missing GSIS IDs
- [17-02]: Three-tier join: GSIS ID (NGS), normalized name+team (PFR/QBR), team-only (PFR blitz)
- [17-02]: Overlap detection before merge prevents pandas _x/_y suffix columns across NGS sources
- [18-01]: NaN propagation for all composite scores -- no imputation or fill
- [18-01]: Catch radius proxy uses raw height_inches (simplest meaningful proxy)
- [18-01]: Compensatory picks 225-262 use linear extrapolation with 0.042/pick decay and 0.4 floor
- [Phase 18]: NaN propagation for all composite scores -- no imputation

### Pending Todos

None.

### Blockers/Concerns

- PFR player ID match rate (~80% estimated) needs validation before Phase 17
- NGS weekly qualification thresholds need Bronze data inspection before Phase 17
- Schedules Bronze covers 2020-2025 only; situational splits limited to that range

## Session Continuity

Last session: 2026-03-15T21:16:03.738Z
Stopped at: Completed 18-01-PLAN.md
Resume file: None

---
*Last updated: 2026-03-15 after 18-01 plan execution*
