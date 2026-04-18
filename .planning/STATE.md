---
gsd_state_version: 1.0
milestone: v6.0
milestone_name: Website Production Ready + Agent Ecosystem
status: executing
stopped_at: "Phase 63-02 complete — advisor tool hardening shipped. Local audit: 5 FAIL → 0 FAIL (7 PASS / 5 WARN / 0 FAIL). getSentimentSummary now carries total_articles/bullish_players/bearish_players alongside legacy total_docs/top_positive/top_negative; /api/lineups carries flat `lineup` field alongside nested `lineups`; /api/predictions and /api/lineups return empty envelopes (HTTP 200) instead of 404 on offseason-empty data; compareExternalRankings passes (router already registered in main.py). All 25 web + 8 schema tests passing. 6 commits. TOOL-AUDIT-LOCAL.md documents delta. Ready for 63-03 (rankings+external hardening), 63-04 (conversation persistence), 63-05 (widget reach), or 63-06 (live-site re-audit SHIP gate)."
last_updated: "2026-04-18T15:25:00.000Z"
last_activity: 2026-04-18 -- Phase 61-04 daily cron resilience shipped
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 26
  completed_plans: 13
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-17)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Phase 61 — news-sentiment-live

## Production Status

| Component | URL | Status |
|-----------|-----|--------|
| Frontend | https://frontend-jet-seven-33.vercel.app | LIVE (2026 preseason data) |
| Backend | https://nfldataengineering-production.up.railway.app | LIVE (Parquet fallback) |
| MAE | 4.92 (2022-2024, half_ppr) | Near v3.2 baseline (4.80) |
| Tests | 1,379+ passing | All green |

## Current Position

Phase: 61 (news-sentiment-live) — EXECUTING
Plan: 4 of 6 (shipped; 61-05 news UI + 61-06 optional Haiku enrichment remain)
Status: Executing Phase 61
Last activity: 2026-04-18 -- Phase 61-04 daily cron resilience shipped

Progress: [█████░░░░░] 50% (13 plans complete across v6.0)

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
| Phase 64 P01 | 38min | 2 tasks | 2 files |
| Phase 62 P01 | 5min | 2 tasks | 1 file  |
| Phase 65 P01 | 12min | 2 tasks | 2 files |
| Phase 61 P01 | 20min | 3 tasks | 8 files |
| Phase 62 P02 | 10min | 2 tasks | 4 files |
| Phase 64 P02 | 30min | 2 tasks | 5 files |
| Phase 63 P02 | 55min | 2 tasks | 7 files |
| Phase 61 P04 | 27min | 2 tasks | 4 files |

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
- [Phase 65-01]: Inventory result: 42 agents (11 ACTIVE / 31 FRAMEWORK-OWNED / 0 DORMANT / 0 REDUNDANT), 29 skills (12 DATA-OWNED / 5 DESIGN-HOLISTIC cluster / 9 DESIGN-TARGETED / 2 DOC-SPECIALIST / 1 FRAMEWORK)
- [Phase 65-01]: 5-skill design-holistic overlap cluster confirmed: impeccable, taste-skill, soft-skill, emil-design-eng, redesign-skill — all share banned-font lists, anti-AI-purple rules, GPU-safe motion, viewport stability directives
- [Phase 65-01]: Two consolidation options framed for 65-02 checkpoint — Option A (umbrella-with-modes) preferred, Option B (shared-rules include) as fallback
- [Phase 65-01]: code-reviewer (opus) vs git-code-reviewer (sonnet) near-redundancy flagged for 65-04 audit but kept ACTIVE (intentional pre-commit vs post-push division)
- [Phase 61-01]: Rule-first sentiment stance locked — new news sources are orthogonal to ANTHROPIC_API_KEY (D-01, D-04); Haiku enrichment demoted to optional website-only path
- [Phase 61-01]: Each ingestor owns module-local copies of _NAME_PATTERN + _TEAM_MENTIONS (web-scraper convention) rather than extracting a shared util — keeps coupling low, per D-01
- [Phase 61-01]: D-06 graceful-failure contract uniformly enforced — HTTPError/URLError/parse errors all log warning and exit 0, so daily cron is never blocked by upstream flakes
- [Phase 61-01]: Stdlib-only implementation (urllib + xml.etree.ElementTree) for the two new scripts, no new requirements.txt deps; feedparser kept isolated to the older RSS script
- [Phase 62-02]: Design-token layer is additive-only — tokens.css holds :root custom properties (no DOM selectors); theme.css keeps sole ownership of colors; zero visual change on shipment
- [Phase 62-02]: Added beyond the interface contract where AUDIT-BASELINE demanded it — --fs-micro (11px) absorbs 50+ text-[9/10/11px] uses; --pos-qb..fs consolidates 6 duplicated POSITION_COLORS maps for 62-03
- [Phase 62-02]: CSS durations in ms / TypeScript mirror in seconds (motion library convention); MOTION.base = 220ms keeps weighted feel on hover lifts vs a flat 200ms
- [Phase 62-02]: Stagger step locked at 40ms — keeps 10-item list entrance under 800ms (10 × 40 + 480 slower)
- [Phase 62-02]: Semantic spacing aliases (--gap-field/row/stack/section, --pad-card, --pad-card-sm) layered over raw --space-N so component code reads intent rather than magnitude
- [Phase 62-02]: Root .gitignore narrow un-ignore for web/frontend/src/lib/ — the Python-template lib/ rule was swallowing frontend source; pre-existing untracked frontend lib/ files logged to deferred-items.md for follow-up chore
- [Phase 64-02]: slot_hint assignment uses snap_pct ordering (not depth_chart_order — that column doesn't exist in bronze rosters)
- [Phase 64-02]: Status filter keeps ACT+RES so IR-returning starters stay visible (practice squad / cut excluded)
- [Phase 64-02]: OL LT/RT split via snap_pct ordering within T and G groups — cosmetic, bronze doesn't expose LT/RT granularity
- [Phase 64-02]: Offseason current-week returns max (season, week) with source=fallback instead of 503 — keeps frontend from breaking in April/May
- [Phase 64-02]: team_roster_service.py is the single parquet reader for teams/* namespace — 64-03 defense-metrics extends, does not duplicate
- [Phase 64-02]: Rating formula (round((1-(rank-1)/31)*49+50)) correctly scoped to 64-03, not 64-02 — grep confirms zero matches in 64-02 service/router code
- [Phase 63-02]: Dual-schema pattern preserved — advisor-facing keys (board, lineup, bullish_players, total_articles) added alongside legacy keys (players, lineups, top_positive, total_docs) so website widgets stay compatible while advisor contract is met
- [Phase 63-02]: Empty-envelope replaces 404 in /api/predictions and /api/lineups — advisor tool widgets render on success responses; offseason-missing data returns 200+empty list instead of HTTPException(404)
- [Phase 63-02]: FlatLineupPlayer model added alongside nested TeamLineup list — router populates both shapes from the same DataFrame iteration; no duplicate parquet reads
- [Phase 63-02]: Audit script getTeamRoster probe marked warn_on_empty=True — preseason emptiness is a legitimate WARN (consistent with other offseason-empty tools: news feed, predictions, team sentiment)
- [Phase 63-02]: Result: 5 FAIL → 0 FAIL in local audit (7 PASS / 5 WARN / 0 FAIL). EXTERNAL_SOURCE_DOWN category remains for 63-03 to verify when Sleeper cache is stale
- [Phase 61-04]: Daily cron hardened — 5 sources (RSS/Reddit/Sleeper/RotoWire/PFT) + rule-first extraction always runs regardless of ANTHROPIC_API_KEY; per-source failures isolated via try/except wrappers; pipeline exits 0 as long as one step succeeds
- [Phase 61-04]: ENABLE_LLM_ENRICHMENT repo variable (default 'false') wired into daily-sentiment.yml env block — implements D-04 feature flag at cron boundary; plan 61-06 can flip it without workflow edit
- [Phase 61-04]: Rule-first log discriminator uses isinstance(extractor, RuleExtractor) rather than is_available check — RuleExtractor.is_available is always True, so type-check is the only reliable way to identify D-06 path in stdout
- [Phase 61-04]: Step labels rebranded 1/6..6/6 → 1/8..8/8 in orchestrator stdout to reflect expanded source list; extractor type name embedded in StepResult.detail for post-hoc log diffing
- [Phase 61-04]: Health summary step (if: always()) emits ::notice:: annotations only for non-secret ENABLE_LLM_ENRICHMENT toggle — never echoes ANTHROPIC_API_KEY (T-61-04-01 mitigation)
- [Phase 61-04]: Resilience suite (7 tests) pins D-06 contract — test_single_ingestion_failure_does_not_abort_pipeline + test_extraction_runs_without_anthropic_api_key would regress if someone later tried to make LLM path mandatory

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

Last session: 2026-04-18T15:25:00Z
Stopped at: Phase 61-04 complete — daily cron resilience + D-06 guarantee shipped. RotoWire + PFT steps wired into scripts/daily_sentiment_pipeline.py (now 8 steps total). `.github/workflows/daily-sentiment.yml` hardened with ENABLE_LLM_ENRICHMENT env var (default 'false', D-04 feature flag) and health-summary ::notice:: step. 7 resilience tests in tests/sentiment/test_daily_pipeline_resilience.py pin the D-06 contract. Dry-run verified exit 0 with extractor=RuleExtractor when ANTHROPIC_API_KEY is absent. 3 commits on main (ff8ec21, c1b5bd6, e096860). Ready for 61-05 (news page UI), 61-06 (optional Haiku enrichment via ENABLE_LLM_ENRICHMENT flag), or 61-03 backtest wrap-up.
Resume file: None
