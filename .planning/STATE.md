---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Prediction Data Foundation
status: unknown
stopped_at: Completed 23-02-PLAN.md
last_updated: "2026-03-19T01:39:23.687Z"
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 9
  completed_plans: 9
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-15)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 23 — cross-source-features-and-integration

## Current Milestone

v1.3 Prediction Data Foundation — Ready to plan Phase 20

## Current Position

Phase: 23 (cross-source-features-and-integration) — COMPLETE
Plan: 2 of 2 (all plans complete)

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
| v1.2 Archive | .planning/milestones/v1.2-* |
| Codebase Map | .planning/codebase/ |

## Accumulated Context

### Decisions

Carried from v1.2. See PROJECT.md Key Decisions table.

- **Phase 20-01**: Officials season range starts at 2015 (nflverse confirmed coverage)
- **Phase 20-01**: PBP expanded to 140 columns (37 new: penalty, ST, fumble recovery, drive detail)
- **Phase 20-01**: Stadium coordinates include 6 international venues
- **Phase 20-02**: PBP re-ingested for 2016-2025 with 140-column schema (was 103)
- **Phase 20-02**: Officials data ingested for 2016-2025 (~1,900 rows/season, 7 crew positions)
- **Phase 20-02**: 302 tests pass with zero regressions after data expansion
- [Phase 21]: Touchback proxy: KO uses return_yards==0 + kickoff_returner_player_id IS NULL; punt uses punt_in_endzone==1
- [Phase 21]: FG buckets use kick_distance with NFL-standard <30/30-39/40-49/50+ split
- [Phase 21]: Added _filter_st_plays helper (Plan 01 dep) as Rule 3 auto-fix in Plan 02
- **Phase 21-01**: Penalty metrics use penalty==1 flag with penalty_team off/def split
- **Phase 21-01**: Turnover luck uses expanding window with shift(1) lag, not rolling
- **Phase 21-01**: is_turnover_lucky threshold: >0.60=lucky, <0.40=unlucky
- **Phase 21-03**: Turnover luck columns excluded from rolling windows (uses expanding window internally)
- **Phase 21-03**: compute_pbp_derived_metrics orchestrator merges 11 functions following compute_pbp_metrics pattern
- **Phase 22-01**: STADIUM_ID_COORDS uses actual Bronze data IDs (15 differed from research estimates)
- **Phase 22-01**: Arizona timezone: 0h diff in summer (both UTC-7), 1h in winter (AZ stays UTC-7, LA falls to UTC-8)
- **Phase 22-01**: LON01 = Twickenham Stadium (not Wembley alt) per actual data
- **Phase 22-02**: Fixed game_context.py import from src.config to config (consistent with other src/ modules)
- **Phase 22-02**: OAK/SD travel NaN expected for pre-relocation team codes (2016-2019)
- [Phase 22]: Fixed game_context.py import from src.config to config (consistent with other src/ modules)
- [Phase 23]: Division rank uses (win_pct desc, wins desc) sort for tiebreaking
- [Phase 23]: Games behind uses straight win difference (football convention, not baseball half-game)
- [Phase 23]: Referee penalty rate: game-level sum (both teams), expanding mean per referee-season with shift(1)
- [Phase 23]: Feature vector assembles to 337 columns via left joins on [team, season, week]
- [Phase 23]: Null policy: Week 1 rolling columns NaN allowed; core cols non-null week 2+

### Pending Todos

None.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-19T01:35:08Z
Stopped at: Completed 23-02-PLAN.md
Resume file: None

---
*Last updated: 2026-03-15 after v1.3 roadmap created*
