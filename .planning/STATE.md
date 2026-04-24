---
gsd_state_version: 1.0
milestone: v7.1
milestone_name: Draft Season Readiness
status: requirements_defined
started_at: "2026-04-24"
last_updated: "2026-04-24T00:00:00Z"
last_activity: 2026-04-24
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
previous_milestone: v7.0
next_phase: 71
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-24 after v7.1 Draft Season Readiness started)

**Core value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now with a production website + AI advisor ecosystem.
**Current focus:** v7.1 Draft Season Readiness — LLM-primary extraction, external projections comparison, Sleeper league integration, v7.0 tech debt cleanup.

## Current Position

Phase: 71 — LLM-Primary Extraction (next; ready for plan-phase)
Plan: —
Status: v7.0 archived (`v7.0` tag on origin). v7.1 requirements + roadmap committed. Ready to `/gsd:plan-phase 71` or `/gsd:autonomous --from 71` to kick off execution.
Last activity: 2026-04-24 — v7.1 milestone structure created

**Execution order (proposed):** 71 → 72 (depends on 71) → (73 ∥ 74 ∥ 75 parallel) → milestone close

Progress: 0/5 phases (0%)
[░░░░░░░░░░░░░░░░░░░░] 0%

## Milestone Goal

Deliver draft-season-critical features before fantasy draft season opens:
- LLM-primary sentiment extraction (so offseason news produces real signals)
- External projections comparison (ESPN/Sleeper/Yahoo side-by-side)
- Sleeper league integration (personalized rosters + advisor)
- v7.0 tech debt cleanup (8 items)

## Phase Breakdown (v7.1)

| Phase | Name | Requirements | Success Criteria | Depends on |
|-------|------|--------------|------------------|------------|
| 71 | LLM-Primary Extraction | 5 (LLM-01..05) | 5 | — |
| 72 | Event Flag Expansion + Non-Player Attribution | 5 (EVT-01..05) | 5 | 71 |
| 73 | External Projections Comparison | 5 (EXTP-01..05) | 5 | — (parallel) |
| 74 | Sleeper League Integration | 4 (SLEEP-01..04) | 4 | — (parallel) |
| 75 | v7.0 Tech Debt Cleanup | 8 (TD-01..08) | 7 | — (parallel) |

**Coverage:** 27/27 v7.1 requirements mapped, 0 orphans.

## Accumulated Context

Carried forward from v7.0 (shipped 2026-04-24):

- Frontend LIVE: https://frontend-jet-seven-33.vercel.app (Next.js on Vercel, EmptyState + data_as_of chips on 4 pages)
- Backend LIVE: https://nfldataengineering-production.up.railway.app (FastAPI on Railway, graceful defaulting on predictions/lineups/roster)
- Daily cron: `0 12 * * *` UTC runs sentiment + roster refresh; `permissions: contents: write, issues: write`; decoupled roster refresh season=2026
- Sanity gate: `scripts/sanity_check_projections.py --check-live` promoted to blocking GHA step; `auto-rollback` job live (5-min window, no force-push, audit commit format)
- Bronze player rosters + depth_charts now version-controlled (committed 2026-04-24) — fixes PlayerNameResolver on CI runner
- ANTHROPIC_API_KEY set on Railway env + GitHub Secret; ENABLE_LLM_ENRICHMENT GitHub Variable set to true
- Phase 69 extraction confirmed running end-to-end: LLM enrichment path writes to `data/silver/sentiment/signals_enriched/`; but RuleExtractor is still primary and produces 0 signals on offseason content — this is the core problem v7.1 solves with Phase 71
- Tests: 1469+ passing

### Decisions (v7.1 provisional)

- [v7.1]: Milestone themed "Draft Season Readiness" — narrative cohesion around fantasy draft preparation
- [v7.1]: LLM-primary extraction is P1 (Phase 71) — primary driver for the milestone; unblocks real offseason signal
- [v7.1]: Keep RuleExtractor as fallback path for zero-cost dev + API outages (do not delete it)
- [v7.1]: Phase 72 event flag expansion depends on Phase 71 (Claude is the producer of new flags)
- [v7.1]: Phases 73 (external projections) + 74 (Sleeper league) + 75 (tech debt) run in parallel after 71-72

### Pending Todos

None yet. Ready to invoke `/gsd:plan-phase 71` to break Phase 71 into plans.

### Blockers/Concerns

- Pending v7.0 external ops (carried forward) — do NOT block v7.1 but should be observed:
  - Railway /api/health not showing `llm_enrichment_ready` flag (suggests Railway hasn't redeployed with Phase 66 code OR CDN caching)
  - `/api/news/team-events` returns empty `[]` instead of 32 zero-filled rows — potentially a separate bug worth a ticket
  - Daily cron observation for Kyler Murray canary (ROSTER-05)
  - Live rollback proof on first real regression (SANITY-09)

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Data     | PFF paid data integration | v8.0 | v4.1 |
| Data     | Neo4j Aura cloud graph setup | v8.0 | v4.1 |
| Content  | Marketing (Remotion, NotebookLM, social video) | v7.2 | v6.0 |
| Models   | Heuristic consolidation (3 duplicate functions) | v7.3 | v6.0 |
| Models   | Unified evaluation pipeline (466-feature residual) | v7.3+ | v4.1 |
| Models   | QB heuristic -2.47 bias fix | Acknowledged | v4.1 |
| Data     | Refresh AWS credentials + S3 sync | Expired March 2026 | v4.0 |
| Auth     | Multi-user persistence (beyond session) | v7.2 or v7.3 | 2026-04-24 |

## Session Continuity

Last session: 2026-04-24
Stopped at: v7.1 milestone structure committed; 27 requirements mapped across 5 phases; ready for Phase 71 plan.
Resume with: `/gsd:plan-phase 71` (or `/gsd:autonomous --from 71` for full autonomous run).
Resume file: None
