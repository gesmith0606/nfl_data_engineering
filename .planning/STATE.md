---
gsd_state_version: 1.0
milestone: v7.0
milestone_name: Production Stabilization
status: executing
started_at: "2026-04-21"
last_updated: "2026-04-22T00:00:00Z"
last_activity: 2026-04-22
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 8
  completed_plans: 8
  percent: 40
previous_milestone: v6.0
next_phase: 68
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-21 after v7.0 Production Stabilization started)

**Core value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now delivered to end users via a production website that must work reliably.
**Current focus:** v7.0 Production Stabilization — fix 6 regressions found in 2026-04-20 user audit, close sanity-check blindspots

## Current Position

Phase: 68 — Sanity-Check v2 (next)
Plan: —
Status: Phase 66 + 67 complete (code). Both in `human_needed` pending external actions (Railway env var + daily-cron run). Checkpoint taken before Phase 68.
Last activity: 2026-04-22 — Phase 67 commits landed locally, tests green, VERIFICATION.md written

**Execution order:** 66 ✓ → (67 ✓ ∥ 68 next ∥ 69) → 70

Progress: 2/5 phases complete code-side (40%)
[████████░░░░░░░░░░░░] 40%

### Phase 66 Status — human_needed

Commits: `9853067` (CONTEXT) → `c4c1640` (Dockerfile) → `0782870` (backend defaulting + /api/health flag) → `1cf224e` (frontend hook) → `12fc9e6` (docs).

External actions pending from user:
1. `git push origin main` (Railway auto-deploys on push)
2. Set `ANTHROPIC_API_KEY` in Railway Variables tab
3. Run 6 verification curls from `.planning/phases/66-p0-deployment-hotfixes/66-VERIFICATION.md`

Tests: 44/44 web tests pass (32 existing + 12 new in `tests/web/test_graceful_defaulting.py`).

### Phase 67 Status — human_needed

Commits: `5fd1b65` (refresh_rosters v2) → `bfd30c1` (team_roster_service live-first) → `f09f57f` (daily cron harden + artifacts) → `7a4a740` (11 tests + docs).

External actions pending:
1. Daily cron run on GitHub Actions (or manual trigger via `gh workflow run daily-sentiment.yml -f season=2026`)
2. Kyler Murray acceptance canary — confirm `/api/teams/ARI/roster` matches his Sleeper truth after cron landed

Tests: 11 new in `tests/test_refresh_rosters_v2.py` covering FA handling, change-type classifier, Bronze live write. All pass.

## Production Audit Findings (2026-04-20)

User audit of https://frontend-jet-seven-33.vercel.app surfaced 6 regressions:

| # | Issue | Root Cause | Affected | v7.0 Phase |
|---|-------|------------|----------|------------|
| 1 | Kyler Murray still on Cardinals | `refresh_rosters.py` skips `team=null` (released); writes only to Gold preseason, not Bronze rosters | Roster data | 67 |
| 2 | Predictions page broken | Frontend omits `season`/`week` → backend 422 | `/api/predictions` | 66 |
| 3 | Lineups page broken | Same 422 pattern + Railway Docker image missing `data/bronze/schedules/` | `/api/lineups`, `/api/teams/*/roster` | 66 |
| 4 | Matchups page partial | Railway missing Bronze schedules → 503 on `/api/teams/current-week` | Matchup view | 66 |
| 5 | News no context | `ANTHROPIC_API_KEY` unset on Railway → extractor never ran → `event_flags:[]`, `sentiment:null` across all 32 teams | `/api/news/team-events`, `/api/news/feed` | 66 + 69 |
| 6 | Advisor news access | **FALSE alarm** — 4/12 tools exist (`getNewsFeed`, `getPlayerNews`, `getTeamSentiment`, `getSentimentSummary`); WARN because #5 data empty | AI advisor audit | 69 (resolves when #5 lands) |

**Meta-issue (Phase 68):** Sanity-check script (Phase 60) passed exit 0 through all of this because:
- Deploy gate never ran `--check-live` as blocking (smoke is annotation-only, post-deploy)
- Payload validator checks `len(data) == 32` only — empty rows pass
- Never probes `/api/predictions`, `/api/lineups`, `/api/teams/*/roster`
- No roster drift check against Sleeper canonical
- No check that news extractor recently ran / API key set

Phase 68 is the structural fix — the gate is what lets every future regression ship.

## Phase Breakdown (v7.0)

| Phase | Name | Requirements | Success Criteria | Depends on |
|-------|------|--------------|------------------|------------|
| 66 | P0 Deployment Hotfixes | 6 (HOTFIX-01..06) | 6 | — |
| 67 | Roster Refresh v2 | 6 (ROSTER-01..06) | 6 | — (parallel) |
| 68 | Sanity-Check v2 | 10 (SANITY-01..10) | 6 | — (parallel) |
| 69 | Sentiment Backfill | 5 (SENT-01..05) | 5 | 66 |
| 70 | Frontend Empty/Error States | 5 (FE-01..05) | 5 | 66, partially 69 |

**Coverage:** 32/32 v7.0 requirements mapped, 0 orphans.

## Accumulated Context

Carried forward from v6.0:

- Frontend LIVE: https://frontend-jet-seven-33.vercel.app (Next.js on Vercel)
- Backend LIVE: https://nfldataengineering-production.up.railway.app (FastAPI on Railway, Parquet fallback)
- Advisor TOOL_REGISTRY: 12 tools (`scripts/audit_advisor_tools.py:223`)
- Design tokens (`tokens.css` + `design-tokens.ts`) + 5 motion primitives consumed by shell + 11 pages
- CI gate: `scripts/sanity_check_projections.py` runs in deploy-web.yml; `--check-live` used post-deploy only (non-blocking) — Phase 68 fixes this
- Daily cron: `0 12 * * *` UTC runs 5-source news pipeline + refresh_rosters.py in daily-sentiment.yml
- Tests: 1379+ passing

### Decisions (v7.0 provisional)

- [v7.0]: Defer marketing/content + Sleeper league integration + external projections comparison to v7.1+ — foundational stability first
- [v7.0]: DQAL-03 rolled into Phase 68 (SANITY) — roster drift + rookie ingest + rank recalibration become sanity-check coverage, not standalone cleanup (absorbed via SANITY-10)
- [v7.0]: Advisor news access issue is a FALSE alarm — tools exist, fix Phase 69 (extractor) resolves it
- [v7.0]: Sanity-check v2 (Phase 68) is the structural fix — if the gate doesn't see failures, every future deploy has the same blind spot
- [v7.0]: Execution order 66 → (67 ∥ 68 ∥ 69) → 70 — 66 is the critical path, 67/68/69 run parallel after, 70 benefits from all upstream data being correct

### Pending Todos

None yet. Ready to invoke `/gsd:plan-phase 66` to break Phase 66 into plans.

### Blockers/Concerns

- ANTHROPIC_API_KEY still not set on Railway — blocks sentiment backfill (Phase 69 depends on it via HOTFIX-01 in Phase 66)
- Railway Docker image `data/` contents need verification — `data/bronze/schedules/` and `data/bronze/players/rosters/` known missing (HOTFIX-02/03 in Phase 66)

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

Last session: 2026-04-22
Stopped at: Phase 66 + 67 code complete (8 commits `ae38416..7a4a740`). Both in human_needed awaiting Railway env var + daily-cron run. Checkpointed before Phase 68 (sanity-check v2, largest phase at 10 reqs). Resume with `/gsd:autonomous --from 68` after Railway actions land.
Resume file: None
