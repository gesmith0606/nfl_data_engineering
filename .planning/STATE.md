---
gsd_state_version: 1.0
milestone: v7.0
milestone_name: Production Stabilization
status: defining_requirements
started_at: "2026-04-21"
last_updated: "2026-04-21T00:00:00Z"
last_activity: 2026-04-21
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
previous_milestone: v6.0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-21 after v7.0 Production Stabilization started)

**Core value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now delivered to end users via a production website that must work reliably.
**Current focus:** v7.0 Production Stabilization — fix 6 regressions found in 2026-04-20 user audit, close sanity-check blindspots

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-04-21 — Milestone v7.0 started

## Production Audit Findings (2026-04-20)

User audit of https://frontend-jet-seven-33.vercel.app surfaced 6 regressions:

| # | Issue | Root Cause | Affected |
|---|-------|------------|----------|
| 1 | Kyler Murray still on Cardinals | `refresh_rosters.py` skips `team=null` (released); writes only to Gold preseason, not Bronze rosters | Roster data |
| 2 | Predictions page broken | Frontend omits `season`/`week` → backend 422 | `/api/predictions` |
| 3 | Lineups page broken | Same 422 pattern + Railway Docker image missing `data/bronze/schedules/` | `/api/lineups`, `/api/teams/*/roster` |
| 4 | Matchups page partial | Railway missing Bronze schedules → 503 on `/api/teams/current-week` | Matchup view |
| 5 | News no context | `ANTHROPIC_API_KEY` unset on Railway → extractor never ran → `event_flags:[]`, `sentiment:null` across all 32 teams | `/api/news/team-events`, `/api/news/feed` |
| 6 | Advisor news access | **FALSE alarm** — 4/12 tools exist (`getNewsFeed`, `getPlayerNews`, `getTeamSentiment`, `getSentimentSummary`); WARN because #5 data empty | AI advisor audit |

**Meta-issue:** Sanity-check script (Phase 60) passed exit 0 through all of this because:
- Deploy gate never ran `--check-live` (smoke is annotation-only, post-deploy)
- Payload validator checks `len(data) == 32` only — empty rows pass
- Never probes `/api/predictions`, `/api/lineups`, `/api/teams/*/roster`
- No roster drift check against Sleeper canonical
- No check that news extractor recently ran / API key set

## Accumulated Context

Carried forward from v6.0:

- Frontend LIVE: https://frontend-jet-seven-33.vercel.app (Next.js on Vercel)
- Backend LIVE: https://nfldataengineering-production.up.railway.app (FastAPI on Railway, Parquet fallback)
- Advisor TOOL_REGISTRY: 12 tools (`scripts/audit_advisor_tools.py:223`)
- Design tokens (`tokens.css` + `design-tokens.ts`) + 5 motion primitives consumed by shell + 11 pages
- CI gate: `scripts/sanity_check_projections.py` runs in deploy-web.yml; `--check-live` used post-deploy only (non-blocking)
- Daily cron: `0 12 * * *` UTC runs 5-source news pipeline + refresh_rosters.py in daily-sentiment.yml
- Tests: 1379+ passing

### Decisions (v7.0 provisional)

- [v7.0]: Defer marketing/content + Sleeper league integration + external projections comparison to v7.1+ — foundational stability first
- [v7.0]: DQAL-03 rolled into Phase 3 (SANITY) — roster drift + rookie ingest + rank recalibration become sanity-check coverage, not standalone cleanup
- [v7.0]: Advisor news access issue is a FALSE alarm — tools exist, fix #5 (extractor) resolves it
- [v7.0]: Sanity-check v2 (Phase 3) is the structural fix — if the gate doesn't see failures, every future deploy has the same blind spot

### Pending Todos

None yet.

### Blockers/Concerns

- ANTHROPIC_API_KEY still not set on Railway — blocks sentiment backfill (Phase 4 depends on it)
- Railway Docker image `data/` contents need verification — `data/bronze/schedules/` and `data/bronze/players/rosters/` known missing

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Data     | 61-03 event-adjustment activation | Awaiting Bronze event accumulation (0/48 weeks) | v6.0 |
| Models   | Heuristic consolidation (3 duplicate functions) | v7.3 | v6.0 |
| Models   | Unified evaluation pipeline (466-feature residual) | v7.3+ | v4.1 |
| Models   | QB heuristic -2.47 bias fix | Acknowledged | v4.1 |
| Data     | PFF paid data integration | v8.0 | v4.1 |
| Frontend | External projections comparison (ESPN/Sleeper/Yahoo) | v7.1 — new | 2026-04-21 |
| Frontend | Sleeper league integration | v7.1 | v6.0 |
| Content  | Marketing (Remotion, social video, NotebookLM) | v7.2 | v6.0 |
| Infra    | Refresh AWS credentials + S3 sync | Expired March 2026 | v4.0 |

## Session Continuity

Last session: 2026-04-21
Stopped at: Defining v7.0 requirements — proceeding with REQUIREMENTS.md write
Resume file: None
