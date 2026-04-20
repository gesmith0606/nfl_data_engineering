---
gsd_state_version: 1.0
milestone: v6.0
milestone_name: Website Production Ready + Agent Ecosystem
status: completed
stopped_at: "Phase 62-03 complete — DSGN-02 consistency pass landed on the app shell (page-container, header, sidebar, Heading) + pages 1-5 (overview, accuracy, projections, rankings, predictions). Six atomic commits on main (2134cff shell, 1a8bfcb overview, d2673af accuracy, dc1404c projections, f183e59 rankings, 4e63ab5 predictions). Every touched file now routes typography/spacing/elevation through the 62-02 token scale; zero raw text-(xs|sm|base|lg|xl|2xl|3xl|4xl) or text-[Npx] utilities remain; all 5 pages GET 200 on dev server; typecheck clean. Overview page re-audited 6.8 → ~7.1 (clears DSGN-01 gate). POSITION_COLORS consolidation + Select-width unification deferred to 62-04/62-06. Added --space-16 + --size-header tokens additively. Next up: 62-04 motion primitives + pages 6-11."
last_updated: "2026-04-20T00:57:00Z"
last_activity: 2026-04-20
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 26
  completed_plans: 21
  percent: 81
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

Phase: 62
Plan: 03 complete; 04 up next (motion primitives + pages 6-11)
Status: Phase 62-03 complete; shell + pages 1-5 token-compliant
Last activity: 2026-04-20

Progress: [███████░░░] 70% (18 plans complete across v6.0)

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 61 | 6 | - | - |
| 63 | 6 | - | - |

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
| Phase 61 P06 | 17min | 2 tasks | 8 files |
| Phase 63 P04 | 15min | 2 tasks | 7 files |
| Phase 62 P03 | 18min | 2 tasks | 13 files |

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
- [Phase 61-06]: Optional LLM enrichment shipped per D-04: new src/sentiment/enrichment/ package with LLMEnrichment class + enrich_silver_records batch driver; double-gated on ENABLE_LLM_ENRICHMENT=true AND ANTHROPIC_API_KEY set; fail-open at three layers (client build, enrich(), batch driver) so disabled pipelines exit 0 and enabled-without-key exits 0 with 0 records
- [Phase 61-06]: D-02 auto-mode lock cemented — SentimentPipeline._build_extractor("auto") now returns RuleExtractor() unconditionally regardless of ANTHROPIC_API_KEY; "claude" mode still works for explicit callers; prior "use Claude if available" behaviour is gone from the default path
- [Phase 61-06]: Non-destructive sidecar pattern — enrich_silver_records writes to data/silver/sentiment/signals_enriched/season=YYYY/week=WW/ while original signals/ tree remains untouched; news_service silently merges sidecar {summary, refined_category} into NewsItem when present
- [Phase 61-06]: Deferred anthropic SDK import inside _run_llm_enrichment — disabled pipelines never trigger the import path, keeping startup clean; when enabled but key is missing, _build_client returns None and logs a single warning
- [Phase 61-06]: CLI flag --enable-llm-enrichment uses action='store_true' with default=None so main() can distinguish explicit CLI override from env var fallback (ENABLE_LLM_ENRICHMENT accepts true/1/yes, case-insensitive)
- [Phase 61-06]: T-61-06-01 mitigation — log line always emits bool(os.environ.get('ANTHROPIC_API_KEY')); key value is never format-argumented anywhere in the enrichment or pipeline code
- [Phase 63-04]: `week` in getPositionRankings is Zod `.optional()` (not `.default(1)`) so the LLM cannot silently fabricate — presence/absence of week is the grounding signal
- [Phase 63-04]: Dedicated /api/projections/latest-week endpoint (not piggybacked on /api/projections) so the advisor can resolve scaffolding before committing to a full projection read; cheaper when preseason data is missing
- [Phase 63-04]: ProjectionResponse.meta is Optional — backward compatible with the already-deployed Railway Parquet fallback that predates this plan
- [Phase 63-04]: resolveDefaultWeek returns null on fetch failure (distinct from {week: null}) so the advisor can distinguish 'season has no data' from 'backend unreachable'
- [Phase 63-04]: Prefer backend meta.data_as_of over the latest-week helper's value — meta is closer to the actual projection read and guaranteed to agree with the rows returned
- [Phase 63-04]: Upstream traceability pattern (data_as_of on Gold responses) ready to extend to getPlayerProjection, compareStartSit, getTeamRoster with minimal code
- [Phase 62-03]: Shell primitives (page-container, header, sidebar, Heading) are the single place the base scale changes — downstream pages never reach past the shell for typography/spacing; future --fs-h2 / --space-4 tunings propagate without per-page edits
- [Phase 62-03]: Heading component gained optional `level: 1|2|3` prop (additive API, defaults to 2) so h1/h3 consumers can land in 62-04/62-05 without re-editing the shared primitive
- [Phase 62-03]: --space-16 (64px) + --size-header aliases added to tokens.css so header chrome carries named intent (was h-16 magic); additive-only, zero consumer break
- [Phase 62-03]: POSITION_COLORS consolidation deferred from 62-03 — cross-component import restructure violates "visual-only" guardrail; --pos-* tokens from 62-02 remain the destination for 62-04/62-06 sweep
- [Phase 62-03]: Filter Select widths (w-28/w-24/w-36) preserved — best done in one cross-page sweep in 62-04 with shared SELECT_WIDTHS constant than piecemeal here
- [Phase 62-03]: Overview page re-audited 6.8 → ~7.1 (+0.3) — PageContainer heading restoration + token typography + --gap-stack rhythm all lift the page above the DSGN-01 >7 gate
- [Phase 62-03]: Icon sizing normalized to h-[var(--space-N)] w-[var(--space-N)] across injury/tier/position badges and empty-state icons — makes it explicit that icon sizes pull from the same 4px grid as paddings

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

Last session: 2026-04-20T00:57:00Z
Stopped at: Phase 62-03 complete — DSGN-02 consistency pass landed on the app shell + pages 1-5. Six atomic commits on main (2134cff shell, 1a8bfcb overview, d2673af accuracy, dc1404c projections, f183e59 rankings, 4e63ab5 predictions). Every touched file routes typography/spacing/elevation through 62-02 tokens; zero raw text-* or text-[Npx] utilities remain; all 5 pages 200 on dev server; typecheck clean. Overview re-audited 6.8 → ~7.1. POSITION_COLORS + Select-width consolidation deferred to 62-04/62-06. Added --space-16 + --size-header tokens additively. Next up: 62-04 motion primitives + pages 6-11.
Resume file: None
