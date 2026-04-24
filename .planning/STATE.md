---
gsd_state_version: 1.0
milestone: v7.1
milestone_name: Draft Season Readiness
status: executing
stopped_at: Phase 71 Plan 03 complete — batched Claude primary extractor with prompt caching shipped; LLM-03 benchmark passing at 5.57x; CostLog Parquet sink ready; HAIKU_4_5_RATES exported. Ready for Plan 71-04 (pipeline wiring).
last_updated: "2026-04-24T20:41:13.000Z"
last_activity: 2026-04-24 -- Phase 71 Plan 03 shipped (29 more tests added, 119 sentiment tests green; LLM-03 ratio=5.57x)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 5
  completed_plans: 3
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-24 after v7.1 Draft Season Readiness started)

**Core value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now with a production website + AI advisor ecosystem.
**Current focus:** Phase 71 — llm-primary-extraction

## Current Position

Phase: 71 (llm-primary-extraction) — EXECUTING
Plan: 4 of 5 (Plans 01, 02, 03 complete)
Status: Executing Phase 71
Last activity: 2026-04-24 -- Phase 71 Plan 03 shipped

**Execution order (proposed):** 71 → 72 (depends on 71) → (73 ∥ 74 ∥ 75 parallel) → milestone close

Progress: 3/5 plans in Phase 71 (60%)
[████████████░░░░░░░░] 60%

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
- [71-01]: ClaudeClient Protocol uses attribute-based shape (`messages: Any`), not a method, to match real `anthropic.Anthropic` SDK (`.messages.create(...)` chain)
- [71-01]: All schema extensions are additive with safe defaults — zero rename/remove, preserving every existing call site
- [71-01]: Extractor identity strings live as module-level constants (`_EXTRACTOR_NAME_*`) for single source of truth across Plans 71-02..05
- [71-02]: FakeClaudeClient uses typed dataclasses (not MagicMock) for response shape so tests catch SDK-surface drift at authoring time; satisfies runtime-checkable ClaudeClient Protocol via attribute-based duck typing
- [71-02]: `max_tokens` excluded from SHA computation — Anthropic caches by prompt, not output ceiling; inclusion would invalidate cached fixtures on unrelated tuning
- [71-02]: Fixture recording MUST use `roster_provider=lambda: []` — documented invariant in README.md; SHA otherwise drifts across machines/roster-parquet refreshes
- [71-02]: Placeholder SHAs suffixed per batch (`_PENDING_WAVE_2_SHA_w17`, `_w18`) to avoid dict-registry collision during the Wave-2 interim
- [71-03]: Prompt caching shape is a 2-element system list with `cache_control=ephemeral` on both the static prefix and `ACTIVE PLAYERS:` roster block; empty roster drops the second cached entry
- [71-03]: `_MAX_TOKENS_BATCH=4096` (vs single-doc 1024) to accommodate JSON array of 8-16 signals per batched call
- [71-03]: Parse errors inside `_parse_batch_response` are swallowed (return empty); only actual API errors from `_call_claude_batch` propagate so Plan 71-04 can catch them and fall back per-doc to RuleExtractor
- [71-03]: CostLog Parquet filenames embed `call_id` suffix (`llm_costs_{ts}_{call_id}.parquet`) so same-second concurrent writes don't collide
- [71-03]: `HAIKU_4_5_RATES` dict exported at module scope (input=$1, output=$5, cache_read=$0.10, cache_creation=$1.25 per 1M tokens) so Plan 71-05 can import directly for SUMMARY cost summary
- [71-03]: `_build_batched_prompt_for_sha` factored to module scope so tests + future fixture-recording scripts can compute `prompt_sha` without instantiating the extractor
- [71-03]: W17/W18 fixtures enriched to 78 signals per batch (4-6 per doc) to achieve LLM-03 5× gate against the noisy 28-signal RuleExtractor baseline on offseason content (ratio=5.57x)
- [71-03]: Real fixture `prompt_sha` values populated overwriting `_PENDING_WAVE_2_SHA_w17`/`_w18` placeholders (W17: `f59fdd9b...`, W18: `1c0e3e1a...`)

### Pending Todos

Plan 71-03 (batched Claude primary extractor) shipped. Next: Plan 71-04 — pipeline wiring (extractor_mode="claude_primary" routing in SentimentPipeline, per-doc soft fallback to RuleExtractor on API errors, non-player items persistence to data/silver/sentiment/non_player_pending/, PipelineResult counter bumps).

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
Stopped at: Phase 71 Plan 03 complete — batched Claude primary extractor with prompt caching, CostLog Parquet sink, deterministic SHA-keyed test replay, and LLM-03 5× benchmark (measured ratio=5.57x) shipped; 119 sentiment tests green. Ready for Plan 71-04 (pipeline wiring).
Resume with: `/gsd:execute-phase 71 --plan 04` (or `/gsd:autonomous --from 71-04` for full autonomous run).
Resume file: .planning/phases/71-llm-primary-extraction/71-04-pipeline-wiring-PLAN.md
