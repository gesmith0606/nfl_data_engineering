---
gsd_state_version: 1.0
milestone: v6.0
milestone_name: Website Production Ready + Agent Ecosystem
status: executing
stopped_at: Phase 63-01 complete (baseline audit); 63-02..06 pending
last_updated: "2026-04-18T00:40:14Z"
last_activity: 2026-04-18
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 9
  completed_plans: 4
  percent: 44
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-17)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 60 — data-quality

## Production Status

| Component | URL | Status |
|-----------|-----|--------|
| Frontend | https://frontend-jet-seven-33.vercel.app | LIVE (2026 preseason data) |
| Backend | https://nfldataengineering-production.up.railway.app | LIVE (Parquet fallback) |
| MAE | 4.92 (2022-2024, half_ppr) | Near v3.2 baseline (4.80) |
| Tests | 1,379+ passing | All green |

## Current Position

Phase: 63 (ai-advisor-hardening) — IN PROGRESS (1/6 plans)
Plan: 63-01 complete — baseline TOOL-AUDIT.md produced (4 PASS / 3 WARN / 5 FAIL)
Status: Wave-2 plans (63-02 schema, 63-03 missing routes, 63-04 data gaps) now have precise scope.
Last activity: 2026-04-18

Progress: [████░░░░░░] 44% (4 plans complete across v6.0)

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

## Accumulated Context

| Phase 60 P01 | 5min | 2 tasks | 2 files |
| Phase 60 P02 | 6min | 2 tasks | 2 files |
| Phase 60 P03 | 4min | 1 task  | 1 file  |
| Phase 63 P01 | 4min | 2 tasks | 2 files |

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v6.0]: All 6 phases are independent — no hard dependencies, work in any order
- [v4.1/P5]: Heuristic-only baseline is 4.87 MAE. QB XGB adds 0.05 for bias control.
- [SV2]: Rule-based extraction works without API key. Claude is optional upgrade.
- [AI]: Gemini 2.5 Flash (free) + Groq fallback. Tool-calling to FastAPI, not RAG.
- [Phase 60-01]: update_rosters combines team+position correction into a single pass against Gold parquet
- [Phase 60-01]: log_changes writes timestamped sections on every invocation (including dry-run and no-op) for continuous audit trail
- [Phase 60-02]: Sleeper search_rank is the primary live consensus source; FantasyPros API returns 403 so it is no longer tried
- [Phase 60-02]: Missing-consensus-player is a WARNING (not CRITICAL) because live Sleeper includes current rookies absent from Gold; preserves exit-code-zero contract for Plan 60-03 CI gate
- [Phase 60-02]: Freshness thresholds: Gold 7 days, Silver 14 days (per D-08)
- [Phase 60-03]: CI gate keys exclusively on sanity check exit code (0=deploy, 1=block); no stdout grep — preserves warnings-allowed contract from 60-02
- [Phase 60-03]: Added data/** to deploy-web.yml paths trigger so data-only commits (daily roster refresh) also validate before deploy
- [Phase 63-01]: httpx chosen for probe (already available via anthropic==0.92.0 transitive; no new requirement)
- [Phase 63-01]: TOOL_REGISTRY declared as plain `ast.Assign` (no annotation) so the plan's AST verification can detect it
- [Phase 63-01]: warn_on_empty flag separates off-season empty payloads from genuine bugs — keeps ship gate meaningful without false negatives in preseason
- [Phase 63-01]: Baseline result: 4 PASS / 3 WARN / 5 FAIL. FAILs bucket into 3 categories: schema_mismatch (2: getDraftBoard, getSentimentSummary), http_error_404 (3: getGamePredictions, getTeamRoster, compareExternalRankings)

### Pending Todos

None yet.

### Blockers/Concerns

- Groq + Google API keys in .env but not yet in Railway/Vercel env vars
- ANTHROPIC_API_KEY still not set (rule-based extraction working fine)
- 2025 roster data not ingested — limits player name resolution for sentiment
- Draft tool frontend (W9-02/03) not yet built

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Models | QB heuristic -2.47 bias fix | Acknowledged | v4.1 |
| Models | Bayesian/Quantile for production floor/ceiling | Researched, not shipped | v3.2 |
| Infra | Refresh AWS credentials + S3 sync | Expired March 2026 | v4.0 |
| Frontend | Draft tool UI (W9-02/03) | Planned | v4.0 |

## Session Continuity

Last session: 2026-04-18T00:40:14Z
Stopped at: Phase 63-01 baseline audit complete — TOOL-AUDIT.md written (4P/3W/5F). Ready for 63-02/03/04 fix waves.
Resume file: None
