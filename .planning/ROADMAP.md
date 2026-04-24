# Roadmap: NFL Data Engineering Platform

## Milestones

- ✅ **v1.0 Bronze Expansion** — Phases 1-7 (shipped 2026-03-08)
- ✅ **v1.1 Bronze Backfill** — Phases 8-14 (shipped 2026-03-13)
- ✅ **v1.2 Silver Expansion** — Phases 15-19 (shipped 2026-03-15)
- ✅ **v1.3 Prediction Data Foundation** — Phases 20-23 (shipped 2026-03-19)
- ✅ **v1.4 ML Game Prediction** — Phases 24-27 (shipped 2026-03-22)
- ✅ **v2.0 Prediction Model Improvement** — Phases 28-31 (shipped 2026-03-27)
- ✅ **v2.1 Market Data** — Phases 32-34 (shipped 2026-03-28)
- ✅ **v2.2 Full Odds + Holdout Reset** — Phases 35-38 (shipped 2026-03-29)
- ✅ **v3.0 Player Fantasy Prediction System** — Phases 39-48 (shipped 2026-04-01)
- ✅ **v3.1 Graph-Enhanced Fantasy Projections** — Phases 49-53 (shipped 2026-04-03)
- ✅ **v3.2 Model Perfection** — Phases 54-57 (shipped 2026-04-09)
- *v4.0 Production Launch* — Phases W7-W12 (parallel, see `.planning/v4.0-web/`)
- *v5.0 Sentiment v2* — Phases SV2-01 through SV2-04 (complete)
- ✅ **v6.0 Website Production Ready + Agent Ecosystem** — Phases 60-65 (shipped 2026-04-20)
- ✅ **v7.0 Production Stabilization** — Phases 66-70 (shipped 2026-04-24; 4 human_needed + 1 passed — see `.planning/milestones/v7.0-ROADMAP.md`)
- 📋 **v7.1 External Projections + Sleeper League** — planned
- 📋 **v7.2 Marketing & Content** — planned

## Phases

<details>
<summary>✅ v6.0 Website Production Ready + Agent Ecosystem (Phases 60-65) — SHIPPED 2026-04-20</summary>

- [x] Phase 60: Data Quality (3/3 plans) — completed 2026-04-17
- [x] Phase 61: News & Sentiment Live (6/6 plans) — completed 2026-04-19
- [x] Phase 62: Design & UX Polish (6/6 plans) — completed 2026-04-20
- [x] Phase 63: AI Advisor Hardening (6/6 plans) — completed 2026-04-20
- [x] Phase 64: Matchup View Completion (4/4 plans) — completed 2026-04-20
- [x] Phase 65: Agent Ecosystem Optimization (4/4 plans) — completed 2026-04-20

Full details: `.planning/milestones/v6.0-ROADMAP.md` | Requirements: `.planning/milestones/v6.0-REQUIREMENTS.md`

</details>

<details>
<summary>✅ v7.0 Production Stabilization (Phases 66-70) — SHIPPED 2026-04-24</summary>

- [x] Phase 66: P0 Deployment Hotfixes (6 reqs) — human_needed, code shipped 2026-04-21
- [x] Phase 67: Roster Refresh v2 (6 reqs) — human_needed, code shipped 2026-04-22
- [x] Phase 68: Sanity-Check v2 (10 reqs, 57 tests) — 5/6 passed + 1 human_needed (live rollback proof)
- [o] Phase 69: Sentiment Backfill (5 reqs) — human_needed, blocked on GH Secret + Variable setup
- [x] Phase 70: Frontend Empty/Error States (5 reqs, 10 tests) — passed 2026-04-24

Full details: `.planning/milestones/v7.0-ROADMAP.md` | Requirements: `.planning/milestones/v7.0-REQUIREMENTS.md` | Audit: `.planning/v7.0-MILESTONE-AUDIT.md`

</details>

### 🚧 v7.1 Draft Season Readiness (In Progress)

**Milestone Goal:** Deliver draft-season-critical features before fantasy draft season opens — LLM-primary sentiment extraction (so offseason news produces real signals, not 0-signal RuleExtractor fallback), external projections comparison (ESPN/Sleeper/Yahoo side-by-side), Sleeper league integration (personalized rosters + advisor), and v7.0 tech debt cleanup.

**Phase Numbering:**
- Integer phases (71-75): Planned milestone work
- Decimal phases (71.1, etc.): Urgent insertions (if needed)

**Summary checklist:**

- [x] **Phase 71: LLM-Primary Extraction** — Shipped 2026-04-24. 5/5 plans complete. 5.57× LLM-03 ratio on offseason content; CI-enforced LLM-04 cost gate at $1.5700/week (gate <$5); 165 sentiment tests green; CLI + GHA EXTRACTOR_MODE knob ready for production activation via single GitHub Variable flip.
- [ ] **Phase 72: Event Flag Expansion + Non-Player Attribution** — Add is_drafted / is_rumored_destination / is_coaching_change / etc.; decide coach-and-reporter handling (team rollup vs separate channel)
- [ ] **Phase 73: External Projections Comparison** — ESPN + Sleeper + Yahoo weekly projections side-by-side with ours on projections page + new /api/projections/comparison endpoint
- [ ] **Phase 74: Sleeper League Integration** — Username auth → league listing → roster import → advisor `getUserRoster` tool → start/sit personalization
- [ ] **Phase 75: v7.0 Tech Debt Cleanup** — 8 items rolled forward (gitignore frontend configs, remove --no-verify, format-relative-time guard, duplicate relativeTime consolidation, etc.)

## Phase Details

### Phase 71: LLM-Primary Extraction
**Goal**: Convert `src/sentiment/processing/extractor.py` from rule-primary + LLM-enrichment-only to LLM-primary with rule fallback. Offseason Bronze content (drafts/trades/coaching/rookie buzz) must produce signals instead of silent zeros. Preserve dev-mode zero-cost path.
**Depends on**: Nothing (first v7.1 phase)
**Requirements**: LLM-01, LLM-02, LLM-03, LLM-04, LLM-05
**Success Criteria** (what must be TRUE):
  1. `ClaudeExtractor` class exists as a peer to `RuleExtractor`, emitting structured `{player_name, event_type, sentiment_score, summary, event_flags}` signals from raw Bronze docs (not just enrichment)
  2. Re-running sentiment pipeline on 2025 W17 + W18 Bronze with `ENABLE_LLM_ENRICHMENT=true` produces ≥ 5× more signals than rule-based; measured and committed to SUMMARY
  3. Prompt-cache the player list across docs; target < $5/week at 80 docs/day
  4. Deterministic tests via recorded Claude responses — no live API calls in CI
  5. `RuleExtractor` path preserved for dev + API-outage scenarios (`ENABLE_LLM_ENRICHMENT=false` is zero-cost)

**Plans:** 5/5 plans executed (Phase 71 COMPLETE)

Plans:
- [x] 71-01-schema-and-contracts-PLAN.md — PlayerSignal/PipelineResult schema extensions + ClaudeClient Protocol
- [x] 71-02-fixtures-and-fake-client-PLAN.md — FakeClaudeClient + recorded W17/W18 offseason Bronze + Claude fixtures
- [x] 71-03-batched-claude-extractor-PLAN.md — Batched primary extraction + prompt caching + CostLog Parquet sink + benchmark (LLM-03 ratio=5.57x)
- [x] 71-04-pipeline-wiring-PLAN.md — SentimentPipeline claude_primary branch + per-doc soft fallback + LLMEnrichment short-circuit (137 sentiment tests passing)
- [x] 71-05-cli-gha-and-benchmark-summary-PLAN.md — CLI --extractor-mode/--mode + GHA EXTRACTOR_MODE env + CI-enforced LLM-04 cost gate ($1.5700/wk warm-cache) + 71-BENCHMARK.md + phase 71-SUMMARY.md (165 sentiment tests passing)

### Phase 72: Event Flag Expansion + Non-Player Attribution
**Goal**: Extend `event_flags` beyond injury/trade/usage to cover the draft-season domain (rookie buzz, trade rumors, coaching changes, cap cuts). Decide how to attribute non-player subjects (coaches/reporters/teams) that Phase 69 surfaced as `player_id: null` rejects.
**Depends on**: Phase 71 (Claude extractor is the producer of these new flags)
**Requirements**: EVT-01, EVT-02, EVT-03, EVT-04, EVT-05
**Success Criteria**:
  1. New flags `is_drafted`, `is_rumored_destination`, `is_coaching_change`, `is_trade_buzz`, `is_holdout`, `is_cap_cut`, `is_rookie_buzz` in schema + emitted by ClaudeExtractor
  2. Non-player subjects either attribute to team (rollup) or route to `non_player_news` channel — decision captured in CONTEXT.md
  3. Weekly aggregator no longer silent-drops `player_id: null`; tracks metric or attributes per (2)
  4. `/api/news/team-events` populates expanded flags for ≥ 15 of 32 teams on 2025 W17+W18 backfill
  5. Advisor `getPlayerNews` / `getTeamSentiment` return non-empty for ≥ 20 teams post-backfill

### Phase 73: External Projections Comparison
**Goal**: Surface ESPN + Sleeper + Yahoo weekly projections side-by-side with ours on the projections page. Users compare; we show transparency. Sleeper already has MCP; ESPN/Yahoo may require scraping.
**Depends on**: Nothing (parallel with 71/72)
**Requirements**: EXTP-01, EXTP-02, EXTP-03, EXTP-04, EXTP-05
**Success Criteria**:
  1. Bronze ingestion at `data/bronze/external_projections/{source}/season=YYYY/week=WW/` for ESPN + Sleeper + Yahoo
  2. Silver merged schema `{player_id, source, projected_points, scoring_format}` with all 4 sources (ours + 3 external)
  3. New `/api/projections/comparison?season=Y&week=W&scoring=F` endpoint returns 4-source shape
  4. Frontend projections page renders comparison table with delta column + position filter
  5. Cron refresh keeps external data current; `data_as_of` chip surfaces freshness
**UI hint**: yes

### Phase 74: Sleeper League Integration
**Goal**: Let users connect their Sleeper account → import rosters → get personalized advice. Sleeper MCP already wired; need frontend auth + backend user-scoped context + new advisor tool.
**Depends on**: Nothing (parallel with 71/72/73)
**Requirements**: SLEEP-01, SLEEP-02, SLEEP-03, SLEEP-04
**Success Criteria**:
  1. Username auth flow: frontend form → backend resolves leagues + rosters via Sleeper API
  2. `/leagues` route with league selector + roster view; rosters cached in session
  3. New advisor tool `getUserRoster({league_id})` returning user's lineup + bench
  4. Start/sit advisor uses actual roster when auth is active (vs hypothetical baseline)
**UI hint**: yes

### Phase 75: v7.0 Tech Debt Cleanup
**Goal**: Clear the 8 debt items rolled forward from v7.0 audit so subsequent milestones start clean.
**Depends on**: Nothing (parallel with all)
**Requirements**: TD-01, TD-02, TD-03, TD-04, TD-05, TD-06, TD-07, TD-08
**Success Criteria**:
  1. Auto-rollback no longer uses `--no-verify` (single revert with `-m`); structural test guards against regression
  2. `web/frontend/**/*.json` whitelisted in root `.gitignore`; CI + fresh clones get vitest deps
  3. `daily-sentiment.yml` roster refresh uses `$(date +%Y)` not hardcoded year
  4. Duplicate `relativeTime()` removed from `news-feed.tsx` + `player-news-panel.tsx` (consolidated to `formatRelativeTime`)
  5. `formatRelativeTime("")` does not produce "Updated unknown"
  6. `VALID_NFL_TEAMS` has single Rams entry (LA, not LAR)
  7. CLAUDE.md documents that Bronze rosters + depth_charts are committed as of 2026-04-24

### 📋 v7.2 Marketing & Content (Planned)

### 📋 v7.2 Marketing & Content (Planned)

Preliminary scope — not yet broken into phases.
- Remotion video generation from projection data (MKT-01)
- YouTube/Instagram/TikTok automated distribution (MKT-02)
- NotebookLM podcast generation pipeline (MKT-03)

## Progress

**Execution Order:**
v7.0 phases execute as: 66 → (67 ∥ 68 ∥ 69) → 70
- 66 is blocking for 69 (API key + Docker image) and 70 (backend stops 422-ing)
- 67 and 68 can run in parallel with 69 (no data dependencies between them)
- 70 comes last because it benefits from all upstream data being correct

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 60. Data Quality | v6.0 | 3/3 | Complete | 2026-04-17 |
| 61. News & Sentiment Live | v6.0 | 6/6 | Complete | 2026-04-19 |
| 62. Design & UX Polish | v6.0 | 6/6 | Complete | 2026-04-20 |
| 63. AI Advisor Hardening | v6.0 | 6/6 | Complete | 2026-04-20 |
| 64. Matchup View Completion | v6.0 | 4/4 | Complete | 2026-04-20 |
| 65. Agent Ecosystem Optimization | v6.0 | 4/4 | Complete | 2026-04-20 |
| 66. P0 Deployment Hotfixes | v7.0 | 0/TBD | Not started | - |
| 67. Roster Refresh v2 | v7.0 | 0/TBD | Not started | - |
| 68. Sanity-Check v2 | v7.0 | 0/TBD | Not started | - |
| 69. Sentiment Backfill | v7.0 | 0/TBD | Not started | - |
| 70. Frontend Empty/Error States | v7.0 | 0/TBD | Not started | - |
| 71. LLM-Primary Extraction | v7.1 | 5/5 | Complete | 2026-04-24 |
| 72. Event Flag Expansion | v7.1 | 0/TBD | Not started | - |
| 73. External Projections Comparison | v7.1 | 0/TBD | Not started | - |
| 74. Sleeper League Integration | v7.1 | 0/TBD | Not started | - |
| 75. v7.0 Tech Debt Cleanup | v7.1 | 0/TBD | Not started | - |
