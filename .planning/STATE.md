---
gsd_state_version: 1.0
milestone: v7.2
milestone_name: Data + Site Polish
status: roadmap-created
stopped_at: v7.2 roadmap created 2026-04-27. 9 phases (76-84) covering 23 requirements across 8 categories. Awaiting phase planning.
last_updated: "2026-04-27T19:00:00Z"
last_activity: 2026-04-27
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-24 after v7.1 Draft Season Readiness started)

**Core value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now with a production website + AI advisor ecosystem.
**Current focus:** v7.2 Data + Site Polish — roadmap created; awaiting phase planning.

## Current Position

Phase: Not started (Phase 76 next)
Plan: —
Status: Roadmap created — 9 phases (76-84) covering 23 requirements
Last activity: 2026-04-27 — v7.2 roadmap committed

**Mode:** "Tighten each theme" — every requirement cut to its smallest defensible scope. Critical path is 79→84 (deploy hardening) and 82→83 (advisor auth-aware tool); everything else parallelizes.

## Milestone Goal

Tighten what's already shipped — close half-done flows, kill tech debt, and lock in production reliability so v8.0 (PFF) can build on a clean foundation.

## Phase Breakdown (v7.2)

| Phase | Name | Requirements | Success Criteria | Depends on |
|-------|------|--------------|------------------|------------|
| 76 | AWS Refresh + S3 Sync | 3 (AWS-01..03) | 3 | — |
| 77 | Sentiment Source Expansion | 3 (INGEST-01..03) | 3 | — |
| 78 | Heuristic Consolidation | 3 (HEUR-01..03) | 3 | — |
| 79 | Audit Provenance + Live Version Probe | 2 (DQ-01, DQ-02) | 3 | — |
| 80 | Sanity Warning Triage | 1 (DQ-03) | 4 | — |
| 81 | Dashboard Feature Audit | 2 (UX-01, UX-02) | 3 | — |
| 82 | Sleeper OAuth + Multi-User | 3 (AUTH-01..03) | 3 | — |
| 83 | Advisor Tool Expansion | 3 (TOOL-01..03) | 3 | 82 |
| 84 | Deploy Hardening | 4 (DEPLOY-01..04) | 4 | 79 |

**Coverage:** 23/23 v7.2 requirements mapped, 0 orphans.

**Execution order:**
- Phases 76, 77, 78, 79, 80, 81, 82 can run in parallel.
- Phase 83 starts after Phase 82 (TOOL-03 needs auth-aware session).
- Phase 84 starts after Phase 79 (DEPLOY-02 + DEPLOY-04 consume `/api/version` + `script_sha`).

## Accumulated Context

Carried forward from v7.1 (shipped 2026-04-26):

- Frontend LIVE: https://frontend-jet-seven-33.vercel.app
- Backend LIVE: https://nfldataengineering-production.up.railway.app
- Daily cron: `0 12 * * *` UTC; LLM-primary extraction active when `ENABLE_LLM_ENRICHMENT=true`
- New cron: `weekly-external-projections.yml` Tuesdays 14:00 UTC + Sundays 12:00 UTC
- Sleeper integration: `/dashboard/leagues` username connect + `getUserRoster` advisor tool
- Tests: ~1634 passing
- 3-week deploy freeze closed 2026-04-27 with 6 root-cause fixes; gate now end-to-end green

### Decisions (v7.2 provisional)

- [v7.2]: Milestone themed "Data + Site Polish" — pre-v8.0 foundation tightening, not feature expansion
- [v7.2]: 9 phases (76-84) chosen over 10 because most categories are single-PR; only DQ split into two (DQ-01/02 critical-path vs DQ-03 triage)
- [v7.2]: UX-01 + UX-02 kept as one phase (Phase 81) — same per-route walk methodology, share screenshot setup
- [v7.2]: Critical path 79→84 (deploy hardening consumes Phase 79 outputs) and 82→83 (advisor auth-aware tool consumes Phase 82 session)
- [v7.2]: Marketing & Content (Remotion/NotebookLM) deferred to a separate post-v7.2 milestone — production hardening takes priority

### Pending Todos

- Plan Phase 76 (or any of 76, 77, 78, 79, 80, 81, 82 — all independent starts)
- Phase 73 EXTP-05 first cron observation (Tuesday 14:00 UTC + Sunday 12:00 UTC) — closes naturally during v7.2

### Blockers/Concerns

- AWS credentials still expired (Phase 76 unblocks)
- ANTHROPIC_API_KEY GitHub Secret + ENABLE_LLM_ENRICHMENT GitHub Variable assumed live (set during v7.0/v7.1 close-out)
- W1-2026 sanity-threshold restore (`_NEWS_CONTENT_MIN_TEAMS_OK 10→20`) is a pre-season-kickoff checklist item, not a phase

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Data     | PFF paid data integration | v8.0 | v4.1 |
| Data     | Neo4j Aura cloud graph setup | v8.0 | v4.1 |
| Content  | Marketing (Remotion, NotebookLM, social video) | post-v7.2 separate milestone | v7.2 (2026-04-27) |
| Models   | Heuristic consolidation (3 duplicate functions) | v7.2 Phase 78 | v6.0 |
| Models   | Unified evaluation pipeline (466-feature residual) | v7.3+ | v4.1 |
| Models   | QB heuristic -2.47 bias fix | v7.2 Phase 78 (HEUR-03 regression test) | v4.1 |
| Data     | Refresh AWS credentials + S3 sync | v7.2 Phase 76 | v4.0 |
| Auth     | Multi-user persistence (beyond session) | v7.2 Phase 82 | 2026-04-24 |
| Auth     | Cookie-based `sleeper_user_id` phase-out + deletion | v7.3 | v7.2 (2026-04-27) |
| Sentiment| Twitter/X sentiment ingestion | v7.3+ | v7.2 (2026-04-27) |
| Sentiment| ESPN Insider/CBS HQ paid sentiment sources | TBD (subscription cost evaluation) | v7.2 (2026-04-27) |

## Session Continuity

Last session: 2026-04-27
Stopped at: v7.2 roadmap created. 9 phases (76-84) covering 23 requirements across 8 categories. Critical path is 79→84 and 82→83; 7 phases parallelizable from start.
Resume with: `/gsd:plan-phase 76` (or any of 76, 77, 78, 79, 80, 81, 82 — all independent starts).
Resume file: `.planning/milestones/v7.2-ROADMAP.md`

### Deferred follow-ups (post-v7.2)

- Cookie-based `sleeper_user_id` phase-out + deletion (deferred from AUTH-03 backwards-compat path)
- Twitter/X sentiment ingestion (rate-limit complexity)
- ESPN Insider/CBS HQ paid sentiment sources (subscription cost evaluation)
- Full UX redesign of any individual dashboard page (Phase 81 is gap closure only, not redesign)
- Per-user advisor history persistence beyond current `usePersistentChat` localStorage
- Cloud-side audit running on S3-backed Silver instead of local-FS-backed (deferred until AWS sync stabilizes — Phase 76)
- Marketing & content automation (Remotion, NotebookLM, social distribution) — separate post-v7.2 milestone
