---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: Market Data
status: unknown
stopped_at: Completed 33-02-PLAN.md
last_updated: "2026-03-28T05:34:00.704Z"
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 33 — silver-line-movement-features

## Current Milestone

v2.1 Market Data -- historical odds, line movement features, CLV tracking

## Current Position

Phase: 34
Plan: Not started

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
- Ablation protocol: add candidate features, re-run selection, ship only if holdout improves
- Ensemble features loaded from metadata.json not config.py

v2.1 research findings:

- nflverse schedules already has closing lines (spread_line, total_line) with zero nulls
- SBRO XLSX archives (2016-2021) recommended for opening lines; only new dep is openpyxl
- Closing-line-derived features are retrospective-only (leakage if used in live predictions)
- Opening_spread and opening_total are the only market features safe for live prediction
- [Phase 32]: 45-entry hardcoded mapping dict for FinnedAI team names (not fuzzy matching)
- [Phase 32]: Sign convention: negate FinnedAI spreads to match nflverse positive=home favored
- [Phase 32]: Join by (season, home_team, gameday) since FinnedAI has no week column
- [Phase 32]: Implausible spread filter at |spread| > 25 drops corrupt FinnedAI entries
- [Phase 32]: Sign convention check uses < 0 (not <= 0) to allow pick'em opening lines
- [Phase 33]: Magnitude buckets encoded as ordinal float64 (0-3) for numeric dtype filter compatibility
- [Phase 33]: Directional features (spread) negated for away; symmetric features (totals, magnitude) identical for both teams
- [Phase 33]: Only opening_spread and opening_total added to _PRE_GAME_CONTEXT -- all closing/shift/magnitude features excluded as retrospective

### Pending Todos

None -- fresh milestone.

### Blockers/Concerns

- SBRO XLSX actual column names unverified -- must inspect real file before writing parser
- 2022-2024 has no free opening lines (CLV works all seasons; line movement trains on 2016-2021)
- SBRO site could go offline -- FinnedAI/sportsbookreview-scraper is backup

## Session Continuity

Last session: 2026-03-28T05:29:33.368Z
Stopped at: Completed 33-02-PLAN.md
Resume file: None

---
*Last updated: 2026-03-27 after v2.1 roadmap creation*
