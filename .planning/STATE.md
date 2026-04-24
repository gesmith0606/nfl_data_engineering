---
gsd_state_version: 1.0
milestone: v7.1
milestone_name: Draft Season Readiness
status: Phase 71 shipped — ready for Phase 72
stopped_at: Phase 71 COMPLETE (5/5 plans). Plan 71-05 shipped — CLI --extractor-mode/--mode args + GHA EXTRACTOR_MODE env (gated on vars.ENABLE_LLM_ENRICHMENT) + CI-enforced LLM-04 cost gate (warm-cache projection $1.5700/week, gate <$5) + 71-BENCHMARK.md (rule=28 claude=156 ratio=5.57x, fixture commit 925d52e) + 71-SUMMARY.md. 165 sentiment tests green. LLM-01..05 all closed. Ready for Phase 72.
last_updated: "2026-04-24T22:12:54.602Z"
last_activity: 2026-04-24
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 5
  completed_plans: 6
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-24 after v7.1 Draft Season Readiness started)

**Core value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now with a production website + AI advisor ecosystem.
**Current focus:** Phase 71 — llm-primary-extraction

## Current Position

Phase: 72
Plan: Not started
Status: Phase 71 shipped — ready for Phase 72
Last activity: 2026-04-24

**Execution order (proposed):** 71 ✓ → 72 (depends on 71) → (73 ∥ 74 ∥ 75 parallel) → milestone close

Progress: 5/5 plans in Phase 71 (100%)
[████████████████████] 100%

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
- [71-04]: EXTRACTOR_MODE env precedence: explicit constructor arg wins; env only consulted when arg defaults to 'auto'; unknown env values fall through to 'auto' with INFO log (T-71-04-01 mitigation)
- [71-04]: Per-doc soft fallback wraps the entire batch call in try/except; on raise, _rule_fallback (RuleExtractor) processes each doc individually, claude_failed_count += len(batch). Daily cron always completes (D-06 fail-open contract preserved)
- [71-04]: _run_legacy_loop is byte-identical extraction of pre-71-04 per-doc loop; auto/rule/claude modes regression-locked
- [71-04]: Silver envelope gains "is_claude_primary": true ONLY when set (key omitted otherwise); enrich_silver_records short-circuits via bool(data.get("is_claude_primary", False)) — pre-71-04 envelopes unaffected
- [71-04]: Two new Silver sinks at data/silver/sentiment/non_player_pending/ and data/silver/sentiment/unresolved_names/ — partition layout mirrors signals/; envelope shape uses generic _write_envelope helper
- [71-04]: _build_extractor converted from @staticmethod to instance method for access to self._claude_client + self._cost_log; back-compat sweep verified zero unbound call sites in src/ scripts/ tests/
- [71-04]: When claude_primary requested but no client available, pipeline silently downgrades to RuleExtractor with WARNING log AND clears self._is_claude_primary so run loop takes legacy path
- [71-05]: CLI default for --extractor-mode is None (NOT 'auto') so main() can detect 'no override' and skip passing the kwarg to SentimentPipeline — preserves the EXTRACTOR_MODE env precedence Plan 71-04 built. Default 'auto' would clobber env-driven routing.
- [71-05]: ANTHROPIC_API_KEY missing-key WARNING gated to _MODES_REQUIRING_API_KEY = {'claude', 'claude_primary'} — rule/auto/unset don't need the key, no nagging. Tests verify both directions.
- [71-05]: GHA EXTRACTOR_MODE expression returns empty string when LLM enrichment is off. Pipeline _resolve_extractor_mode treats empty as 'auto', so off-state is byte-identical to no env var — clean rollback path via single GitHub Variable flip.
- [71-05]: Cost-projection CI gate imports BATCH_SIZE from src.sentiment.processing.extractor (NEVER hard-codes 8). Any future BATCH_SIZE tune at the source ripples through the projection automatically.
- [71-05]: Cost gate uses W18 warm-cache fixture (cache_read>0, cache_creation==0) for the projection — represents steady-state weekly operation. W17 cold-cache is informational only (one-shot ceiling).

### Pending Todos

Phase 71 complete. Production activation: `gh variable set ENABLE_LLM_ENRICHMENT --body 'true'` then wait for next daily cron (`0 12 * * *` UTC). Health-summary step will log `::notice::Extractor mode: claude_primary`. Cost-log Parquet files will appear under `data/ops/llm_costs/season=2026/week=NN/`. Next milestone work: Phase 72 (EVT — Event Flag Expansion + Non-Player Attribution; depends on 71). Phases 73 (External Projections) ∥ 74 (Sleeper League) ∥ 75 (Tech Debt) can run parallel.

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
Stopped at: Phase 71 COMPLETE (5/5 plans). Plan 71-05 shipped — CLI --extractor-mode/--mode args + GHA EXTRACTOR_MODE env (gated on vars.ENABLE_LLM_ENRICHMENT) + CI-enforced LLM-04 cost gate (warm-cache projection $1.5700/week, gate <$5) + 71-BENCHMARK.md (rule=28 claude=156 ratio=5.57x, fixture commit 925d52e) + 71-SUMMARY.md. 165 sentiment tests green. LLM-01..05 all closed. Ready for Phase 72.
Resume with: `/gsd:discuss-phase 72` then `/gsd:plan-phase 72` then `/gsd:execute-phase 72`.
Resume file: (no plan file yet — Phase 72 needs discussion + planning first)
